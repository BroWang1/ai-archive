import logging

import orjson
from django.forms.models import model_to_dict
from django.views.generic import View
from django.utils.decorators import method_decorator
from munch import Munch as AttrDict

from apps.image.models import Image
from apps.image import service as img_svr
from apps.image import tasks as img_task
from apps.data.models import Data
from apps.job.models import *
from apps.job import service as job_svr
from apps.job import runner
from apps.project import service as proj_svr
from libs import ApiResponse, PageView, cache, lodash, util
from libs.decorators import require_project_perm, test_project_user_role_by_project_id
from libs.defs import ApiErrorEnum, JobRegressionEnum, JobStatusEnum
from .schemas import *

logger = logging.getLogger('job_view')


class JobListView(PageView):
    fields_simple = ('id', 'project_id', 'creator_id', 'name', 'languages', 'status', 'reason', 'created_at',
                     'updated_at', 'parent_id', 'plan_start_at', 'plan_end_at')

    Query_Fields = ('cur_id', 'project_id', 'id', 'name__icontains', 'status', 'creator_id',
                    'created_begin_at', 'created_end_at')

    def get(self, request):
        vmi = JobListSchema.model_validate(request.GET.dict())

        project_id, info_type, page, page_size = vmi.project_id, vmi.info_type, vmi.page, vmi.page_size
        is_parent = vmi.is_parent

        param = self.make_query_params(vmi)
        if vmi.language:
            param['languages__contains'] = vmi.language
        if 'id' in param:
            job_info = Job.objects.filter(pk=param['id']).values('id', 'parent_id').first()
            if job_info is None:
                # 指定 id 的任务不存在，直接返回空列表，避免后续 None 下标访问报错
                return ApiResponse(data={'list': [], 'total': 0, 'page': page, 'page_size': page_size})
            if is_parent is not None:
                if is_parent > 0 and job_info['parent_id'] == 0:     # 搜子级
                    del param['id']
                    param['parent_id'] = job_info['id']
                elif is_parent == 0 and job_info['parent_id'] > 0:  # 搜父级
                    param['id'] = job_info['parent_id']
        else:
            if is_parent is not None:  # 筛选是否回归数据
                if is_parent == 0:
                    param['parent_id'] = 0
                else:
                    param['parent_id__gt'] = 0
        fields = self.fields_simple if info_type == 0 else ()

        total, jobs = self.page_query(Job, param, page, page_size, fields=fields)
        all_job_ids = list(map(lambda x: x['id'], jobs))

        # 统计回归任务数 {job_id: {job_id, children:[]}}
        job_regress_stat = job_svr.job_of_regress_num(all_job_ids, project_id)
        # 统计缺陷数 {job_id: {job_id, bug_num}}
        job_bugs_stat = job_svr.job_of_bug_num(all_job_ids, project_id)

        if 'id' in param and total == 1 and all_job_ids and param['id'] == all_job_ids[0]:  # id 查询时返回children信息
            children = Job.objects.filter(parent_id=param['id']).values(*fields).order_by('-id')
            jobs[0]['children'] = children
            all_job_ids.extend(list(map(lambda x: x['id'], children)))

        job_ext_info_stat = {} if info_type == 0 else \
            {o_['job_id']: o_ for o_ in JobExtra.objects.filter(pk__in=all_job_ids).values()}

        for job_ in jobs:
            _job_id = job_['id']
            job_ext_info = job_ext_info_stat.get(_job_id, {})
            job_.update(job_ext_info)
            job_['regress_num'] = len(job_regress_stat[_job_id]['children']) if _job_id in job_regress_stat else 0
            job_['bug_num'] = job_bugs_stat[_job_id]['bug_num'] if _job_id in job_bugs_stat else 0

        return ApiResponse(data={'list': jobs, 'total': total, 'page': page, 'page_size': page_size})


