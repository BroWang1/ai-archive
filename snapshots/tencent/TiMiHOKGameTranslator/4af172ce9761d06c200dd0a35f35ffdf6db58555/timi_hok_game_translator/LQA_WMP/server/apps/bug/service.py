import os

import orjson
from munch import munchify, Munch as AttrDict
from django.template.loader import render_to_string, TemplateDoesNotExist
from django.template.loader import get_template

from .schemas import BugCreateSchema
from apps.project import service as proj_svr
from apps.data.models import Data
from apps.image.models import Image
from apps.job.models import Job
from apps.user.models import User
from apps.project.models import Module, Project
from apps.bug.models import Bug
from libs import TaskBase, lodash, storage, bugtracker
from libs.defs import BugBillStatusEnum, BugRegressStatusEnum
from libs.util import coordinate_trans, datetime_ms


class BugBuildBase(object):
    image_fields = ('id', 'project_id', 'data_id', 'ai_bug_types', 'ai_check_detail', 'language', 'file_name', 'job_id',
                    'size', 'rect_location')
    data_fields = ('id', 'project_id', 'job_id', 'module_id', 'device', 'resource_version')
    project_fields = ('id', 'code', 'name')

    BUG_NAMES = {'1': '漏译', '2': '超框', '3': '漏key', '4': '标准框重叠', '5': '错译', '7': '非标准框',
                 '8': '错译(规则)', '9': '行高百分比', '10': '字体太小'}

    def __init__(self, image, data, config_bill):
        self.image = image
        self.data = data
        self.config_bill = config_bill

    @classmethod
    def filter_check_detail(cls, check_detail, allow_bug_types_set=None):
        """根据 allow_bug_types_set 过滤需要用到的 check_detail"""
        if isinstance(check_detail, str):
            check_detail = orjson.loads(check_detail)
        detail = {}
        if not allow_bug_types_set or len(allow_bug_types_set) == 0:
            allow_bug_types_set = set(list(cls.BUG_NAMES.keys()))
        else:
            allow_bug_types_set = set([str(i) for i in allow_bug_types_set])
        for k, v in check_detail.items():
            if k in allow_bug_types_set:
                detail[k] = v
        return detail

    @classmethod
    def query_db(cls, cate, pks, fields=None, mapping=True, attrify=True):
        """bug build 查表时从这里查 精确返回字段"""
        if len(pks) == 0:
            return {} if mapping else []
        if cate == 'image':
            model, fields_ = Image, fields if fields else cls.image_fields
        elif cate == 'data':
            model, fields_ = Data, fields if fields else cls.data_fields
        elif cate == 'module':
            model, fields_ = Module, {} if mapping else []
        elif cate == 'project':
            model, fields_ = Project, fields if fields else cls.project_fields
        else:
            raise Exception(f'not supported cate: {cate}')

        datas = model.objects.filter(pk__in=pks).values(*fields_)
        if mapping:
            return {d_['id']: AttrDict(d_) if attrify else d_ for d_ in datas}
        else:
            return [AttrDict(d_) if attrify else d_ for d_ in datas]

    def build_current_owner(self, req_bug_types=None, default=''):
        """
        bug 处理人
        :param req_bug_types:  实际提单时的bug_types
        :param default:
        :return: user_names
        """
        image, config_bill, data = self.image, self.config_bill, self.data

        if config_bill is None:
            return default
        config_bill = munchify(config_bill)
        if not (config_bill.bug_type_enable or config_bill.language_enable or config_bill.module_enable):  # 如果全部关闭返回默认
            return default
        user_name_set = set()

        ai_bug_types, language, module_id = image.ai_bug_types, image.language, data.module_id if data else 0
        if req_bug_types is None:
            req_bug_types = ai_bug_types

        for bill_item in config_bill.rows:
            if bill_item.enable:
                if config_bill.bug_type_enable and bill_item.get('bug_type', 0) not in req_bug_types:
                    continue
                if config_bill.language_enable and bill_item.get('language', 0) != language:
                    continue
                if config_bill.module_enable and bill_item.get('module', 0) != module_id:
                    continue
                user_name_set.update(bill_item.user_names)
        if len(user_name_set) == 0:
            return default
        return ','.join(user_name_set)


