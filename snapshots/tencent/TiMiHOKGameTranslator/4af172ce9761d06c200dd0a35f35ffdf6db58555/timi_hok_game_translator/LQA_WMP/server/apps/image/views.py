import os
import logging
import time

import orjson
from django.views.generic import View
from django.db import DatabaseError, transaction
from django.forms.models import model_to_dict
from django.db.models import Q
from PIL import Image as PImage

import settings
from apps.bug.models import Bug
from apps.data.models import ReviewedEnum, Data
from apps.job.models import Job
from apps.image import service as img_svr
from apps.image.models import *
from apps.image.tasks import run_ai_sign, run_submit_ai_sign
from libs.defs import ApiErrorEnum, JobDiscernEnum
from libs import ApiResponse, PageView, cache, lodash, storage
from .schemas import *

logger = logging.getLogger('img_view')


def _patch_image_info(image, image_bugs_stat, datas_stat=None):
    if not datas_stat:
        datas_stat = {}
    stat = image_bugs_stat.get(image['id'])
    image['bug_num'] = stat.get('bug_num', 0) if stat else 0
    image['shot_img_path'] = datas_stat.get(image['data_id'], {}).get('shot_img_path', '')
    image['module_id'] = datas_stat.get(image['data_id'], {}).get('module_id', None)
    return image


class ImageListView(PageView):
    Query_Fields = ('id', 'pk__gte', 'pk__lte', 'cur_id', 'job_id', 'data_id', 'err_type', 'will_review', 'is_latest',
                    'file_name__contains', 'created_begin_at', 'created_end_at',
                    'updated_begin_at', 'updated_end_at', 'reviewed', 'rect_location__contains')

    def get(self, request):
        """
        GET /api/image/list
        """
        vmi = ImageListSchema.model_validate(request.GET.dict())
        info_type, page, page_size = vmi.info_type, vmi.page, vmi.page_size

        if vmi.pk__gte is not None and vmi.pk__lte is not None and vmi.pk__gte > vmi.pk__lte:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='请检查图片ID范围')

        param = self.make_query_params(vmi)
        page_by_where = self.page_by_where(param)
        if vmi.languages is not None:
            param['language__in'] = vmi.languages
        if vmi.data_id:   # 多语种对比场景
            if vmi.job_id is None:
                return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='data_id查询时需要job_id参数')
            if 'id' in param:
                del param['id']
        elif vmi.module_ids is not None:     # 模块搜索
            if 'data_id' in param:
                del param['data_id']
            param = Q(data_id__in=Data.objects.filter(module__in=vmi.module_ids)) & Q(**param)
        if vmi.ai_bug_types and len(vmi.ai_bug_types) > 0:
            if isinstance(param, dict):
                param = Q(**param)
            q = Q()
            for ai_bug_type in vmi.ai_bug_types:
                q |= Q(ai_bug_types__contains=ai_bug_type)
            param &= q
        if vmi.rect_location__contains and vmi.languages is None:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='检测文本查询时必须指定"区域语言"')

        fields = ()
        if info_type == 0:
            fields = [field.name for field in Image._meta.fields]
            fields.remove('rect_location')
            fields.remove('ai_check_detail')

        total, images = self.page_query(Image, param, page, page_size, fields=fields, page_by_where=page_by_where)

        image_bugs_stat = {}
        datas_stat = {}
        if len(images) > 0:
            image_ids = []
            data_ids = []
            img_keys = ('file_path', 'ai_mark_img_path', 'ai_rect_img_path')
            for image_ in images:
                image_ids.append(image_['id'])
                data_ids.append(image_['data_id'])
                for img_key in img_keys:
                    image_[img_key] = f"{image_[img_key]}?_t={image_['updated_at']}" if image_[img_key] else ''
            image_bugs_stat = img_svr.image_of_bug_num(image_ids, images[0]['job_id'])
            datas = Data.objects.filter(pk__in=data_ids).values('id', 'shot_img_path', 'module_id')
            datas_stat = {data['id']: data for data in datas}
        for image in images:
            _patch_image_info(image, image_bugs_stat, datas_stat)
        return ApiResponse(data={'list': images, 'total': total, 'page': vmi.page, 'page_size': vmi.page_size})

    def patch(self, request):
        vmi = ImageListUpdateSchema.model_validate(orjson.loads(request.body))
        body = vmi.model_dump(exclude_unset=True)
        ids = body['ids']
        del body['ids']
        num = Image.update_db(ids, body)
        return ApiResponse(data={'num': num})