class JobView(View):

    @method_decorator(require_project_perm())
    def post(self, request):
        """创建普通Job"""
        body_json = getattr(request, 'body_json', None) or orjson.loads(request.body)
        vmi = JobSchema.model_validate(body_json)
        vmi_extra = JobExtraSchema.model_validate(body_json)
        vmi.plan_start_at = util.datetime_ms(vmi.plan_start_at)
        vmi.plan_end_at = util.datetime_ms(vmi.plan_end_at)

        # if vmi.plan_start_at < datetime.datetime.now() or vmi.plan_start_at > vmi.plan_end_at:
        #     return ApiResponse(ApiErrorEnum.ERROR, msg='存在无效时间，请检查')
        if vmi_extra.trans_res_repo == '' and vmi_extra.trans_res_file_path:
            return ApiResponse(ApiErrorEnum.ERROR, msg='译文资源不能为空')

        err_msg, job = job_svr.create_job_by_custom(vmi, vmi_extra, request.user)
        if err_msg:
            return ApiResponse(ApiErrorEnum.ERROR, msg=err_msg)
        return ApiResponse(data={'job': model_to_dict(job)})

    @method_decorator(require_project_perm())
    def patch(self, request):
        """修改job信息"""
        body_json = getattr(request, 'body_json', None) or orjson.loads(request.body)
        vmi = JobSchema.model_validate(body_json)
        vmi_extra = JobExtraSchema.model_validate(body_json)
        vmi.plan_start_at = util.datetime_ms(vmi.plan_start_at)
        vmi.plan_end_at = util.datetime_ms(vmi.plan_end_at)
        job_id = vmi.id
        if not Job.objects.filter(pk=job_id, project_id=vmi.project_id).exists():
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到job:{job_id}')

        job_info = vmi.model_dump(exclude={'id', 'project_id'}, exclude_unset=True)
        if len(job_info) > 0:   # 更新job信息
            Job.update_db(job_id, job_info)

        job_extra_info = vmi_extra.model_dump(exclude_unset=True)
        if len(job_extra_info) > 0:
            job_extra_old = JobExtra.objects.filter(pk=job_id).first()
            if not job_extra_old:
                return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'未找到job_extra:{job_id}')
            JobExtra.update_db(job_id, job_extra_info)     # 更新job_extra信息
            job_extra_info['job_id'] = job_id
            job_extra_info['project_id'] = vmi.project_id
            job_svr.update_job_extra_files(AttrDict(job_extra_info), job_extra_old)     # 更新job_extra管理文件信息
        return ApiResponse(msg='提交成功')

    def get(self, request):
        """任务详情 编辑器也有调用"""
        vmi = JobGetSchema.model_validate(request.GET.dict())
        job_id, progress, fields, mappings = vmi.job_id, vmi.progress, vmi.fields, vmi.mappings

        job_info = Job.objects.filter(pk=job_id).values().first()
        if job_info is None:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到job:{job_id}')
        job_info_bak = job_info

        job_ext_info = JobExtra.objects.filter(pk=job_id).values().first()
        if job_ext_info is None:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到job_extra:{job_id}')
        job_ext_info.update(job_info)
        job_info = job_ext_info

        if progress:
            all_count = len(job_svr.job_of_data_ids(job_info_bak, 1))
            ai_signed_count = len(job_svr.job_of_data_ids(job_info_bak, 4))
            job_info['progress_rate'] = f'{ai_signed_count}/{all_count}'
            job_info['all_count'] = all_count
            job_info['ai_signed_count'] = ai_signed_count

        if len(fields) > 0:
            job_info = lodash.pick(job_info, fields)
        data = {'job': job_info}

        if mappings == '1':
            _fields = ('name', 'value', 'label')
            data['mappings'] = {
                'language': [lodash.pick(o_, _fields) for o_ in proj_svr.ProjCfgService.get_sys_language()],
                'bug_type': [lodash.pick(o_, _fields) for o_ in proj_svr.ProjCfgService.get_sys_bugtype()],
                'status': [lodash.pick(o_, _fields) for o_ in util.choices_to_python(JobStatusEnum)]
            }
        return ApiResponse(data=data)