class BugBuildComm(BugBuildBase):
    """通用描述生成器。description_tpl 最终渲染后记得replace掉\n"""

    description_tpl = """
<p>
<span>【测试机型】：%s</span><br>
<span>【分辨率】：%s</span><br>
<span>【图片ID】：%s</span><br>
<span>【图片名称】：%s</span><br>
<span>【任务ID】：%s</span><br>
<span>【发生时间】：%s</span><br>
<span>【操作步骤】</span><br>
<span style="margin-left: 2em;">%s</span><br>
<br>
<span>【预期结果】</span><br>
<span style="margin-left: 2em;">%s</span><br>
<br>
<span>【实际结果】</span><br>
%s
<p>
    """

    def __init__(self, image, data, config_bill):
        super(BugBuildComm, self).__init__(image, data, config_bill)

    def build_title(self, use_check_detail, version_report=''):
        parts = self.image.file_name.split('_')
        region = parts[-2] if len(parts) >= 2 else ''
        prefix = '-'.join([p for p in (version_report.split('-')[0], region) if p])
        text_str = self.build_title_raw(use_check_detail)
        return f"【{prefix}】【LQA】-{text_str}" if prefix else f"【LQA】-{text_str}"

    def build_title_raw(self, use_check_detail):
        '''"英/日/俄/法" "模块1" 漏译/漏key/标准框重叠 key:"" '''
        text_list = []
        data1 = use_check_detail.get('1', [])  # 漏译
        data2 = use_check_detail.get('2', {})  # 超框
        data3 = use_check_detail.get('3', [])  # 漏key
        data4 = use_check_detail.get('4', [])  # 标准框重叠
        # 漏译
        if len(data1) > 0:
            text_list.append("漏译")
        # 超框
        data20 = data2.get("0", [])  # 文本超文本框
        data21 = data2.get("1", [])  # 文本超图像框
        if len(data20) > 0:
            text_list.append("文本超文本框")
        if len(data21) > 0:
            text_list.append("文本超图像框")
        if len(data3) > 0:
            text_list.append("漏key")
        if len(data4) > 0:
            text_list.append("标准框重叠")
        # 解决bug标题超长导致提单失败，方案只给一个md5和bug类型
        if "--" in str(use_check_detail):
            text_str = 'MD5:' + str(use_check_detail).split("--")[1].split(",")[0] + '等多处{}问题'.format(text_list)
        else:
            start_index = str(use_check_detail).find('[')
            if start_index != -1:
                text_str = str(use_check_detail)[start_index:start_index + 20] + '、'.join(text_list)
            else:
                text_str = str(use_check_detail)[:10] + '、'.join(text_list)
        return text_str

    def build_description(self, check_rect_detail, allow_lf=True):
        """buid_description"""
        image, data = self.image, self.data
        phone_type = data.device.get('phone_type', '') if data and data.device else ''
        screen_w = data.device.get('screen_w', 0) if data and data.device else 0
        screen_h = data.device.get('screen_h', 0) if data and data.device else 0
        resolution = f'{screen_w}x{screen_h}' if screen_w and screen_h else ''
        image_id, image_name, job_id = image.id, image.file_name, image.job_id
        setp = '通过图像识别判断页面是否存在漏译，漏key，超框问题'
        expected_results = "页面是不存在漏译，漏key，超框问题"

        bug_descs, bug_keys = self.build_bug_items(check_rect_detail)
        actual_results = bug_descs
        description = self.description_tpl % (phone_type, resolution, image_id, image_name, job_id, datetime_ms(), setp,
                                             expected_results, actual_results)
        return description.replace('\n', ''), bug_keys

    def _build_bug_item(self, bugs, topic=''):
        key_desc_list, key_list = [], []
        for bug in bugs:
            key, rect = (bug[0], bug[1]) if isinstance(bug[0], str) else (bug[1], bug[0])
            key_desc = f'页面中【{key}】存在 {topic} 问题'
            key_list.append(key)
            key_desc_list.append(key_desc)
        return key_desc_list, key_list

    def build_bug_items(self, use_check_detail):
        if len(use_check_detail) == 0:
            return '', []
        bugs_item_1 = use_check_detail.get('1', []), '漏译'  # 漏译
        bugs_item_20 = use_check_detail.get('2', {}).get("0", []), '文本超文本框'  # 超框:文本超文本框
        bugs_item_21 = use_check_detail.get('2', {}).get("1", []), '文本超图像框'  # 超框:文本超图像框
        bugs_item_3 = use_check_detail.get('3', []), '漏key'  # 漏key
        bugs_item_4 = use_check_detail.get('4', []), '标准框重叠'  # 标准框重叠
        bug_items = (bugs_item_1, bugs_item_20, bugs_item_21, bugs_item_3, bugs_item_4)
        rets = list(map(lambda item: self._build_bug_item(item[0], item[1]), bug_items))
        bug_keys = {'1': rets[0][1], '2': {'0': rets[1][1], '1': rets[2][1]}, '3': rets[3][1], '4': rets[4][1]}
        description = ''
        for i, desc in enumerate(rets[0][0] + rets[1][0] + rets[2][0] + rets[3][0] + rets[4][0]):
            description += f'<span style="margin-left: 2em;">{i + 1}.{desc}</span><br>'
        return description, bug_keys