class ImageView(View):

    # 计算 同job data language 下的is_latest iteration属性的正确性
    LOCK_KEY_JOB_DATA_LAN_PREFIX = 'image_job_data_lan_latest_update'

    @classmethod
    def _lock_key(cls, job_id, data_id, language):
        return f'{cls.LOCK_KEY_JOB_DATA_LAN_PREFIX}:{job_id}_{data_id}_{language}'

    def get(self, request):
        """
        GET /api/image/entity
        """
        image_id = int(request.GET.get('image_id', 0))
        if not image_id:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='参数错误')
        image = Image.objects.filter(pk=image_id).values().first()
        if not image:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到image:{image_id}')
        image_bugs_stat = img_svr.image_of_bug_num((image['id'], ), image['job_id'])
        data = Data.objects.filter(pk=image['data_id']).values('id', 'shot_img_path', 'module_id').first()
        datas_stat = {data['id']: data} if data else {}
        _patch_image_info(image, image_bugs_stat, datas_stat)
        return ApiResponse(data={'image': image})

    def post(self, request):
        """编辑器调用 上传图片   POST /api/image/entity"""
        vmi = ImageCreateSchema.model_validate(request.POST.dict())

        if len(request.FILES) == 0:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='未上传图片')
        req_file = next(request.FILES.values())

        if vmi.regression:
            bug_ids = vmi.bug_ids
            if len(bug_ids) == 0:
                return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='回归任务，bug_id不运行未空')
            bugs_cnt = Bug.objects.filter(pk__in=bug_ids).count()
            if bugs_cnt != len(bug_ids):
                return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='存在无效的 bug_id')

        project_id, data_id, job_id, rect_locations, ai_sign, language = (vmi.project_id, vmi.data_id, vmi.job_id,
                                                                          vmi.rect_locations, vmi.ai_sign, vmi.language)

        # if not Data.objects.filter(job_id=job_id, pk=data_id).exists():
        #     return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'job_id:{job_id} data_id:{data_id} dont match')

        if not Job.objects.filter(id=job_id, project_id=project_id).exists():
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'job:{job_id} project_id:{project_id} 不合法')

        current_user = request.user
        rect_locations_dict = orjson.loads(rect_locations)
        file_name = req_file.name

        image_dr = Image.objects.filter(project_id=project_id, job_id=job_id, data_id=data_id).first()
        data_review = DataReview.objects.filter(project_id=project_id, data_id=data_id).first()
        data_review_new = None

        data_review_update = False
        size_t = PImage.open(req_file).size
        size_s = f"{size_t[0]},{size_t[1]}"
        if ((data_review and data_review.image_id == 0)
                or (image_dr and data_review and data_review.image_id == image_dr.id)):
            rect_location_clean, rect_location_check, rect_location_dirty = (
                img_svr.DataReviewService.auto_review(rect_locations_dict, size_t))
            data_review.rect_location = rect_locations
            data_review.check_rect_location = rect_location_check
            data_review.dirty_rect_location = rect_location_dirty
            data_review.size = size_s
            data_review.reviewer = "system"
            clean_rect_location = rect_location_clean
            data_review_update = True
        elif data_review and data_review.dirty_rect_location:
            clean_rect_location, _ = img_svr.DataReviewService.data_clean(rect_locations,
                                                                          data_review.dirty_rect_location)
        else:
            rect_location_clean, rect_location_check, rect_location_dirty = (
                img_svr.DataReviewService.auto_review(rect_locations_dict, size_t))
            review_params = {
                "project_id": project_id,
                "data_id": data_id,
                "rect_location": rect_locations,
                "check_rect_location": rect_location_check,
                "dirty_rect_location": rect_location_dirty,
                "size": size_s,
                "reviewer": "system"
            }
            data_review_new = DataReview(**review_params)
            clean_rect_location = rect_location_clean
        # 处理文件
        abs_path, url_path = storage.gen_job_file_path(project_id, job_id, 'image', file_name)
        req_file.seek(0)
        tmp_abs_path, _ = storage.write_temp_file(req_file)

        image_info = {
            'project_id': project_id,
            'job_id': job_id,
            'data_id': data_id,
            'language': language,
            'rect_location': rect_locations,
            'file_name': file_name,
            'file_path': url_path,
            'ai_sign': ai_sign,
            'size': size_s
        }
        image = Image(**image_info)

        def _save_db(lock):
            try:
                ids = list(Image.objects.filter(job_id=job_id, data_id=data_id, language=language)
                           .values_list('id', flat=True))
                image.iteration = len(ids) + 1  # 这里为了计算iteration准确性 所以要加锁
                with transaction.atomic():
                    if len(ids) > 0:
                        Image.update_db(ids, {'is_latest': SwitchEnum.OFF})
                    image.save()
                    if data_review_new:
                        data_review_new.image_id = image.id
                        data_review_new.save()
                        Data.update_db(data_id, {'reviewed': ReviewedEnum.AUTO})
                    elif data_review_update:
                        data_review.image_id = image.id
                        data_review.save()
                        Data.update_db(data_id, {'reviewed': ReviewedEnum.AUTO})
                    storage.mv_file(tmp_abs_path, abs_path)
            except DatabaseError as err:
                logger.error('ImageView post err:', exc_info=err)
                return ApiResponse(ApiErrorEnum.ERROR, msg='创建失败 写数据库失败')
            except Exception as err:
                logger.error('ImageView post err1:', exc_info=err)
                return ApiResponse(ApiErrorEnum.ERROR, msg=f'创建失败 err:{str(err)}')
            logger.info(f'[event.image.add] user:{current_user["name"]} id:{image.id}')

        lock_key = self._lock_key(job_id, data_id, language)
        ok, save_db_response = cache.try_lock(lock_key, _save_db)
        if not ok:
            return ApiResponse(ApiErrorEnum.ERROR, msg='创建失败 获取锁失败')
        if save_db_response:
            return save_db_response

        task_id = ''
        if vmi.ai_sign or vmi.create_bug or vmi.regression:
            ctx = img_svr.prepare_ai_sign_task_ctx(data_review, image, ctx={
                'clean_rect_location': clean_rect_location,
                'regression': vmi.regression,
                'bug_ids': vmi.bug_ids,
                'discern': vmi.discern,
                'create_bug': vmi.create_bug,
                'staff_name': current_user['name']
            }, trace=f'image_upload:{image.id}')
            event = 'event.run_ai_sign_0'
            ctx['_event'] = event
            task = run_ai_sign.apply_async((ctx,))  # 编辑器上传图片
            task_id = task.task_id
            logger.info(f'[{event}] user:{current_user["name"]} '
                        f'task_id:{task.task_id} image_id:{image.id}')
        image_info = model_to_dict(image)
        del image_info['rect_location']
        return ApiResponse(data={'image': image_info, 'task_id': task_id})

    def delete(self, request):
        """
        DELETE /api/image/entity
        """
        body = orjson.loads(request.body)
        image_ids = body.get('image_ids', [])
        image_id = int(body.get('image_id', '0'))
        project_id = int(body.get('project_id', 0))
        if not project_id or (len(image_ids) == 0 and image_id == 0):
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='参数错误')
        if image_id:
            image_ids = [image_id]

        imgs = Image.objects.filter(pk__in=image_ids).values()
        if len(imgs) != len(image_ids):
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='image_ids存在异常数据')

        errs = []
        use_imgs = []
        for img in imgs:
            if project_id != img['project_id']:
                errs.append((img["id"], f'image_id:{img["id"]} project_id:{project_id} 不匹配'))
                continue
            use_imgs.append(img)

        job_ids = list(Job.objects.filter(project_id=project_id).values_list('id', flat=True))

        def _save_db(lock, img_info):
            ts = [int(time.time() * 1000)]
            with (transaction.atomic()):
                ts.append(int(time.time() * 1000))
                image_id = img_info['id']
                images = Image.objects.filter(job_id=job_id, data_id=data_id, language=language, project_id=project_id
                                              ).order_by('-iteration', '-id').values('id', 'is_latest')
                if len(images) == 0:
                    return
                ts.append(int(time.time() * 1000))
                #  计算 iteration 和 is_latest
                max_iteration_of_image_id = 0
                all_image_ids_set = set()
                for image_ in images:
                    if image_['id'] != image_id:
                        all_image_ids_set.add(image_['id'])
                        if max_iteration_of_image_id == 0:
                            max_iteration_of_image_id = image_['id']
                if len(all_image_ids_set) > 0:
                    all_image_ids_set.remove(max_iteration_of_image_id)
                    logger.info(f'delete image, set image_id:{all_image_ids_set} is_latest=0')
                    Image.update_db(all_image_ids_set, {'is_latest': 0})
                if max_iteration_of_image_id:
                    logger.info(f'delete image, set image_id:{max_iteration_of_image_id} is_latest=1')
                    Image.update_db(max_iteration_of_image_id, {'is_latest': 1})
                ts.append(int(time.time() * 1000))
                #  更新DataReview
                data_review = DataReview.objects.filter(project_id=project_id, image_id=image_id).first()
                if data_review:
                    ts.append(int(time.time() * 1000))
                    rect_location = check_rect_location = dirty_rect_location = '{}'
                    image_id_ = 0
                    size_ = ''
                    #  为了用上索引 这里查询用job_id__in=job_ids 替代 project_id=project_id
                    image_new = Image.objects.filter(job_id__in=job_ids, data_id=data_id).exclude(id=image_id)\
                        .order_by('id').first()
                    if image_new:
                        ts.append(int(time.time() * 1000))
                        image_id_ = image_new.id
                        size_ = image_new.size
                        ret = img_svr.DataReviewService.auto_review(image_new.rect_location, image_new.size)
                        ts.append(int(time.time() * 1000))
                        rect_location = image_new.rect_location
                        check_rect_location = ret[1]
                        dirty_rect_location = ret[2]
                        logger.info(
                            f'delete image, update data_review:{data_review.id} with image:{image_new.id}')
                    else:
                        logger.info(f'delete image, update data_review:{data_review.id} empty')
                    data_review.rect_location = rect_location
                    data_review.check_rect_location = check_rect_location
                    data_review.dirty_rect_location = dirty_rect_location
                    data_review.reviewer = "system"
                    data_review.size = size_
                    data_review.image_id = image_id_
                    data_review.save()
                    Data.update_db(data_id, {'reviewed': ReviewedEnum.AUTO})
                logger.info(ts)
                # 删除Image记录
                Image.objects.filter(pk=image_id).delete()
                logger.info(f'delete image: {image_id}')
                # 删除文件
                for field in ('file_path', 'ai_mark_img_path', 'ai_rect_img_path'):
                    field_path = img_info[field]
                    if field_path:
                        file_path_abs = storage.get_abs_path(field_path)
                        storage.mv_to_temp(file_path_abs)
                        logger.info(f'delete image {image_id} {project_id} {field_path}')
            logger.info(f'[event.image.del] user:{current_user["name"]} image_id:{image_id}')

        current_user = request.user
        for img_info_ in use_imgs:
            try:
                job_id, data_id, language = img_info_['job_id'], img_info_['data_id'], img_info_['language']
                lock_key = self._lock_key(job_id, data_id, language)
                ok, _ = cache.try_lock(lock_key, _save_db, img_info_)
                if not ok:
                    errs.append((img_info_['id'], '删除失败 获取锁失败'))
            except Exception as err:
                logger.error('DataView save err:', exc_info=err)
                errs.append((img_info_['id'], str(err)))

        return ApiResponse(data={'errs': errs})


