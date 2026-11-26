import logging

import orjson
from django.views.generic import View
from django.utils.decorators import method_decorator

from libs import ApiResponse, PageView, lodash, bugtracker
from libs.util import time_ms
from libs.defs import ApiErrorEnum, RoleEnum
from libs.decorators import require_project_perm
from apps.image.models import Image
from apps.project.models import Project
from apps.project import service as proj_svr
from apps.bug.tasks import run_bug_create
from apps.bug.models import Bug
from apps.bug import service as bug_svr
from .schemas import *

logger = logging.getLogger('bug_view')

SECRET_MASK = '******'


def _project_id_param(request):
    try:
        return int(request.GET.get('project_id', 0))
    except ValueError:
        return 0


@require_project_perm()
def view_tracker_meta(request):
    """当前项目缺陷系统信息及提单下拉选项  GET /api/bug/tracker_meta?project_id= """
    project_id = _project_id_param(request)
    data = {'type': 'none', 'label': '', 'remote': False, 'enabled': True,
            'version_report_list': [], 'version_fix_list': [], 'release_id_list': [], 'error': ''}
    try:
        tracker = bugtracker.get_tracker(project_id)
        data.update(type=tracker.type, label=tracker.label, remote=tracker.remote)
        data.update(tracker.get_options())
    except bugtracker.BugTrackerError as err:
        logger.warning(f'view_tracker_meta project:{project_id} err: {err}')
        data['error'] = str(err)
    return ApiResponse(data=data)


@require_project_perm()
def view_tracker_fields(request):
    """缺陷系统中可作为“自定义提单字段”的字段及选项  GET /api/bug/tracker_fields?project_id= """
    project_id = _project_id_param(request)
    try:
        tracker = bugtracker.get_tracker(project_id)
        return ApiResponse(data={'fields': tracker.get_fields(), 'type': tracker.type})
    except bugtracker.BugTrackerError as err:
        return ApiResponse(ApiErrorEnum.ERROR, msg=str(err))


@require_project_perm(RoleEnum.ADMIN)
def view_tracker_test(request):
    """测试缺陷系统连接  POST /api/bug/tracker_test """
    vmi = BugTrackerTestSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
    config = vmi.model_dump()
    if config['api_key'] == SECRET_MASK:   # 未修改密钥，使用已保存的
        saved = proj_svr.ProjCfgService.get_bug_tracker(vmi.project_id) or {}
        config['api_key'] = saved.get('api_key', '')
    try:
        tracker = bugtracker.get_tracker(vmi.project_id, config)
        return ApiResponse(msg=tracker.test_connection())
    except bugtracker.BugTrackerError as err:
        return ApiResponse(ApiErrorEnum.ERROR, msg=str(err))


@require_project_perm()
def view_bug_build_info(request):
    """网页单个提单时，build提单内容    GET /api/bug/build_info """
    vmi = BugBuildInfoSchema.model_validate(request.GET.dict())
    image_id, project_id, bug_types = vmi.image_id, vmi.project_id, vmi.bug_types

    image = bug_svr.BugBuildBase.query_db('image', (image_id,)).get(image_id, None)
    if not image or (image and image.project_id != project_id):
        return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'未找到image_id:{image_id}，请确认是否已删除')

    bug_types_set = set([str(bug_type_) for bug_type_ in bug_types])
    use_check_detail = bug_svr.BugBuildBase.filter_check_detail(image.ai_check_detail, bug_types_set)
    if len(use_check_detail) == 0:
        logger.warning(f'view_bug_build_info {len(image.ai_check_detail)} bug_types_set:{bug_types_set}')
        return ApiResponse(ApiErrorEnum.ERROR, msg=f'没有有效的bug信息，请检查提单bug类型是否包含实际检测出的bug类型')

    project_info = bug_svr.BugBuildBase.query_db('project', (project_id,)).get(project_id, None)

    config_bill = proj_svr.ProjCfgService.get_bill(project_id)
    if not config_bill:
        return ApiResponse(ApiErrorEnum.ERROR, msg=f'未找到项目提单project_id:{project_id}，请完善提单配置')

    data = bug_svr.BugBuildBase.query_db('data', (image.data_id,)).get(image.data_id, None)
    if not data:
        return ApiResponse(ApiErrorEnum.ERROR, msg=f'未找到data_id:{image.data_id}，请确认是否已删除')

    version_report = ''
    module = None
    if bug_svr.has_custom_template(project_info):
        module = bug_svr.BugBuildBase.query_db('module', (data.module_id,)).get(data.module_id, None)
        version_report = data.resource_version
    builder = bug_svr.make_builder(image, data, config_bill, project_info, module)

    description, bug_keys = builder.build_description(use_check_detail)
    resp = {
        'title': builder.build_title_raw(use_check_detail),
        'description': description,
        'bug_keys': bug_keys,
        'current_owner': builder.build_current_owner(bug_types, default=request.user['name']),
        'title_pre': getattr(builder, 'title_pre', ''),
        'version_report': version_report
    }
    return ApiResponse(data=resp)


