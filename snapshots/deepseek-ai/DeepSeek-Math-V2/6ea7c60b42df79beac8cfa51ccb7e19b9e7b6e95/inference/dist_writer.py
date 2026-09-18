# copy from https://gitlab.deepseek.com/deepseek/hai-llm/-/blob/master/scripts/dist_safetensor_writer.py

import os
import math
import torch
from pathlib import Path
from datetime import timedelta
from multiprocessing.shared_memory import SharedMemory
from uuid import uuid4
import numpy as np
import time
import json
try:
    from hf3fs_fuse.io import make_iovec, make_ioring, ioring, register_fd, deregister_fd, h3fio
except Exception:
    pass


INT_LEN = 8
BYTE_ORDER = 'big'


def tensor_to_bytes(tensor: torch.Tensor) -> bytes:
    if tensor.numel() == 0:
        return b''
    return tensor.view(torch.int8).numpy().data.cast('B')
    

except_fs = {'cpu'}
clusters = ['jd', 'hg']
hf3fs_paths = []
hf3fs_mount_points = []
for cluster in clusters:
    hf3fs_paths += os.listdir(f'/hf3fs-{cluster}') if os.path.exists(f'/hf3fs-{cluster}') else []
    hf3fs_mount_points += [os.path.join(f'/hf3fs-{cluster}', f) for f in hf3fs_paths if f not in except_fs]


def get_hf3fs_mount_point(file_path: str) -> str:
    rp =  os.path.realpath(Path(file_path).absolute())
    return '/'.join(rp.split('/')[:3])