class BugBuildTpl(BugBuildBase):
    """
    基于模板的描述生成器：模板位于 apps/bug/templates/spec2/<项目代号小写>/，
    包含 report.tpl / bug_info.tpl / test_env.tpl，可参考 spec2/normal 自定义。
    """

    def __init__(self, image, data, config_bill, module, config_language, project_info):
        super(BugBuildTpl, self).__init__(image, data, config_bill)
        self.module = module
        self.config_language = config_language
        self.project_info = project_info

        self.title_pre = f'【{project_info["name"]}】#本地化#'

    def build_title(self, use_check_detail, version_report=''):
        """构建title"""
        text_str = self.build_title_raw(use_check_detail)
        return f"{self.title_pre} {text_str}"

    def build_title_raw(self, use_check_detail):
        """
        构建title 动态部分
        example: "英/日/俄/法" "模块1" 漏译/漏key/标准框重叠 key:""
        need config_language,module,image,job
        """
        language_text = ''
        if self.config_language:
            for config_lan in self.config_language:
                if self.image.language == config_lan['value']:
                    language_text = config_lan.get('custom_label', '') or config_lan.get('label', '')
        module_text = self.module.name if self.module else ''
        bug_type_names = set()
        bug_text_keys = set()
        ret = self._build_bug_items(use_check_detail)
        for bug_key_str in ret['infos']:
            if bug_key_str == '2':
                for sub_bug_key_str in ret['infos'][bug_key_str]:
                    infos = ret['infos'][bug_key_str][sub_bug_key_str]
                    if len(infos) > 0:
                        bug_type_names.add(self.BUG_NAMES['2'])
                    for info in infos:
                        text_key, _, _, _, _ = info
                        if text_key:
                            bug_text_keys.add(text_key)
            else:
                infos = ret['infos'][bug_key_str]
                if len(infos) > 0:
                    bug_type_names.add(self.BUG_NAMES[bug_key_str])
                for info in infos:
                    text_key, _, _, _, _ = info
                    if text_key:
                        bug_text_keys.add(text_key)

        bug_type_name_text = '/'.join(bug_type_names)
        bug_key_text = ','.join(bug_text_keys)
        return f'"{language_text}" "{module_text}" {bug_type_name_text} key:"{bug_key_text}"'[:100]

    def build_description(self, use_check_detail, allow_lf=True):
        """need image data"""
        bug_info, bug_keys = self.make_bug_items_context(use_check_detail)
        ctx = {
            'test_env': {'version': self.data.resource_version},
            'bug_info': bug_info
        }
        content = self._render_to_string('report.tpl', ctx, allow_lf)
        return content, bug_keys

    def _matched_rect_extern_info(self, rect):
        """need image"""
        text_key, parent_widget, text_str, source_string, widget_name = '', '', '', '', ''
        image = self.image
        if not (image and hasattr(image, 'size')):
            return text_key, text_str, source_string, parent_widget, widget_name
        rect_locations_dict = getattr(image, 'rect_locations_dict', None)
        if not rect_locations_dict:
            height = int(image.size.split(',')[1])
            rect_locations = orjson.loads(image.rect_location).get('text', [])
            rect_locations_dict = {}
            for rect_location_text in rect_locations:
                _, rect_ = coordinate_trans(rect_location_text['corners'], height)
                rect_location_text['rect'] = rect_
                rect_locations_dict[rect_location_text['rect']] = rect_location_text
            setattr(image, 'rect_locations_dict', rect_locations_dict)
        rect_location = image.rect_locations_dict.get(tuple(rect), None)
        if rect_location:
            text_key = rect_location.get('TextKey', '')
            text_str = rect_location.get('textStr', '')
            source_string = rect_location.get('SourceString', '')
            parent_widget = rect_location.get('ParentWidget', '')
            widget_name = rect_location.get('WidgetName', '')
        return text_key, text_str, source_string, parent_widget, widget_name

    def _build_bug_item(self, bugs, bug_type):
        """need image"""
        infos, key_list = [], []

        def __get_rect_extern_info(bug_):
            key, rect = (bug_[0], bug_[1]) if isinstance(bug_[0], str) else (bug_[1], bug_[0])
            info = self._matched_rect_extern_info(rect)
            key_list.append(key)
            infos.append(info)

        for bug in bugs:
            if bug_type == '4':
                for bug1 in bug:
                    __get_rect_extern_info(bug1)
            else:
                __get_rect_extern_info(bug)
        return infos, key_list

    def _build_bug_items(self, use_check_detail):
        bugs_item_1 = use_check_detail.get('1', []), '1'  # 漏译
        bugs_item_20 = use_check_detail.get('2', {}).get("0", []), '20'  # 超框:文本超文本框
        bugs_item_21 = use_check_detail.get('2', {}).get("1", []), '21'  # 超框:文本超图像框
        bugs_item_3 = use_check_detail.get('3', []), '3'  # 漏key
        bugs_item_4 = use_check_detail.get('4', []), '4'  # 标准框重叠
        bugs_item_5 = use_check_detail.get('5', []), '5'  # 错译
        bugs_item_7 = use_check_detail.get('7', []), '7'  # 非标准框
        bugs_item_8 = use_check_detail.get('8', []), '8'  # 错译(规则)
        bugs_item_9 = use_check_detail.get('9', []), '9'  # 行高百分比
        bugs_item_10 = use_check_detail.get('10', []), '10'  # 字体太小
        bug_items = (bugs_item_1, bugs_item_20, bugs_item_21, bugs_item_3, bugs_item_4, bugs_item_5, bugs_item_7,
                     bugs_item_8, bugs_item_9, bugs_item_10)
        rets = list(map(lambda item: self._build_bug_item(item[0], item[1]), bug_items))
        bug_keys = {'1': rets[0][1], '2': {'0': rets[1][1], '1': rets[2][1]}, '3': rets[3][1], '4': rets[4][1],
                    '5': rets[5][1], '7': rets[6][1], '8': rets[7][1], '9': rets[8][1], '10': rets[9][1]}
        infos = {'1': rets[0][0], '2': {'0': rets[1][0], '1': rets[2][0]}, '3': rets[3][0], '4': rets[4][0],
                 '5': rets[5][0], '7': rets[6][0], '8': rets[7][0], '9': rets[8][0], '10': rets[9][0]}
        return {'infos': infos, 'bug_keys': bug_keys}

    def build_bug_items(self, use_check_detail):
        bug_info, bug_keys = self.make_bug_items_context(use_check_detail)
        content = self._render_to_string('bug_info.tpl', {'bug_info': bug_info}, False)
        return content, bug_keys

    def make_bug_items_context(self, use_check_detail):
        context = {}
        ret = self._build_bug_items(use_check_detail)
        bug_keys, infos = ret['bug_keys'], ret['infos']
        all_infos = (infos['1'] + infos['2']['0'] + infos['2']['1'] + infos['3'] + infos['4'] + infos['5'] + infos['7']
                     + infos['8'] + infos['9'] + infos['10'])

        context['bug_type_names'] = [self.BUG_NAMES[but_type_str] for but_type_str in use_check_detail]
        items = ([], [], [], [], [])
        distinct_dict = {}
        for _, info in enumerate(all_infos):
            # text_key, text_str, source_string, parent_widget, widget_names = info  # 顺序不要改动
            if not info[1]:  # 去空字符串
                continue
            unin_key = f'{info[0]}_{info[1]}'
            if unin_key in distinct_dict:  # 去重
                continue
            distinct_dict[unin_key] = 1
            for j, ele_str in enumerate(info):
                items[j].append(ele_str)
        context['text_keys'] = items[0]
        context['text_strs'] = items[1]
        context['source_strings'] = items[2]
        context['parent_widgets'] = items[3]
        context['widget_names'] = items[4]
        return context, bug_keys

    def _render_to_string(self, tpl, ctx, allow_lf=True):
        spec_name = self.project_info['code'].lower()
        try:
            content = render_to_string(f'spec2/{spec_name}/{tpl}', ctx)
        except TemplateDoesNotExist:
            content = render_to_string(f'spec2/normal/{tpl}', ctx)
        if not allow_lf:
            content = content.replace('\n', '')
        return content


