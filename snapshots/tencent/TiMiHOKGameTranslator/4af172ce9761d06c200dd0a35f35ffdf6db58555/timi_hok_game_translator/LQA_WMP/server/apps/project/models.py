from django.db import models
import datetime

from libs.defs import ProjectTypeEnum, ProjectPhaseEnum, GameTypeEnum, SwitchEnum, BugTrackerTypeEnum
from libs import BaseAttrModel, BaseModel


class Project(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=100, unique=True, verbose_name='项目代号')
    name = models.CharField(max_length=100, verbose_name='项目名称')
    img = models.CharField(default='', max_length=255, verbose_name='项目图标')
    project_type = models.IntegerField(choices=ProjectTypeEnum, verbose_name='项目类型')
    project_phase = models.IntegerField(choices=ProjectPhaseEnum, verbose_name='项目阶段')
    # 游戏类型支持多选，以逗号分隔存储（如 '1,3'；取值见 GameTypeEnum）
    game_type = models.CharField(default='', max_length=32, verbose_name='游戏类型')
    team = models.CharField(default='', max_length=100, verbose_name='所属团队')
    # AI 识别服务中的项目标识，请求时以 "{cvtest_project}_lqa" 作为 project-method
    cvtest_project = models.CharField(default='', max_length=32, verbose_name='AI识别项目名')
    test_manager = models.CharField(default='', max_length=100, verbose_name='测试经理')

    class Meta:
        # app_label = 'project'
        db_table = 'lqa_project'


# class ProjectConfig(BaseModel):
#     """用来存储项目的一些开关配置（不需要元素搜索，否则单独建表）"""
#     id = models.BigAutoField(primary_key=True)
#     project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
#     cate = models.IntegerField(choices=ProjectConfigCateEnum)
#     # content内容规格，参考./schemas.py中的ProjectConfig相关的Schema
#     content = models.JSONField(default=dict, verbose_name='配置json')
#
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     class Meta:
#         # app_label = 'project_config'
#         db_table = 'lqa_project_config'
#         constraints = [models.UniqueConstraint(fields=['project_id', 'cate'], name='idx__project_id__cate')]


class Module(BaseAttrModel):
    """项目配置：模块"""
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=100, verbose_name='模块名字')
    show_name = models.CharField(max_length=100, verbose_name='模块show名字')
    sub_module = models.CharField(default='', max_length=100, verbose_name='子模块')

    class Meta:
        # app_label = 'module'
        db_table = 'lqa_module'



class ProjectConfigBugType(BaseAttrModel):
    """项目配置：缺陷类型"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=32, verbose_name='name')
    label = models.CharField(max_length=32, verbose_name='label')
    value = models.IntegerField(verbose_name='value')
    enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.ON, verbose_name='enable')
    trans_marks = models.CharField(max_length=1024, default='[]', verbose_name='trans_marks')   # json数组

    class Meta:
        db_table = 'lqa_project_config_bugtype'


class ProjectConfigLanguage(BaseAttrModel):
    """项目配置：语言"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=32, verbose_name='name')
    label = models.CharField(max_length=32, verbose_name='label')
    custom_label = models.CharField(max_length=32, default='', verbose_name='custom_label')
    value = models.IntegerField(verbose_name='value')
    enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.ON, verbose_name='enable')

    class Meta:
        db_table = 'lqa_project_config_language'


class ProjectConfigImgRevert(BaseAttrModel):
    """项目配置：图片还原"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    root_path = models.CharField(max_length=128, verbose_name='root_path')
    key = models.CharField(max_length=32, verbose_name='key')
    text = models.CharField(max_length=32, verbose_name='text')
    lang_path = models.TextField(default='', verbose_name='lang_path')
    no_trans_text = models.CharField(max_length=128, verbose_name='no_trans_text')

    class Meta:
        db_table = 'lqa_project_config_imgrevert'


class ProjectConfigBugBillMethod(BaseAttrModel):
    """项目配置：提单分配方式"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    bug_type_enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='bug_type_enable')
    language_enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='language_enable')
    module_enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='module_enable')
    # [新增] 缺陷描述模板，支持HTML格式和变量替换（{image_id}、{image_name}、{job_id}、{create_time}）
    description_template = models.TextField(default='', verbose_name='缺陷描述模板')

    class Meta:
        db_table = 'lqa_project_config_bugbill_method'


class ProjectConfigBugBillUser(BaseAttrModel):
    """项目配置：提单处理人"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.ON, verbose_name='enable')
    bug_type = models.IntegerField(default=0, verbose_name='bug_type')
    language = models.IntegerField(default=0, verbose_name='language')
    module = models.IntegerField(default=0, verbose_name='module')
    user_names = models.JSONField(default=list, verbose_name="user_names")

    class Meta:
        db_table = 'lqa_project_config_bugbill_user'


class ProjectConfigOther(BaseAttrModel):
    """
    项目配置：还原执行（Webhook）
    还原任务由前端浏览器直接调用 Webhook 触发（Jenkins / GitLab CI / 自建服务等），
    url / headers / body 支持 {{变量}} 占位符，变量列表见 apps.job.service.runner_variables
    """
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    webhook_url = models.CharField(max_length=512, default='', verbose_name='Webhook地址')
    webhook_method = models.CharField(max_length=8, default='POST', verbose_name='请求方法')
    webhook_headers = models.TextField(default='{}', verbose_name='请求头(JSON)')
    webhook_body = models.TextField(default='', verbose_name='请求体模板(JSON)，为空时发送全部变量')
    editor_path = models.CharField(max_length=128, default='', verbose_name='编辑器路径')
    editor_version = models.CharField(max_length=32, default='', verbose_name='编辑器版本')

    class Meta:
        db_table = 'lqa_project_config_other'


class ProjectConfigBugTracker(BaseAttrModel):
    """项目配置：缺陷系统（每个项目一条）"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    tracker_type = models.CharField(max_length=16, choices=BugTrackerTypeEnum, default=BugTrackerTypeEnum.NONE,
                                    verbose_name='缺陷系统类型')
    base_url = models.CharField(max_length=255, default='', verbose_name='缺陷系统地址')
    username = models.CharField(max_length=128, default='', verbose_name='账号（禅道）')
    api_key = models.CharField(max_length=255, default='', verbose_name='API Key（Bugzilla）/ 密码（禅道）')
    product = models.CharField(max_length=128, default='', verbose_name='产品名称（Bugzilla）/ 产品ID（禅道）')
    component = models.CharField(max_length=128, default='', verbose_name='组件（Bugzilla）')
    extra = models.JSONField(default=dict, verbose_name='高级配置(JSON)')

    class Meta:
        db_table = 'lqa_project_config_bugtracker'


class ProjectConfigCustomField(BaseAttrModel):
    """项目配置：自定义提单字段
    用于在提单界面动态添加自定义下拉选择框，字段值会原样提交到缺陷系统对应字段。
    - field_name: 显示在提单弹窗中的标题
    - field_key: 缺陷系统中的字段名（如 Bugzilla 的 cf_xxx、禅道的 type/os）
    - options: 下拉选项列表（可从缺陷系统拉取，也可手动编辑）
    - enable: 是否启用该字段
    - sort_order: 排序顺序
    """
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    field_name = models.CharField(max_length=64, verbose_name='字段显示名称')
    field_key = models.CharField(max_length=64, verbose_name='缺陷系统字段名')
    options = models.JSONField(default=list, verbose_name='下拉选项列表')
    enable = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.ON, verbose_name='enable')
    sort_order = models.IntegerField(default=0, verbose_name='排序')

    class Meta:
        db_table = 'lqa_project_config_custom_field'