class ImageAiSignView(View):

    def post(self, request):
        """手动批量图片识别     POST /api/image/ai_sign"""
        vmi = ImageAiSignRequestSchema.model_validate(orjson.loads(request.body))
        image_id, job_id, discern, languages = vmi.image_id, vmi.job_id, vmi.discern, vmi.languages
        if not image_id and not job_id:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'job_id和image_id不能同时为空')
        logger.info(f'image ai sign: image_id:{image_id} job_id:{job_id}')

        current_user = request.user
        param = {}
        if languages and len(languages) > 0:
            param['language__in'] = languages
        if image_id:
            param['pk'] = image_id
        else:
            param.update({'job_id': job_id, 'is_latest': 1})
        ctx = {'param': param, 'current_user': current_user, 'discern': discern}
        if image_id:    # 单个任务，同步执行
            run_submit_ai_sign(ctx)
        else:   # 批量任务，异步执行
            run_submit_ai_sign.apply_async((ctx,))
        return ApiResponse(msg='提交成功')


class DataReviewView(View):
    def get(self, request):
        """GET /api/image/data_review """
        data_id = int(request.GET.get('data_id', 0))
        project_id = int(request.GET.get('project_id', 0))

        if not data_id or not project_id:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM)

        dr = DataReview.objects.filter(project_id=project_id, data_id=data_id).first()
        if not dr:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='数据无审核记录，请先还原图片')
        dr = model_to_dict(dr)
        rect_location = img_svr.DataReviewService.rect_location_to_corners(dr['rect_location'], dr['size'])
        dr['rect_location'] = rect_location
        return ApiResponse(data={'data_review': dr})

    def patch(self, request):
        """PATCH /api/image/data_review """
        vmi = DataReviewPatchSchema.model_validate(orjson.loads(request.body))
        try:
            orjson.loads(vmi.check_rect_location)
            orjson.loads(vmi.dirty_rect_location)
        except Exception as err:
            logger.error(f'data_review parse err: {err}')
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'rect_location 或 dirty_rect_location json解析失败')

        dr = DataReview.objects.filter(pk=vmi.id).values('id', 'data_id').first()
        if not dr:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到 DataReview:{vmi.id}')
        data_id = dr['data_id']
        if not Data.objects.filter(pk=data_id).exists():
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到 Data:{data_id}')

        staff = request.user['name']
        body = vmi.model_dump(exclude={'id'}, exclude_unset=True)
        body['reviewer'] = staff
        with transaction.atomic():
            DataReview.update_db(vmi.id, body)
            Data.update_db(data_id, {'reviewed': ReviewedEnum.MANUAL})

        return ApiResponse()