def has_custom_template(project_info) -> bool:
    """项目是否在 templates/spec2/<code>/ 下提供了自定义提单模板"""
    if not project_info:
        return False
    try:
        get_template(f'spec2/{project_info["code"].lower()}/report.tpl')
        return True
    except TemplateDoesNotExist:
        return False


def make_builder(image, data, config_bill, project_info, module=None, config_language=None):
    """有自定义模板的项目使用模板生成器，否则使用通用生成器"""
    if has_custom_template(project_info):
        if config_language is None:
            config_language = proj_svr.ProjCfgService.get_language(project_info['id'])
        return BugBuildTpl(image, data, config_bill, module, config_language, project_info)
    return BugBuildComm(image, data, config_bill)


def _make_payload(bug: Bug, custom_fields) -> bugtracker.BugPayload:
    return bugtracker.BugPayload(
        lqa_bug_id=bug.id,
        title=bug.title,
        description=bug.description,
        priority=int(bug.priority or 0),
        severity=int(bug.severity or 0),
        version_report=bug.version_report,
        version_fix=bug.version_fix,
        release_id=bug.release_id,
        assignees=[n.strip() for n in (bug.current_owner or '').split(',') if n.strip()],
        reporter=bug.reporter,
        custom_fields=custom_fields or {},
    )