class JobActionView(View):
    """
    任务启/停/重试（还原任务由前端调用 Webhook 触发，见 apps/job/runner.py）
      start   未执行的任务：返回渲染后的 Webhook 请求，前端负责发起
      retry   重试：重新提交未完成识别的图片，并返回 Webhook 请求
      started 前端调用 Webhook 成功后回调：任务置为执行中
      stop    结束任务
    """

    def _lock_key(self, job_id):
        return f'action_job:{job_id}'

    def _check_no_ai_mark_image(self, request, job):
        """检查ai_mark_img_path为空的Image并提交ai_sign任务"""
        images = Image.objects.filter(job_id=job.id, is_latest=1, ai_mark_img_path='').values()
        if len(images) == 0:
            return

        empty_location_list = []
        for image_ in images:
            if image_['rect_location'] == '':
                empty_location_list.append(image_['id'])
        if len(empty_location_list) > 0:
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'有数据文本框集合为空请检查，image_ids: {empty_location_list}')
        logger.info(f'_check_no_ai_mark_image images_len:{len(images)}')

        current_user = request.user
        discern = job.discern
        code, ctx_list = img_svr.prepare_ai_sign_task_ctx_with_images(images, discern, current_user)
        if code == 0:
            logger.info(f'prepare_ai_sign_task_ctx_with_images2 code:{code} ctx_list_len:{len(ctx_list)}')
            event = 'event.run_ai_sign_2'
            for ctx in ctx_list:
                ctx['_event'] = event
                task = img_task.run_ai_sign.apply_async((ctx,))  # 接口图片识别
                logger.info(f'[{event}] user:{current_user["name"]} '
                            f'task_id:{task.task_id} image_id:{ctx["image_id"]} discern:{discern}')
        else:
            logger.warning(f'prepare_ai_sign_task_ctx_with_images2 code:{code}')

    @staticmethod
    def _trigger_response(job, regression, msg):
        try:
            trigger = runner.build_trigger(job, regression)
        except runner.RunnerConfigError as err:
            return ApiResponse(ApiErrorEnum.ERROR, msg=str(err))
        return ApiResponse(msg=msg, data={'job_id': job.id, 'regression': int(regression), 'trigger': trigger})

    def start_job(self, request, job):
        if job.status != JobStatusEnum.UN_RUNNING:
            return ApiResponse(ApiErrorEnum.ERROR, msg='任务已运行过，请重试任务')
        regression = JobRegressionEnum.REGRESSION if job.parent_id else JobRegressionEnum.NORMAL
        return self._trigger_response(job, regression, '请求已生成，正在调用 Webhook')

    def retry_job(self, request, job):
        def _retry_job(lock):
            api_response_ = self._check_no_ai_mark_image(request, job)
            if api_response_:
                return api_response_
            return self._trigger_response(job, JobRegressionEnum.RETRY, '请求已生成，正在调用 Webhook')

        locked, api_response = cache.try_lock(self._lock_key(job.id), _retry_job, timeout=30)
        return api_response if locked else ApiResponse(ApiErrorEnum.ERROR, msg='lock fail, 请稍后再试')

    def started_job(self, request, job, vmi):
        """Webhook 调用成功：设置任务状态为执行中"""
        def _started(lock):
            if vmi.regression != JobRegressionEnum.RETRY and \
                    Job.objects.filter(pk=job.id).values_list('status', flat=True).first() != JobStatusEnum.UN_RUNNING:
                return ApiResponse(ApiErrorEnum.ERROR, msg='任务已运行过，请重试任务')
            mapping = {'status': JobStatusEnum.RUNNING, 'build_id': vmi.build_id[:128], 'build_no': '',
                       'reason': '', 'exec_start_at': util.datetime_ms(), 'exec_end_at': None}
            Job.update_db(job.id, mapping)
            logger.info(f'[event.job.started] user:{request.user["name"]} job_id:{job.id} '
                        f'regression:{vmi.regression} build_id:{vmi.build_id}')
            return ApiResponse(msg='成功开启任务')

        locked, api_response = cache.try_lock(self._lock_key(job.id), _started, timeout=30)
        return api_response if locked else ApiResponse(ApiErrorEnum.ERROR, msg='lock fail, 请稍后再试')

    def stop_job(self, request, job):
        """只需要改变任务状态"""
        def _stop_job(lock):
            Job.update_db(job.id, {'status': JobStatusEnum.COMPLETED, 'exec_end_at': util.datetime_ms()})
            return ApiResponse(msg=f"成功关闭任务")

        locked, api_response = cache.try_lock(self._lock_key(job.id), _stop_job, timeout=30)
        return api_response if locked else ApiResponse(ApiErrorEnum.ERROR, msg='lock fail, 请稍后再试')

    def post(self, request):
        vmi = JobActionSchema.model_validate(orjson.loads(request.body))
        action, job_id = vmi.action, vmi.job_id

        job = Job.objects.filter(pk=job_id).first()
        if not job:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'未找到job:{job_id}')
        if not test_project_user_role_by_project_id(request.user, job.project_id):
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='没有该项目的权限')

        logger.info(f'[event.job.action] user:{request.user["name"]} action:{action} job_id:{job_id}')

        if action == 'start':
            return self.start_job(request, job)
        elif action == 'retry':
            return self.retry_job(request, job)
        elif action == 'started':
            return self.started_job(request, job, vmi)
        elif action == 'stop':
            return self.stop_job(request, job)