class DistWriter():
    def __init__(self, max_ops=100<<10, write_buf_size=1<<29):
        self.max_ops = max_ops
        self.write_buf_size = write_buf_size
        self.shm = SharedMemory(name=f'hf3fs-iovs-{uuid4()}', create=True, size=self.write_buf_size)
        self._iov = {}
        self._buf = {}
        self._ior = {}
        for hf3fs_mount_point in hf3fs_mount_points:
            try:
                iov = make_iovec(self.shm, hf3fs_mount_point, block_size=0, numa=-1)
                buf = memoryview(iov.iov)
                ior = make_ioring(hf3fs_mount_point, 100 << 10, for_read=False, io_depth=-1, numa=-1)
                self._iov[hf3fs_mount_point] = iov
                self._buf[hf3fs_mount_point] = buf
                self._ior[hf3fs_mount_point] = ior
            except Exception:
                pass
        self.shm.unlink()
        self.fd_cache = {}

    def _open(self, file_path):
        if self.fd_cache.get(file_path) is None:
            # os.makedirs(os.path.dirname(file_path),  exist_ok=True)
            hf3fs_mount_point = get_hf3fs_mount_point(file_path)
            try:
                fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_SYNC)
            except Exception:  # 发现在 weka 上打开文件会 FileExistsError
                fd = os.open(file_path, os.O_WRONLY | os.O_SYNC)
            register_fd(fd)
            self.fd_cache[file_path] = (fd, hf3fs_mount_point)
        return self.fd_cache[file_path]

    def _close_all(self, file_total_bytes):
        for fd, _ in self.fd_cache.values():
            os.truncate(fd, file_total_bytes)
            deregister_fd(fd)
            os.close(fd)
        self.fd_cache = {}

    def chunk_batch_pwrite(self, write_offsets):
        chunks = []
        chunk = []
        total = 0
        def add_chunk():
            nonlocal chunk, total
            if len(chunk) > 0:
                chunks.append(chunk)
                chunk = []
                total = 0

        for r in write_offsets:
            write_file_path, write_bytes, write_file_offset = r
            write_length = len(write_bytes)
            if write_length == 0:
                continue
            if write_length > self.write_buf_size:
                add_chunk()
                chunks.append([r])
            elif total + write_length > self.write_buf_size:
                add_chunk()
                chunk.append(r)
                total += write_length
            else:
                chunk.append(r)
                total += write_length
                if len(chunk) == self.max_ops:
                    add_chunk()
        add_chunk()
        return chunks

    def convert_to_pwrite_list(self, filepath, tensors, metadata):
        head = {}
        if metadata is not None:
             head["__metadata__"] = metadata
        dtype_dict = {
            torch.float64 : 'F64',
            torch.float32: 'F32',
            torch.float16 : 'F16',
            torch.bfloat16: 'BF16',
            torch.float8_e4m3fn: 'F8_E4M3',
            torch.int64 : 'I64',
            torch.int32:  'I32',
            torch.int16 : 'I16',
            torch.int8:  'I8',
            torch.uint8 : 'U8',
            torch.bool : 'BOOL'
        }
        cur_off = 0
        values = []
        for k, v in tensors.items():
            cur_len = v.numel() * v.element_size()
            item = dict(
                dtype = dtype_dict[v.dtype],
                shape = list(v.shape),
                data_offsets = [cur_off, cur_off + cur_len],
            )
            cur_off += cur_len
            head[k] = item
            values.append(v)
        head_bytes = json.dumps(head, ensure_ascii=True).replace(" ","").encode("utf8")
        n = np.array([len(head_bytes)], dtype = np.uint64).tobytes()
        assert np.frombuffer(n, dtype=np.int64)[0] == len(head_bytes)
        head_bytes = n + head_bytes
        p_list = []
        p_list.append((filepath, head_bytes, 0))
        cur_off = len(head_bytes)
        for v in values:
            data_bytes = tensor_to_bytes(v)
            p_list.append((filepath, data_bytes, cur_off))
            cur_off += len(data_bytes)
        return p_list

    def save_tensors(self, filepath, tensors, metadata = None):
        pwrite_list = self.convert_to_pwrite_list(filepath, tensors, metadata)
        file_total_bytes = sum([len(item[1]) for item in pwrite_list])
        for chunk in self.chunk_batch_pwrite(pwrite_list):
            if len(chunk) == 1:
                # 如果超过 self.write_buf_size 的数据，只允许单次 pwrite
                write_file_path, write_bytes, write_file_offset = chunk[0]
                fd, hf3fs_mount_point = self._open(write_file_path)
                iov = self._iov[hf3fs_mount_point]
                buf = self._buf[hf3fs_mount_point]
                ior = self._ior[hf3fs_mount_point]
                content_view = write_bytes
                _write = 0
                total = len(write_bytes)
                while _write < total:
                    to_write = min(self.write_buf_size, total-_write)
                    buf[:to_write] = content_view[_write:_write+to_write]
                    ior.prepare(iov[:to_write], False, fd, write_file_offset+_write)
                    submit_result = ior.submit()
                    total_waited = 0
                    results = []
                    while True:
                        res = submit_result.wait(max_results=1000, min_results=0, timeout=timedelta(seconds=0))
                        total_waited += len(res)
                        results += res
                        if total_waited == 1:
                            break
                        time.sleep(0.01)
                    write_len = results[0].result
                    assert write_len == to_write, f'hf3fs 返回的 write_len({write_len}) 不匹配 file_path={write_file_path} offset={write_file_offset} to_write={to_write}'
                    _write += write_len
            elif len(chunk) > 0:
                # 多次 pwrite，加起来的总和不能超过 self.write_buf_size，避免最后一个比较大，但是 buf 只剩很小，要提交很多次的问题
                # 这里只允许 batch write 同一个 mount point 的数据，不然比较难管理
                hf3fs_mount_point = self._open(chunk[0][0])[1]
                iov = self._iov[hf3fs_mount_point]
                buf = self._buf[hf3fs_mount_point]
                ior = self._ior[hf3fs_mount_point]
                ops = []
                buf_offsets = []
                buf_offset = 0
                for write_file_path, write_bytes, write_file_offset in chunk:
                    fd, h = self._open(write_file_path)
                    assert h == hf3fs_mount_point, f'不能 load 不同 mount point 的数据 {h} {hf3fs_mount_point}'
                    write_length = len(write_bytes)
                    op = [write_file_path, write_length, write_file_offset]
                    ops.append(op)
                    assert buf_offset+write_length <= self.write_buf_size, f'batch write 超过了 buf 最大长度 {self.write_buf_size}'
                    buf[buf_offset:buf_offset+write_length] = write_bytes
                    ior.prepare(iov[buf_offset:buf_offset+write_length], False, fd, write_file_offset, userdata=op)
                    buf_offsets.append((buf_offset, buf_offset+write_length))
                    buf_offset += write_length

                submit_result = ior.submit()
                total_waited = 0
                results = []
                while True:
                    res = submit_result.wait(max_results=1000, min_results=0, timeout=timedelta(seconds=0))
                    total_waited += len(res)
                    results += res
                    if total_waited == len(ops):
                        break
                    time.sleep(0.01)
                for result in results:
                    write_file_path, write_length, write_file_offset = result.userdata
                    assert result.result == write_length, f'hf3fs 返回的 write_len({result.result}) 不匹配 file_path={write_file_path} offset={write_file_offset} to_write={write_length}'
        self._close_all(file_total_bytes)

def save_file(tensors, filepath, metadata = None):
    DistWriter().save_tensors(filepath, tensors, metadata=metadata)