class CreateBugTask(TaskBase):
    """创建bug：先写入平台数据库，再提交到项目配置的缺陷系统。可前后台执行"""
    def run(self):
        self.logger.info(f'CreateBugTask.run ctx:{orjson.dumps(self.ctx).decode()}')
        bug_create_body = BugCreateSchema.model_validate(self.ctx).model_dump(exclude_unset=True)
        custom_fields = bug_create_body.pop('custom_fields', None)
        project_id = bug_create_body['project_id']

        try:
            tracker = bugtracker.get_tracker(project_id)
        except bugtracker.BugTrackerError as err:
            self.logger.error(f'get_tracker project:{project_id} err: {err}')
            return str(err), None

        bug_create_body['bill_status'] = BugBillStatusEnum.INIT
        bug_create_body['tracker'] = tracker.type
        bug = Bug.objects.create(**bug_create_body)
        self.logger.info(f'[event.bug.add] bug_id:{bug.id} image_id:{bug.image_id} tracker:{tracker.type}')

        # 只上传还原截图（不上传检测结果图）
        attachments = [storage.get_abs_path(bug.raw_image_path)] if bug.raw_image_path else []
        attachments = [p for p in attachments if os.path.exists(p)]
        mapping = {'bill_text': ''}
        try:
            external_id = tracker.create_bug(_make_payload(bug, custom_fields), attachments)
            mapping.update(external_id=external_id, external_url=tracker.bug_url(external_id),
                           bill_status=BugBillStatusEnum.SUCCESS)
        except Exception as err:
            self.logger.error(f'tracker create_bug bug_id:{bug.id} err: {err}', exc_info=err)
            mapping.update(bill_status=BugBillStatusEnum.FAILED, bill_text=str(err)[:2000])
        Bug.update_db(bug.id, mapping)
        self.logger.info(f'[event.tracker_bug.add] bug_id:{bug.id} external_id:{mapping.get("external_id")}')
        return mapping['bill_text'], bug