class BugView(View):
    @method_decorator(require_project_perm())
    def post(self, request):
        """提单个bug   POST /api/bug/entity """
        vmi = BugCreateSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        image_id = vmi.image_id

        err, ctx = bug_svr.prepare_create_bug_task_ctx_by_custom(vmi)
        if err:
            return ApiResponse(ApiErrorEnum.ERROR, msg=err)
        event = 'event.run_bug_create_0'
        ctx['_event'] = event
        try:
            task = run_bug_create.apply_async((ctx,))  # 创建bug
            logger.info(f'[{event}] task_id:{task.task_id} image_id:{image_id}')
            return ApiResponse(data={'task': task.task_id})
        except Exception as err:
            return ApiResponse(ApiErrorEnum.ERROR, msg=str(err))


class BugListView(PageView):
    Query_Fields = ('job_id', 'image_id', 'cur_id', 'title__contains')
    Output_Fields = ('id', 'project_id', 'job_id', 'image_id', 'title', 'priority', 'severity', 'reporter',
                     'current_owner', 'version_report', 'version_fix', 'release_id', 'created_at', 'updated_at',
                     'tracker', 'external_id', 'external_url', 'status', 'bill_status', 'bill_text',
                     'regress_status', 'regress_job_ids')

    def get(self, request):
        """bug列表   GET /api/bug/list """
        vmi = BugListSchema.model_validate(request.GET.dict())

        job_id, image_id, info_type, page, page_size = vmi.job_id, vmi.image_id, vmi.info_type, vmi.page, vmi.page_size
        if not (job_id or image_id):
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='job_id和image_id不能同时为空')

        param = self.make_query_params(vmi)
        resp_data = {'list': [], 'total': 0, 'page': page, 'page_size': page_size}
        t1 = time_ms()
        total, bugs = self.page_query(Bug, param, page, page_size)
        if info_type == 1 or len(bugs) == 0:
            resp_data.update(total=total, list=bugs)
            return ApiResponse(data=resp_data)

        project_id = bugs[0]['project_id']
        if not test_project_member(request.user, project_id):
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='没有该项目的权限')

        datas = [lodash.pick(bug, self.Output_Fields) for bug in bugs]
        msg = ''
        try:
            tracker = bugtracker.get_tracker(project_id)
            ids = [b['external_id'] for b in datas if b['tracker'] == tracker.type and b['external_id']]
            tracker_bugs = tracker.get_bugs(ids) if ids else {}
            for bug_ in datas:
                bug_['tracker_status'] = ''
                bug_['tracker_open'] = bug_['status'] != 'closed'
                bug_['is_delete'] = 0
                if bug_['tracker'] != tracker.type or not bug_['external_id']:
                    continue
                tracker_bug = tracker_bugs.get(bug_['external_id'])
                if not tracker_bug:
                    bug_['is_delete'] = 1      # 缺陷系统中已不存在
                    continue
                bug_['tracker_status'] = tracker_bug.status
                bug_['tracker_open'] = tracker_bug.is_open
                if tracker_bug.assignee:
                    bug_['current_owner'] = tracker_bug.assignee
                if tracker_bug.url:
                    bug_['external_url'] = tracker_bug.url
        except bugtracker.BugTrackerError as err:
            logger.warning(f'BugListView sync tracker err: {err}')
            msg = f'同步缺陷系统状态失败: {err}'
        resp_data.update(total=total, list=datas)
        return ApiResponse(data=resp_data, msg=msg or f'cost:{time_ms() - t1}')

    @method_decorator(require_project_perm())
    def post(self, request):
        """批量提交bug  POST /api/bug/list """
        vmi = BugBatchCreateSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        image_ids, job_id = vmi.image_ids, vmi.job_id

        images = Image.objects.filter(pk__in=image_ids, job_id=job_id, project_id=vmi.project_id)
        if len(images) != len(image_ids):
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='存在无效的image_ids，请检查')
        data_ids = list(map(lambda image_: image_.data_id, images))
        project_id = images[0].project_id
        project_info = Project.objects.filter(pk=project_id).values().first()
        if not project_info:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'未找到 project_info:{project_id}')
        config_bill = proj_svr.ProjCfgService.get_bill(project_id)
        data_dict = bug_svr.BugBuildBase.query_db('data', data_ids)
        staff = request.user['name']

        module_dict = {}
        if bug_svr.has_custom_template(project_info):
            module_ids = [0 if data_['module_id'] is None else data_['module_id'] for data_ in data_dict.values()]
            module_dict = bug_svr.BugBuildBase.query_db('module', module_ids)

        stat = {'success': [], 'failed': []}
        items = bug_svr.prepare_create_bug_task_ctx_by_batch(vmi, images, data_dict, config_bill, staff,
                                                             project_info, None, module_dict)
        for err_msg, ctx in items:
            if err_msg:
                stat['failed'].append((ctx['image_id'], err_msg))
            else:
                task = run_bug_create.apply_async((ctx,))  # 批量创建bug
                logger.info(f'[event.run_bug_create] at:1 task_id:{task.task_id} image_id:{ctx["image_id"]}')
                stat['success'].append(ctx['image_id'])
        code = ApiErrorEnum.ERROR if len(stat['success']) == 0 else 0
        return ApiResponse(code, msg=f'提交失败 {stat}' if code else '', data=stat)

    def patch(self, request):
        """批量更新 PATCH /api/bug/list """
        vmi = BugBatchUpdateSchema.model_validate(orjson.loads(request.body))
        project_ids = set(Bug.objects.filter(pk__in=vmi.bug_ids).values_list('project_id', flat=True))
        if not all(test_project_member(request.user, pid) for pid in project_ids):
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='没有该项目的权限')
        count = Bug.update_db(vmi.bug_ids, {'regress_status': vmi.regress_status})
        return ApiResponse(data={'count': count})


