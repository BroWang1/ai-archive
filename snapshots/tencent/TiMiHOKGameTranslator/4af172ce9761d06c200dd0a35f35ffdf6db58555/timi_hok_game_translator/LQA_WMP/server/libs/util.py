import os
import time
import datetime
import hashlib
from functools import partial
from io import BytesIO
import base64

import orjson
from PIL import Image
from django.db.models import Choices
from django.core.files.base import File
from requests import request, JSONDecodeError, HTTPError, URLRequired, TooManyRedirects
import jwt


def time_ms():
    return int(time.time() * 1000)


def datetime_ms(dt=None, del_tz=True):
    """
    dt: datetime
    tz: 去除dt的tzinfo信息, 因为settings.USE_TZ一般设置为False, 表示django处理datetime对时区无感知, 如果dt带有tzinfo, 存db时会报错

    由于django在json序列化时只保留了datetime毫秒的前3位, 所以为了后端和前端使用一致, 生成时间转换一下
    这个方法目的是保留毫秒的前3位 2024-12-06T15:37:30.540123 => 2024-12-06T15:37:30.540000
    """
    if dt and del_tz and dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    if not dt:
        dt = datetime.datetime.now()
    return dt.replace(microsecond=int(dt.microsecond / 1000) * 1000)


def str_to_ms(ts, format='%Y-%m-%d %H:%M:%S'):
    """%Y-%m-%d %H:%M:%S to ms"""
    dt = datetime.datetime.strptime(ts, format)
    return int(dt.timestamp() * 1000)


def ms_to_str(ms):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ms / 1000))


class open_file_safe(object):

    def __init__(self, filepath, mode='r'):
        self.filepath = filepath
        self.mode = mode
        self.fp = None

    def __enter__(self):
        parent_dir = os.path.dirname(self.filepath)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        self.fp = open(self.filepath, self.mode)
        return self.fp

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fp and not self.fp.closed:
            self.fp.close()


def mv_file_safe(src, dest):
    if os.path.isfile(dest):
        os.remove(dest)
    p_path = os.path.dirname(dest)
    if not os.path.isdir(p_path):
        os.makedirs(p_path)
    os.rename(src, dest)


def write_file(buffer_or_fp, file_path=None, chunk_size=1024 * 64):
    with open(file_path, 'wb') as fp:
        if isinstance(buffer_or_fp, File):
            for chunk in buffer_or_fp.chunks(chunk_size):
                fp.write(chunk)
        else:
            for i in range(0, len(buffer_or_fp), chunk_size):
                fp.write(buffer_or_fp[i:i + chunk_size])
    return file_path


def read_file_iter(filepath, chunk_size=1024 * 64):
    with open(filepath, 'rb') as fp:
        for chunk in iter(partial(fp.read, chunk_size), b''):
            yield chunk


def choices_to_python(obj: Choices):
    return tuple(
        map(lambda item: {'value': item[0], 'name': item[1], 'label': item[2]}, zip(obj.values, obj.names, obj.labels)))


def md5(content):
    md5_hash = hashlib.md5()
    md5_hash.update(content.encode('utf-8') if isinstance(content, str) else content)
    return md5_hash.hexdigest()


def encode_jwt(payload, secret_key):
    return jwt.encode(payload, secret_key, algorithm='HS256')


def decode_jwt(token, secret_key):
    try:
        return 0, jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as err:
        return 1, '签名已过期'
    except jwt.InvalidTokenError as err:
        return 2, '非法的Token'
    except Exception:
        return 3, '未知'


def judge_rectangle(corners):
    """判断是否是标准文本框
    :param corners: dict, 位置信息
    :param height: int, 图像高度
    :return: 判断是否是标准矩形框
    """
    x1 = int(corners[0]["x"])
    y1 = int(corners[0]["y"])
    x2 = int(corners[1]["x"])
    y2 = int(corners[1]["y"])
    x3 = int(corners[2]["x"])
    y3 = int(corners[2]["y"])
    x4 = int(corners[3]["x"])
    y4 = int(corners[3]["y"])
    if x1 != x2 or x3 != x4 or y1 != y4 or y2 != y3:
        return False
    return True


def coordinate_trans(corners, height):
    """坐标变换, 将左下角为原点的坐标点转换为左上角为原点的坐标点, 如果是标准矩形用 (x,y,w,h) 表示, 如果非标准矩形用转换后的坐标点表示
    :param corners: dict, 位置信息
    :param height: int, 图像高度
    :param is_rectangle: bool, 默认标准文本框, 返回思维向量, 否则保持原4个点坐标
    :return: 转化后的位置坐标 (x1, y1, x2, y2)
    """
    is_rectangle = judge_rectangle(corners)

    if is_rectangle:
        x1 = int(corners[1]["x"])
        y1 = height - int(corners[1]["y"])
        x2 = int(corners[3]["x"])
        y2 = height - int(corners[3]["y"])
        trans_location = (x1, y1, x2, y2)   # x, y, w, h
    else:
        x1 = int(corners[0]["x"])
        y1 = height - int(corners[0]["y"])
        x2 = int(corners[1]["x"])
        y2 = height - int(corners[1]["y"])
        x3 = int(corners[2]["x"])
        y3 = height - int(corners[2]["y"])
        x4 = int(corners[3]["x"])
        y4 = height - int(corners[3]["y"])
        trans_location = (x1, y1, x2, y2, x3, y3, x4, y4)
    return is_rectangle, trans_location