def prepare_create_bug_task_ctx_by_custom(vmi):
    """人工提单"""
    return '', vmi.model_dump()


def _bug_build_info_auto(bug_body, req_bug_types_set, image, data, config_bill, staff,
                         project_info, config_language, module):
    """自动提单
    return err_msg, bug_body
    """
    # 兜底：图片未完成 AI 识别 / 抽帧失败 / AI 返回异常时，ai_check_detail 可能为空字符串或非法 JSON
    # 直接 orjson.loads('') 会抛 "Input is a zero-length, empty document"，前端只能看到英文异常，
    # 这里转换成友好的中文错误，调用方会把该 image_id 放进 failed 列表并原样展示给用户。
    raw_detail = image.ai_check_detail or ''
    if not raw_detail.strip():
        return '图片未完成 AI 识别或抽帧失败，无法提单', {'image_id': image.id}
    try:
        ai_check_detail = orjson.loads(raw_detail)
    except (ValueError, orjson.JSONDecodeError) as err:
        return f'图片 AI 识别结果不是合法 JSON，无法提单: {err}', {'image_id': image.id}
    use_check_detail = BugBuildBase.filter_check_detail(ai_check_detail, req_bug_types_set)
    if len(use_check_detail) == 0:
        return f'use_check_detail is empty', {'image_id': image.id}

    builder = make_builder(image, data, config_bill, project_info, module, config_language)
    title = builder.build_title(use_check_detail, bug_body.get('version_report', ''))

    current_owner = builder.build_current_owner(use_check_detail, staff)
    description, bug_keys = builder.build_description(use_check_detail, False)
    bug_body.update({
        'project_id': image.project_id,
        'image_id': image.id,
        'title': title,
        'description': description,
        'current_owner': current_owner,
        'raw_image_path': image.file_path,
        'ai_image_path': image.ai_mark_img_path,
        'key_in_bug': orjson.dumps(bug_keys).decode()
    })
    BugCreateSchema.model_validate(bug_body)
    return '', bug_body


def prepare_create_bug_task_ctx_by_batch(vmi, images, data_dict, config_bill, staff,
                                         project_info, config_language, module_dict):
    """自动提单:批量提单"""
    req_bug_types_set = set(vmi.bug_types)  # 希望提单的bug类型
    bug_bodys = []
    for image_ in images:
        try:
            data = data_dict.get(image_.data_id, None)
            if not data:
                bug_bodys.append((f'not found data:{image_.data_id}', {'image_id': image_.id}))
                continue
            module = module_dict.get(data.module_id, None)
            bug_body = vmi.model_dump(include={'job_id', 'version_report', 'release_id',
                                               'version_fix', 'severity', 'priority', 'reporter'})
            if bug_body['job_id'] == 0:
                bug_body['job_id'] = image_.job_id
            if not bug_body.get('reporter'):
                bug_body['reporter'] = staff
            bug_info = _bug_build_info_auto(bug_body, req_bug_types_set, image_, data, config_bill, staff,
                                            project_info, config_language, module)
            bug_bodys.append(bug_info)
        except Exception as err:
            bug_bodys.append((str(err), {'image_id': image_.id}))
    return bug_bodys