def test_project_member(user, project_id):
    from libs.decorators import test_project_user_role_by_project_id
    return test_project_user_role_by_project_id(user, project_id)


# -------- 枚举 → 中文显示（与前端 /api/system/enums 口径保持一致） --------
_SEVERITY_LABELS = dict(BugSeverityEnum.choices)
_TRACKER_LABELS = dict(BugTrackerTypeEnum.choices)


def _calc_regress_text(bug: dict) -> str:
    """与前端 bugs/crud.js human_local_bug_status 逻辑保持一致（后端拿不到 tracker 实时状态时，用 Bug.status 近似判定 closed）"""
    regress_status = bug.get('regress_status')
    is_closed = bug.get('status') == 'closed'
    if regress_status == BugRegressStatusEnum.INIT:
        return '无需回归' if is_closed else '等待回归'
    if regress_status == BugRegressStatusEnum.RUNNING:
        return '回归中'
    if regress_status == BugRegressStatusEnum.SUCCESS:
        return '回归成功'
    if regress_status == BugRegressStatusEnum.FAILED:
        return '回归失败'
    return ''


@require_project_perm()
def view_bug_export_excel(request):
    """导出当前任务下的缺陷单为 Excel  GET /api/bug/export_excel?job_id=&image_id= """
    from io import BytesIO
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from urllib.parse import quote

    try:
        vmi = BugExportSchema.model_validate(request.GET.dict())
        qs = Bug.objects.filter(job_id=vmi.job_id)
        if vmi.image_id:
            qs = qs.filter(image_id=vmi.image_id)
        bugs = list(qs.values('id', 'project_id', 'title', 'severity', 'tracker', 'current_owner',
                              'regress_status', 'status', 'external_url'))

        if not bugs:
            return ApiResponse(ApiErrorEnum.ERROR, msg='当前任务下没有可导出的缺陷单')

        # 权限校验：导出的缺陷必须都属于同一个项目，且用户是该项目成员
        project_id = bugs[0]['project_id']
        if not test_project_member(request.user, project_id):
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='没有该项目的权限')

        # 构造 Excel
        wb = Workbook()
        ws = wb.active
        ws.title = '缺陷列表'

        headers = ['标题', '严重程度', '缺陷系统', '处理人', '回归状态']
        ws.append(headers)

        header_font = Font(bold=True, color='FFFFFFFF')
        header_fill = PatternFill('solid', fgColor='FF409EFF')
        header_align = Alignment(horizontal='center', vertical='center')
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        link_font = Font(color='FF0066CC', underline='single')
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for bug in bugs:
            row_idx = ws.max_row + 1
            title_cell = ws.cell(row=row_idx, column=1, value=bug['title'] or '')
            if bug.get('external_url'):
                title_cell.hyperlink = bug['external_url']
                title_cell.font = link_font
            ws.cell(row=row_idx, column=2, value=_SEVERITY_LABELS.get(bug['severity'], ''))
            ws.cell(row=row_idx, column=3, value=_TRACKER_LABELS.get(bug['tracker'], bug['tracker'] or ''))
            ws.cell(row=row_idx, column=4, value=bug['current_owner'] or '')
            ws.cell(row=row_idx, column=5, value=_calc_regress_text(bug))
            for col in (2, 3, 4, 5):
                ws.cell(row=row_idx, column=col).alignment = center_align

        # 列宽
        widths = [60, 12, 14, 16, 12]
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + i)].width = width
        # 冻结表头
        ws.freeze_panes = 'A2'

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f'bugs_job{vmi.job_id}'
        if vmi.image_id:
            filename += f'_image{vmi.image_id}'
        filename += '.xlsx'
        resp = HttpResponse(buf.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        # RFC 5987 兼容中文文件名
        resp['Content-Disposition'] = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
        return resp
    except Exception as err:
        logger.exception(f'view_bug_export_excel err: {err}')
        return ApiResponse(ApiErrorEnum.ERROR, msg=f'导出失败: {err}')