class JobBugRegressView(View):
    def post(self, request):
        """创建bug回归任务（创建后由前端调用 /api/job/action start 触发执行）"""
        body = orjson.loads(request.body)
        vmi = JobBugRegressSchema.model_validate(body)
        vmi_extra = JobExtraSchema.model_validate(body)

        err_msg, job = job_svr.create_job_by_regress_bugs(vmi, vmi_extra, request.user)
        if err_msg:
            return ApiResponse(ApiErrorEnum.ERROR, msg=err_msg)
        return ApiResponse(data={'job': model_to_dict(job)})


class JobDatasView(View):
    def get(self, request):
        """编辑器调用 获取任务datas"""
        vmi = JobDatasSchema.model_validate(request.GET.dict())
        job_id, regression, language, count, min_id = vmi.job_id, vmi.regression, vmi.language, vmi.count, vmi.minID
        module_ids, iteration, use_cache = vmi.module_ids, vmi.iteration, vmi.use_cache

        job = Job.objects.filter(pk=job_id).values('id', 'languages', 'parent_id', 'regression_bug_ids', 'data_ids').first()
        if not job:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='f未找到job:{job_id}')
        if language is not None and language not in job['languages']:
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'非法的language: {language}')

        if use_cache:
            data_ids = job_svr.job_of_data_ids_query(job_id).job_of_data_ids(job, 3, language, module_ids,
                                                                             iteration=iteration)
        else:
            data_ids = job_svr.job_of_data_ids(job, 3, language, module_ids, iteration=iteration)
        order_data_ids = sorted(data_ids)
        ret_data_ids = []
        if min_id > 0:
            for data_id in order_data_ids:
                if len(ret_data_ids) >= count:
                    break
                if data_id > min_id:
                    ret_data_ids.append(data_id)
        else:
            ret_data_ids = order_data_ids[:count]
        datas = Data.query_batch_by_pks(ret_data_ids, ('id', 'file_path', 'module_id'))
        data = {'bug_ids': [], 'datas': datas}
        if regression == JobRegressionEnum.REGRESSION:   # 回归时获取的数据
            data['bug_ids'] = job['regression_bug_ids']
        return ApiResponse(data=data)


class JobDeviceView(View):
    """这个view主要处理 编辑器还原情况上报 """
    def post(self, request):
        vmi = JobDeviceCreateSchema.model_validate(orjson.loads(request.body))
        job_id, execute_pc, language = vmi.job_id, vmi.execute_pc, vmi.language

        job_dev = JobDevice.objects.filter(job_id=job_id, execute_pc=execute_pc, language=language).values('id').first()
        if job_dev:  # 更新
            mapping = vmi.model_dump(exclude_unset=True)
            JobDevice.update_db(job_dev['id'], mapping)
        else:   # 创建
            JobDevice(**vmi.model_dump(exclude_unset=True)).save()
        return ApiResponse()

    def get(self, request):
        job_id = int(request.GET.get('job_id', 0))
        jds = JobDevice.objects.filter(job_id=job_id).order_by('updated_at').values()
        proj_svr.patch_language_code(jds)
        return ApiResponse(data={'list': jds})


def view_job_progress(request):
    job_id = int(request.GET.get('job_id', 0))

    job = Job.objects.filter(pk=job_id).values('id', 'languages', 'data_ids', 'parent_id').first()
    if not job:
        return ApiResponse(ApiErrorEnum.NOT_EXIST, f'job:{job_id}不存在')

    all_data_count = job_svr.job_of_data_ids(job, 1, counter=True)
    all_imaged_count = job_svr.job_of_data_ids(job, 2, counter=True)

    languges = []

    for language in job['languages']:
        imaged_count = job_svr.job_of_data_ids(job, 2, language, counter=True)
        languges.append({
            'language': language,
            'imaged_count': imaged_count,
            'imaged_count_per': f'{int(imaged_count / all_data_count * 100) if all_data_count > 0 else 0}%'
        })
    return ApiResponse(data={
        'all_data_count': all_data_count,
        'all_imaged_count': all_imaged_count,
        'languges': languges
    })