def prepare_create_bug_task_ctx_by_ai_sign(image_id):
    """自动提单:ai识别后提单
    return err_msg, bug_body
    """
    image = Image.objects.filter(pk=image_id).first()
    data = BugBuildBase.query_db('data', (image.data_id,)).get(image.data_id, None)
    if not data:
        return f'not fund data: {image.data_id}', {}
    job = Job.objects.filter(pk=image.job_id).first()
    user = User.objects.filter(pk=job.creator_id).values().first()
    project_info = BugBuildBase.query_db('project', (image.project_id, )).get(image.project_id, None)
    config_bill = proj_svr.ProjCfgService.get_bill(image.project_id)

    bug_body = lodash.pick(image, ['project_id', 'job_id'])
    body2 = lodash.pick(job, ['version_report', 'release_id', 'version_fix', 'severity', 'priority'])
    bug_body.update(body2)
    bug_body['reporter'] = user['name']     # 由于ai识别提交接口无法知道用户是谁，所以使用job创建者替代

    req_bug_types_set = set(job.bill_bug_types)
    module = None
    if has_custom_template(project_info) and data.module_id:
        module = BugBuildBase.query_db('module', (data.module_id,)).get(data.module_id, None)
    return _bug_build_info_auto(bug_body, req_bug_types_set, image, data, config_bill, user['name'],
                                project_info, None, module)


