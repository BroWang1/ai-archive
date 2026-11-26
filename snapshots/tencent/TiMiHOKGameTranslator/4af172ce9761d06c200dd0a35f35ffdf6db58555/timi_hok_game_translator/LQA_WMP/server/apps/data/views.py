import os
import gzip
import logging

import orjson
from django.views.generic import View
from django.db import transaction, DatabaseError, IntegrityError
from django.db.models import Q
from django.http.response import HttpResponse
from django.forms.models import model_to_dict

from apps.project.models import Project, Module
from apps.job.models import Job
from apps.image.models import DataReview, Image
from apps.data.models import Data, ImagerResource
from libs.defs import ApiErrorEnum, SwitchEnum
from libs import ApiResponse, PageView, cache, storage
from libs.util import md5, read_file_iter
from .schemas import *

logger = logging.getLogger('data_view')


class DataListView(PageView):
    Query_Fields = ('project_id', 'id', 'pk__gte', 'pk__lte', 'job_id', 'cur_id', 'name__contains', 'resource_version',
                    'module_id', 'created_begin_at', 'created_end_at')

    def get(self, request):
        vmi = DataListSchema.model_validate(request.GET.dict())

        project_id, info_type = vmi.project_id, vmi.info_type

        if vmi.pk__gte is not None and vmi.pk__lte is not None and vmi.pk__gte > vmi.pk__lte:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='请检查ID范围')

        param = self.make_query_params(vmi)
        page_by_where = self.page_by_where(param)
        if vmi.reviewed is not None:
            if vmi.reviewed == 0:
                param['reviewed'] = 0
            else:
                param['reviewed__gt'] = 0

        # 当按任务筛选时，除了 Data.job_id = ? 的"原生"数据，
        # 还需要把 Job.data_ids 里"外挂"的数据一并查出来（创建任务时勾选的其它任务数据）
        if vmi.job_id is not None:
            extra_data_ids = Job.objects.filter(pk=vmi.job_id).values_list('data_ids', flat=True).first() or []
            if len(extra_data_ids) > 0:
                job_id_val = param.pop('job_id')
                param = Q(**param) & (Q(job_id=job_id_val) | Q(pk__in=extra_data_ids))

        total, datas = self.page_query(Data, param, vmi.page, vmi.page_size, page_by_where=page_by_where)
        # 查询 image.file_path
        data_ids = [o['id'] for o in datas]
        data_image_map = {}
        image_ids_set = set()
        if len(data_ids) > 0:
            drs = DataReview.objects.filter(project_id=project_id, data_id__in=data_ids).values('data_id', 'image_id')
            for dr_ in drs:
                data_image_map[dr_['data_id']] = dr_
                image_ids_set.add(dr_['image_id'])
        image_dict = {p_['id']: p_ for p_ in Image.objects.filter(pk__in=image_ids_set).values('id', 'file_path',
                                                                                               'updated_at')}
        _block = {}
        for data in datas:
            if info_type == 0 and len(data['name']) > 400:  # 太长就截取
                data['name'] = data['name'][:200] + ' ... ' + data['name'][len(data['name'])-200:]
            image_id = data_image_map.get(data['id'], _block).get('image_id', 0)
            image = image_dict.get(image_id)
            data['revert_img_path'] = image['file_path'] + f'?_t={image["updated_at"]}' if image else ''

        return ApiResponse(data={'list': datas, 'total': total, 'page': vmi.page, 'page_size': vmi.page_size})

    def patch(self, request):
        obj = DatasUpdateSchema.model_validate(orjson.loads(request.body))
        ids, resource_version, module_id = obj.ids, obj.resource_version, obj.module_id
        param = {}
        if resource_version is not None:
            param['resource_version'] = resource_version
        if module_id:
            param['module_id'] = module_id
        if len(param) == 0:
            return ApiResponse(ApiErrorEnum.ERROR, msg='resource_version和module_id不能同时为空')
        # count = Data.objects.filter(pk__in=ids).count()
        # if count != len(ids):
        #     return ApiResponse(ApiErrorEnum.ERROR, msg='存在无效ids，请刷新页面')
        try:
            Data.update_db(ids, param)
            datas = Data.objects.filter(pk__in=ids).values()
            if resource_version:
                for data in datas:
                    cache.resource_version_cache.zadd(data['project_id'], {resource_version: data['id']})
        except Exception as err:
            logger.error('DataView save err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'更新失败 err:{err}')
        return ApiResponse(data={'list': datas})

    def delete(self, request):
        vmi = DatasDeleteSchema.model_validate(orjson.loads(request.body))
        ids = vmi.ids

        datas = Data.objects.filter(pk__in=ids).values('id', 'project_id')
        if len(datas) != len(ids):
            return ApiResponse(ApiErrorEnum.ERROR, msg='存在无效ids，请刷新页面')
        if len(datas) == 0:
            return ApiResponse(ApiErrorEnum.ERROR, msg='无有效数据')

        project_id = datas[0]['project_id']
        updated_num = 0
        try:
            updated_num = Data.update_db(ids, {'is_delete': SwitchEnum.ON})
            if updated_num > 0:
                cache.resource_version_cache.reset(project_id)
            # 跟随Data数据库表做物理删除
            # for data_ in datas:
            #     data_id_, file_path = data_['id'], data_['file_path']
            #     abs_path = storage.get_abs_path(file_path)
            #     storage.mv_to_temp(abs_path)
            #     logger.info(f"_delete_on_node id:{data_id_} file_path:{file_path}")
        except Exception as err:
            logger.error('delete data err:', exc_info=err)
            if updated_num == 0:
                return ApiResponse(ApiErrorEnum.ERROR, msg=f'删除失败 err:{err}')
        return ApiResponse(data={'ids': ids})


class DataView(View):
    content_types = ('json', 'gzip')

    def post(self, request):
        """SDK调用 上传data"""
        content_type = request.headers.get('content-type')
        _, ext = content_type.split('/')
        if ext not in self.content_types:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'body support {self.content_types}')
        # todo 这里以后可以进一步优化一下减小内存开销：用form提交 需要存数据库的字段放field里，用不到的直接存文件
        try:
            body = gzip.decompress(request.body) if ext == 'gzip' else request.body
            body = orjson.loads(body)
            project_id = int(body['project_id'])
            job_id = int(body['job_id'])
            data_dict = body['data']
        except Exception as err:
            logger.error('decode err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'body解析出错 err: {str(err)}')

        name = (data_dict.get("name", '')).strip()
        if len(name) == 0:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='name不能未空')
        if not Job.objects.filter(pk=job_id, project_id=project_id).exists():
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'未找到job:{job_id}')

        resource_version = (data_dict.get("gameData", {}).get("resourceVersion", '')).strip()
        device = {'phone_type': (data_dict.get("phoneType", '')).strip(), 'screen_w': 0, 'screen_h': 0}
        device['screen_w'] = int(data_dict.get('sizeX', 0))
        device['screen_h'] = int(data_dict.get('sizeY', 0))
        # try:  ## 不从里面拿数据了，减少内存开销
        #     ui = orjson.loads(data_dict.get('uiJson'))
        #     device['screen_w'] = int(ui.get('screenWidth', 0))
        #     device['screen_h'] = int(ui.get('screenHeight', 0))
        # except orjson.JSONDecodeError:
        #     pass

        try:
            data = Data(project_id=project_id, job_id=job_id, name=name, resource_version=resource_version,
                        device=device)
            tmp_data_file, _ = storage.write_temp_file(gzip.compress(orjson.dumps(data_dict), 1))
            with transaction.atomic():
                data.save()
                abs_path, url_path = storage.gen_job_file_path(project_id, job_id, 'data', f"{data.id}_data.gzip")
                storage.mv_file(tmp_data_file, abs_path)
                data.file_path = url_path
                data.save(update_fields=['file_path'])
            if resource_version:
                cache.resource_version_cache.zadd(project_id, {resource_version: data.id})
        except Exception as err:
            logger.error('DataView save err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'创建失败 err:{err}')
        logger.info(f'[event.data.add] user:{request.user["name"]} data_id:{data.id} file_path:{data.file_path}')
        return ApiResponse(data={'data': model_to_dict(data)})

    def patch(self, request):
        body = orjson.loads(request.body) if request.content_type == 'application/json' else request.POST.dict()
        vmi = DataUpdateSchema.model_validate(body)
        data_id, shot_img_path, module_id = vmi.id, vmi.shot_img_path, vmi.module_id

        mapping = vmi.model_dump(exclude={'id'}, exclude_unset=True)
        if len(mapping) == 0:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='没有可更新的参数')

        data = Data.objects.filter(pk=data_id).values('id', 'project_id', 'job_id', 'shot_img_path').first()
        if not data:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'data: {data_id} 未找到')

        project_id, job_id = data['project_id'], data['job_id']

        if module_id and not Module.objects.filter(pk=module_id, project_id=project_id).exists():
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'module_id: {module_id} 未找到')

        if shot_img_path and data['shot_img_path'] != shot_img_path:
            _, file_ext = os.path.splitext(shot_img_path)
            filen_name = f"{data['id']}_img{file_ext}" if file_ext else f"{data['id']}_img.jpeg"
            abs_path, url_path = storage.gen_job_file_path(project_id, job_id, 'data', filen_name)
            if data['shot_img_path']:   # 删除旧文件
                abs_url_path_old = storage.get_abs_path(data['shot_img_path'])
                storage.mv_to_temp(abs_url_path_old)
            # 保存新文件
            tmp_abs_path_new = storage.get_abs_path(shot_img_path)
            storage.mv_file(tmp_abs_path_new, abs_path)
            mapping['shot_img_path'] = url_path

        Data.update_db(data_id, mapping)
        return ApiResponse(msg='更新成功')