def err_response_text(err):
    return (err.response.text if err.response is not None else '') if hasattr(err, 'response') else str(err)


def retry_request(method, url, params=None, data=None, json=None, headers=None, timeout=15,
                  retry=2, resp_json=True, **kwargs):
    for idx in range(retry):
        try:
            with request(method, url, params=params, data=data, json=json, headers=headers,
                           timeout=timeout, allow_redirects=False, **kwargs) as resp:
                resp.raise_for_status()
                return None, resp.json() if resp_json else resp
        except (JSONDecodeError, HTTPError, URLRequired, TooManyRedirects) as err:
            return err, None
        except Exception as err:
            if idx == retry - 1:
                return err, None


def compress_image_ify(file_path_abs, limit=1024 * 1024 * 5):
    st = os.stat(file_path_abs)
    if st.st_size > limit:  # 大于 5MB 压缩
        img_io = BytesIO()
        quality = int(1.0 * limit / st.st_size * 100) - 10
        if quality <= 0:
            quality = 10
        with Image.open(file_path_abs) as fp:
            fp.save(img_io, format="JPEG", optimize=True, quality=quality)
            img_io.seek(0)
            return img_io, quality
    return None, 0


def make_enum_validator(enum_cls):
    def validator(v, info):
        return enum_cls[v] if v.startswith('LAN') or v == 'DEFAULT' else enum_cls(int(v))
    return validator


def make_item_array_validator(sep=',', item_class=int):
    def validator(v, info):
        ret = []
        v = v.strip()
        if not v:
            return ret
        items = v.split(sep)
        for item in items:
            ret.append(item_class(item.strip()))
        return ret
    return validator


def _seq_generator():
    """简单生成序列, 注意不是线程安全的"""
    start = 1000
    num = start
    while True:
        yield num
        num += 1
        if num > 100000:
            num = start


seq_generator = _seq_generator()


def get_client_ip(request) -> tuple[Exception, str]:
    try:
        # 获取真实client_ip
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        return None, ip
    except Exception as err:
        return err, ''


def base64_encode_file_iter(file_path, chunk_size=1024*96, encode='utf-8'):
    """
    对文件内容流式编码, 减少内存开销
    file_path   文件名
    chunk_size  为了保持和整体编码一致 只能使用3的倍数 切记
    """
    if chunk_size % 3 != 0:
        raise Exception('chunk_size must be a multiple of 3')
    for chunk in read_file_iter(file_path, chunk_size):
        yield base64.b64encode(chunk).decode(encode)


def make_json_validator():
    def validator(v, info):
        try:
            return orjson.loads(v)
        except:
            raise ValueError('json parse error')
    return validator

def make_img_url_validator():
    def validator(v, info):
        idx = v.find('?')
        return v[:idx] if idx != -1 else v
    return validator


if __name__ == '__main__':
    pass
    # ret = decode_jwt(
    #     'xxxxxxxxxxxx')
    # print(ret)
    # t = time_ms()
    # print(t)
    # ts = ms_to_str(t)
    # print(ts)
    # print(str_to_ms(ts))

    # now = datetime.datetime.now()
    # print(f'1: {now}')
    #
    # from django.core.serializers.json import DjangoJSONEncoder
    # import json
    #
    # data = {"abc": now, "dt": datetime.date.today(), "tm": datetime.time(),
    #         "content": "metaclass 是 Python 面向对象里最难理解, 也是最难使用的魔术代码, "
    #                    "正常情况下, 你不会碰到需要使用 metaclass 的情况, 所以, 以下内容看不懂也没关系, 因为基本上你不会用到"}
    #
    # data1 = json.dumps(data, cls=DjangoJSONEncoder)
    # print(f'json: {data1}')
    #
    # data2 = (orjson.dumps(data)).decode('utf-8')
    # print(f'orjson: {data2}')
    #
    # data3 = (orjson.dumps(data, default=ApiResponse._encode_default, option=orjson.OPT_PASSTHROUGH_DATETIME)).decode('utf-8')
    # print(f'orjson1: {data3}')
    # t1 = time.time()
    # for i in range(10000):
    #     json.dumps(data, cls=DjangoJSONEncoder)
    # t2 = time.time()
    # for i in range(10000):
    #     (orjson.dumps(data, default=ApiResponse._encode_default, option=orjson.OPT_PASSTHROUGH_DATETIME))
    # t3 = time.time()
    # print((t2 - t1) * 1000)
    # print((t3 - t2) * 1000)

    # payload = { 'uid': 2, 'exp': int(time.time()) + 86400 }
    # jwt_str = encode_jwt(payload)
    # print(jwt_str)
    # print(md5(jwt_str))
