import os
import logging
import time
import uuid
import threading
import shutil

from django.http import HttpResponse
from django.views.generic import View

import settings
from libs import ApiResponse, cache, storage, util
from libs.defs import Minute_5, ApiErrorEnum

logger = logging.getLogger('lqa_view')


class IndexView(View):
    def get(self, request):
        return HttpResponse(f"Index")


def view_health(request):
    """健康检查（免登录）"""
    return ApiResponse(data={'status': 'ok'})


class TicketView(View):
    """可以考虑使用 django-ratelimit 限速"""
    def get(self, request):
        uuid_str = uuid.uuid1()
        cache.ticket_cache.set(uuid_str, int(time.time()) + Minute_5)
        return ApiResponse(data={'ticket': uuid_str})


class DiskUsageView(View):
    """磁盘使用情况"""
    def get(self, request):
        total, used, free = shutil.disk_usage(settings.APP_MEDIA_ROOT)
        return ApiResponse(data={'total': total, 'used': used, 'free': free})

        # #下面统计正式文件大小   实测太慢了  放弃使用
        # default_stat = {'total': 0, 'used': 0, 'free': 0, 'expire_at': 0}
        # stat = cache.comm_cahce.get('disk', json=True)
        # if stat and util.time_ms() < stat['expire_at']:    # 使用缓存数据  有效期一天
        #     return ApiResponse(data=stat)
        # else:
        #     # redis锁：判断是否计算任务正在执行
        #     lqa_lock_disk_stat_key = 'lqa_lock_disk_stat'
        #     ok = cache.get_redis_client().set(lqa_lock_disk_stat_key, 1, nx=True, xx=False, ex=Minute_5*3)
        #     if not ok:
        #         return ApiResponse(data=default_stat)
        #
        #     def _disk_stat():
        #         total_size = 0
        #         file_count = 0
        #         for dirpath, dirnames, filenames in os.walk(settings.APP_MEDIA_ROOT):
        #             for filename in filenames:
        #                 filepath = os.path.join(dirpath, filename)
        #                 try:
        #                     total_size += os.path.getsize(filepath)     # 获取文件大小并累加
        #                     file_count += 1
        #                 except OSError as e:
        #                     logger.error(f"cant access file:{filepath}. err: {e}")
        #         total, used, free = shutil.disk_usage(settings.APP_MEDIA_ROOT)
        #         expire_at = util.time_ms() + 86400000
        #         stat_ = {'total': total, 'used': used, 'free': free, 'app_used': total_size,
        #                 'file_count': file_count, 'expire_at': expire_at}
        #         cache.comm_cahce.set('disk', stat_, json=True, timeout=86400 + 1200)
        #         cache.get_redis_client().delete(lqa_lock_disk_stat_key)     # 执行完 删掉key
        #         logger.info(f'disk_stat end')
        #
        #     thread = threading.Thread(target=_disk_stat)
        #     thread.daemon = False
        #     thread.start()
        #     logger.info(f'disk_stat start thread: {thread}')
        #
        #     return ApiResponse(data=default_stat)


def view_upload_file(request):
    if len(request.FILES) == 0:
        return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='未上传文件')
    req_file = next(request.FILES.values())
    file_name = req_file.name
    _, file_extension = os.path.splitext(file_name)
    tmp_abs_path, url_path = storage.write_temp_file(req_file, ext=file_extension if file_extension else '')
    logger.info(f'upload file_name:{file_name} url_path:{url_path}')
    return ApiResponse(data={'file_name': file_name, 'file_path': url_path})


def view_test(request):
    num = request.GET.get('num', 0)
    delay = int(request.GET.get('delay', 10))
    logger.info(int(time.time()*1000))
    return ApiResponse(data={"num": num, "delay": delay})