class DataResourceVersionView(View):
    def get(self, request):
        project_id = request.GET.get('project_id', 0)
        if not Project.objects.filter(pk=project_id).exists():
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'invalidate project_id:{project_id}')
        items = cache.resource_version_cache.zrevrange(project_id, 0, -1)
        items = [item.decode('utf-8') for item in items]
        return ApiResponse(data={'list': items})


class ImagerResourceView(View):

    def get(self, request):
        """GET /api/image/image_resource """
        vmi = ImageResQuerySchema.model_validate(request.GET.dict())
        image_res = ImagerResource.objects.filter(**vmi.dict()).first()

        if not image_res:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='未找到image_res')

        file_path_abs = storage.get_abs_path(image_res.file_path)
        if not os.path.exists(file_path_abs):
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'image_res:{image_res.file_path} 不存在')

        response = HttpResponse(content=read_file_iter(file_path_abs))
        response['md5'] = image_res.md5
        return response

    def post(self, request):
        """POST /api/image/image_resource """
        body = orjson.loads(request.body) if request.content_type == 'application/json' else request.POST.dict()
        vmi = ImageResCreateSchema.model_validate(body)
        project_id = vmi.project_id

        image_res = ImagerResource(**vmi.model_dump(exclude={'upload_data'}, exclude_unset=True))
        # 处理文件
        upload_data_bytes = None
        if vmi.upload_data is not None:
            # upload_data_bytes = base64.b64decode(vmi.upload_data)
            upload_data_bytes = vmi.upload_data
            image_res.md5 = md5(upload_data_bytes)
            # 写临时文件
            tmp_abs_path, _ = storage.write_temp_file(upload_data_bytes)
        try:
            with transaction.atomic():
                image_res.save()
                if upload_data_bytes:
                    # example /var/www/lqa/data/media/image_res/100/20240918/image_data_1024
                    abs_path, url_path, _ = storage.gen_project_file_path(project_id, 'image_resource', f'img_res_{image_res.id}')
                    storage.mv_file(tmp_abs_path, abs_path)
                    image_res.file_path = url_path
                    image_res.save(update_fields=['file_path'])
        except IntegrityError as err:
            if err.args[0] == 1062:
                obj = ImagerResource.objects.filter(name=image_res.name, md5=image_res.md5).first()
                return ApiResponse(data={'image_res': model_to_dict(obj)}, msg='图片已存在')
            else:
                logger.error('ImageRes save err:', exc_info=err)
                return ApiResponse(ApiErrorEnum.ERROR, msg='创建失败')
        except DatabaseError as err:
            logger.error('ImageRes save err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg='创建失败')
        return ApiResponse(data={'image_res': model_to_dict(image_res)}, msg='创建成功')


class ImagerResourceMergeView(View):
    """根据SDK上传的image_resources信息，生成编辑器需要的json数据"""

    Type_Names = {"UnityEngine.UI.Image", "UnityEngine.UI.RawImage"}

    @classmethod
    def _get_image_resource_names(cls, ui_list):
        resource_names = []
        for ui_info in ui_list:
            component_datas = ui_info['ComponentDatas']
            for component_data in component_datas:
                if component_data['typeName'] in ["UnityEngine.UI.Image", "UnityEngine.UI.RawImage"]:
                    component_json = component_data.get('componentJson')
                    if not component_json:
                        continue
                    component_json = orjson.loads(component_json)
                    pic_data_name = component_json.get('picData')
                    if pic_data_name:
                        resource_names.append(pic_data_name)
        return resource_names

    @classmethod
    def merge(cls, data, all_ui_list):
        names = cls._get_image_resource_names(all_ui_list)
        project_id, resource_version = data.project_id, data.resource_version
        img_res_list = ImagerResource.objects.filter(project_id=project_id,
                                                     resource_version=resource_version, name__in=names)
        logger.info(f'image resource pre_merged: {[img_res.id for img_res in img_res_list]}')
        img_res_dict = {img_res_list.name: img_res for img_res in img_res_list}

        suc_ids = []
        suc_file_path = []
        for ui_info in all_ui_list:
            component_datas = ui_info['ComponentDatas']
            for component_data in component_datas:
                try:
                    if component_data['typeName'] in cls.Type_Names:
                        component_json = component_data.get('componentJson')
                        if not component_json:
                            continue
                        component_json = orjson.loads(component_json)
                        pic_data_name = component_json['picData']
                        img_res = img_res_dict.get(pic_data_name)
                        if img_res and img_res.file_path:
                            img_res_file_path_abs = storage.get_abs_path(img_res.file_path)
                            image_data = b''.join(bytes(chunk) for chunk in read_file_iter(img_res_file_path_abs))
                            component_json['picData'] = list(image_data)
                            component_data['componentJson'] = orjson.dumps(component_json).decode()
                            suc_ids.append(img_res.id)
                            suc_file_path.append(img_res_file_path_abs)
                except Exception as err:
                    logger.error('merge err:', exc_info=err)

        if len(suc_ids) > 0:
            logger.info(f'image resource suc merged: {suc_ids}')
            ImagerResource.update_db(suc_ids, {'is_delete': 1})
            for file_path_ in suc_file_path:
                storage.mv_to_temp(file_path_)

        return all_ui_list

    def post(self, request):
        project_id = request.POST.get('project_id', 0)
        data_id = request.POST.get('data_id', 0)

        data = Data.objects.filter(pk=data_id, project_id=project_id).first()
        if not data:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到数据data_id:{data_id}')

        file_path_abs = storage.get_abs_path(data.file_path)
        if not os.path.exists(file_path_abs):
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'数据文件不存在data_id:{data_id} {file_path_abs}')

        with open(file_path_abs, "rb") as fp:
            content_raw = fp.read()
            content = gzip.decompress(content_raw)

        content = orjson.loads(content)
        ui_json_data = orjson.loads(content['uiJson'])
        if ui_json_data:
            all_ui_list = ui_json_data['allUIList']
            new_ui_list = self.merge(data, all_ui_list)
            ui_json_data['allUIList'] = new_ui_list
            content['uiJson'] = orjson.dumps(ui_json_data).decode()
            content_raw = orjson.dumps(content).decode()

        tmp_file_path_abs, _ = storage.write_temp_file(gzip.compress(content_raw, 1))
        storage.mv_file(tmp_file_path_abs, file_path_abs)

        return ApiResponse(msg='数据合并成功')