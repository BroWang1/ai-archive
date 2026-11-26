import os
import logging
import uuid
import datetime

import settings

from libs.util import write_file, mv_file_safe, read_file_iter

logger = logging.getLogger('storage')


APP_MEDIA_ROOT = settings.APP_MEDIA_ROOT

os.makedirs(os.path.join(APP_MEDIA_ROOT, 'media/temp'), exist_ok=True)

def path_join(pre_path, *args, check_slash=True):
    if check_slash:
        args = list(map(lambda arg: arg[1:] if arg[0] == '/' else arg, args))
    full_path = os.path.join(pre_path, *args)
    if os.sep == '\\':
        full_path = full_path.replace('\\', '/')
    return full_path


def get_url_path(abs_path):
    url_path = abs_path.replace(APP_MEDIA_ROOT, '')
    if url_path[0] != '/':
        url_path = '/' + url_path
    return url_path


def get_abs_path(relative_path):
    return path_join(APP_MEDIA_ROOT, relative_path)


def gen_tmp_file_path():
    url_path = path_join('/', 'media', 'temp', f'{str(uuid.uuid4())}.tmp')
    return get_abs_path(url_path), url_path


def gen_project_file_path(project_id, media_type, file_name):
    """media_type: image_resource, comm """
    if media_type not in ('image_resource', 'comm'):
        raise Exception('Unsupported project media type')
    month = datetime.date.today().strftime('%Y%m')
    url_path = path_join('/', 'media', media_type, month, str(project_id), file_name)
    return get_abs_path(url_path), url_path


def gen_job_file_path(project_id, job_id, media_type, file_name):
    """media_type: 'data', 'image', 'comm' """
    if media_type not in ('data', 'image', 'comm'):
        raise Exception('Unsupported job media type')
    month = datetime.date.today().strftime('%Y%m')
    url_path = path_join('/', 'media', media_type, month, str(project_id), str(job_id), file_name)
    return get_abs_path(url_path), url_path


def write_temp_file(buffer_or_fp, chunk_size=1024 * 64, ext=''):
    abs_path, url_path = gen_tmp_file_path()
    if ext:
        url_path += ext
        abs_path += ext
    return write_file(buffer_or_fp, abs_path, chunk_size), url_path


def mv_file(src, dest):
    mv_file_safe(src, dest)
    logger.info(f'mv_file src:{src} dest:{dest}')
    return src, dest


def mv_to_temp(src, strict=False):
    if not os.path.exists(src) and not strict:
        logger.warning(f'mv_to_temp src:{src} file not exist')
        return
    _, src_file_name = os.path.split(src)
    dest_abs_path, url_path = gen_tmp_file_path()
    dest_path, dest_file_name = os.path.split(dest_abs_path)
    dest = os.path.join(dest_path, f'{src_file_name}.{dest_file_name}')
    mv_file_safe(src, dest)
    logger.info(f'mv_to_temp src:{src} dest:{dest}')
    return src, dest


def read_file(abs_path):
    return b''.join(bytes(chunk) for chunk in read_file_iter(abs_path))


def read_url_file(url_path):
    return read_file(get_abs_path(url_path))