class UpdateBugByRegressedImageService(TaskBase):
    """场景：bug回归任务，在编辑器还原完成后，上传图片，然后更新平台与缺陷系统中的缺陷状态"""

    def _get_open_bugs(self, tracker, job_id, image_id, req_bug_ids):
        """获取到所有需要回归 且 未关闭的bug信息 [(local_bug_dict, TrackerBug)]"""
        bugs = list(Bug.objects.filter(job_id=job_id, image_id=image_id, pk__in=req_bug_ids).values())
        if len(bugs) == 0:
            self.logger.warning(f'_get_open_bugs empty, req_bug_ids:{req_bug_ids}')
            return []
        valid_bugs = []
        for bug in bugs:
            if bug['tracker'] != tracker.type or not bug['external_id']:
                self.logger.warning(f'bug:{bug["id"]} tracker:{bug["tracker"]} external_id:{bug["external_id"]} '
                                    f'与当前缺陷系统({tracker.type})不一致或未成功提单，跳过')
                Bug.update_db(bug['id'], {'regress_status': BugRegressStatusEnum.FAILED})
                continue
            valid_bugs.append(bug)
        tracker_bugs = tracker.get_bugs([b['external_id'] for b in valid_bugs])
        ret = []
        for bug in valid_bugs:
            tracker_bug = tracker_bugs.get(bug['external_id'])
            if tracker_bug and tracker_bug.is_open:
                ret.append((bug, tracker_bug))
        return ret

    def run(self):
        """
            1.查找到父任务的image
            2.根据image找到关联的bug列表（一个image可以提交多个bug单）
            3.根据当前最新bug_types和bug的bug_types对比，是否关闭还是重新打开缺陷
            image_id: 当前还原任务的image_id
            bug_ids: 编辑器调用上传图片时传入
        """
        image_id, bug_ids = self.ctx['image_id'], self.ctx['bug_ids']
        self.logger.info(f'UpdateBugByRegressedImageService.run image_id:{image_id} bug_ids:{bug_ids}')

        stats = []
        image = Image.objects.filter(pk=image_id).first()
        job_info = Job.objects.filter(pk=image.job_id).values('id', 'parent_id').first()
        job_id, job_parent_id = job_info['id'], job_info['parent_id']
        if job_parent_id == 0:
            err_msg = f'job:{job_id} parend_id is 0'
            self.logger.error(err_msg)
            return 1, err_msg, stats
        if not Job.objects.filter(pk=job_parent_id).exists():
            err_msg = f'job_parent:{job_parent_id} not exist'
            self.logger.error(err_msg)
            return 2, err_msg, stats
        image_parent = Image.objects.filter(job_id=job_parent_id, data_id=image.data_id, language=image.language)\
            .first()
        if image_parent is None:
            err_msg = f'image_parent not found, job_id:{job_parent_id} data_id:{image.data_id}'
            self.logger.error(err_msg)
            return 3, err_msg, stats

        tracker = bugtracker.get_tracker(image.project_id)
        open_bugs = self._get_open_bugs(tracker, job_parent_id, image_parent.id, bug_ids)
        if len(open_bugs) == 0:
            self.logger.warning(f'opened bugs is empty, update_db bug_ids:{bug_ids}')
            Bug.objects.filter(pk__in=bug_ids, regress_status=BugRegressStatusEnum.RUNNING)\
                .update(regress_status=BugRegressStatusEnum.SUCCESS, updated_at=datetime_ms())
            return 0, 'opened bugs is empty', stats

        req_bug_types_set = set(image.ai_bug_types)
        bugs_reopen = []
        bugs_closed = []
        for bug, tracker_bug in open_bugs:
            key_in_bug = orjson.loads(bug['key_in_bug']) if bug['key_in_bug'] else {}
            bug_types_set = set(map(int, key_in_bug.keys()))
            merged_bug_types_set = req_bug_types_set.intersection(bug_types_set)
            bug['tracker_bug'] = tracker_bug
            if len(merged_bug_types_set) == 0:
                bugs_closed.append(bug)
            else:
                bug['merged_bug_types_set'] = merged_bug_types_set
                bugs_reopen.append(bug)

        self._update_bugs_closed(tracker, bugs_closed, stats)

        project_info = Project.objects.filter(pk=image.project_id).values().first()
        self._update_bugs_reopen(tracker, bugs_reopen, image, project_info, stats)

        return 0, '', stats

    def _update_bugs_closed(self, tracker, bugs, stats):
        for bug in bugs:
            external_id = bug['external_id']
            try:
                tracker.close_bug(external_id, '本地化工具回归验证通过，自动关闭')
                Bug.update_db(bug['id'], {'regress_status': BugRegressStatusEnum.SUCCESS, 'status': 'closed'})
                stats.append(('close', bug['id'], external_id, 'suc'))
            except Exception as err:
                self.logger.error(f'_update_bugs_closed bug_id:{bug["id"]} err: {err}')
                Bug.update_db(bug['id'], {'regress_status': BugRegressStatusEnum.FAILED})
                stats.append(('close', bug['id'], external_id, 'fail'))

    def _update_bugs_reopen(self, tracker, bugs, image, project_info, stats):
        if len(bugs) == 0:
            return
        image_ids = list(map(lambda bug_: bug_['image_id'], bugs))
        image_old_map = BugBuildBase.query_db('image', image_ids)

        for bug in bugs:
            external_id = bug['external_id']
            try:
                self._update_bug_reopen(tracker, bug, image, project_info, image_old_map)
                Bug.update_db(bug['id'], {'regress_status': BugRegressStatusEnum.SUCCESS, 'status': 'open'})
                stats.append(('reopen', bug['id'], external_id, 'suc'))
            except Exception as err:
                self.logger.error(f'_update_bugs_reopen bug_id:{bug["id"]} err: {err}')
                Bug.update_db(bug['id'], {'regress_status': BugRegressStatusEnum.FAILED})
                stats.append(('reopen', bug['id'], external_id, 'fail'))

    def _update_bug_reopen(self, tracker, bug, image, project_info, image_old_map):
        tracker_bug = bug['tracker_bug']
        version_report = bug['version_report']
        merged_bug_types_set = bug['merged_bug_types_set']

        ai_check_detail = orjson.loads(image.ai_check_detail)
        use_check_detail = BugBuildBase.filter_check_detail(ai_check_detail, merged_bug_types_set)
        image_ = image_old_map.get(bug['image_id'], None)
        if not image_:
            raise Exception(f'not found old image:{bug["image_id"]}')
        if has_custom_template(project_info):
            description, _ = BugBuildTpl(image_, None, None, None, None, project_info).build_bug_items(use_check_detail)
        else:
            description, _ = BugBuildComm(image_, None, None).build_bug_items(use_check_detail)

        attachments = [storage.get_abs_path(image.ai_mark_img_path)] if image.ai_mark_img_path else []
        comment = f"<p><span style='color:red'>基于{version_report or '最新'}版本回归验证不通过</span></p>{description}"
        # 优先指派给解决人，其次当前处理人
        assignee = tracker_bug.resolver or tracker_bug.assignee
        tracker.reopen_bug(bug['external_id'], comment, attachments, assignee)
