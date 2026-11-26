from django.db import models

from libs import BaseAttrModel
from libs.defs import (JobStatusEnum, BugPriorityEnum, BugSeverityEnum, SwitchEnum, JobDiscernEnum,
                       JobResTypeEnum)
from apps.project.models import Project
from apps.user.models import User


class Job(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    creator = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=64, verbose_name='任务名称')
    languages = models.JSONField(default=list, verbose_name='需要还原的语言')    # 提交参数是数组，这里指定为数组
    discern = models.IntegerField(choices=JobDiscernEnum, default=JobDiscernEnum.DIFF, verbose_name='识别类型')
    ocr_detect = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='是否ocr')
    status = models.IntegerField(choices=JobStatusEnum, default=JobStatusEnum.UN_RUNNING, verbose_name='任务状态')
    # 回归任务
    parent_id = models.IntegerField(default=0, verbose_name='父任务id')
    regression_bug_ids = models.JSONField(default=list, verbose_name='需要回归bug的id')
    sign_bug_types = models.JSONField(default=list, verbose_name='识别bug类型')   # ai识别时用到
    # 还原执行（由前端调用项目配置的 Webhook 触发）
    svn_url = models.CharField(max_length=128, default='')
    svn_version = models.CharField(max_length=64, default='')
    build_id = models.CharField(max_length=128, default='', verbose_name='外部构建ID/链接（Webhook 返回）')
    build_no = models.CharField(max_length=64, default='', verbose_name='外部构建编号')
    # 提单配置
    bill_bug_types = models.JSONField(default=list, verbose_name='提单bug类型')
    priority = models.IntegerField(choices=BugPriorityEnum, default=BugPriorityEnum.INSIGNIFICANT, verbose_name='优先级')
    severity = models.IntegerField(choices=BugSeverityEnum, default=BugSeverityEnum.PROMT, verbose_name='严重程度')
    version_report = models.CharField(max_length=32, default='', verbose_name='发现版本')
    version_fix = models.CharField(max_length=32, default='', verbose_name='合入版本')
    release_id = models.CharField(max_length=32, default='', verbose_name='发布计划')

    plan_start_at = models.DateTimeField(blank=True, verbose_name='预约开始时间')
    plan_end_at = models.DateTimeField(blank=True, verbose_name='预约结束时间')
    exec_start_at = models.DateTimeField(blank=True, null=True, verbose_name='实际开始时间')
    exec_end_at = models.DateTimeField(blank=True, null=True, verbose_name='实际结束时间')
    remark = models.CharField(max_length=255, default='', verbose_name='备注')

    celery_task_id = models.CharField(max_length=64, default='', verbose_name='celery_task id')
    data_ids = models.JSONField(default=list, verbose_name='补充数据id')
    all_data_ids = models.JSONField(default=list, verbose_name='任务结束后填充')
    config_path99 = models.CharField(max_length=128, default='', verbose_name='99配置表路径')
    reason = models.TextField(default='', verbose_name='任务失败原因')

    class Meta:
        # app_label = 'job'
        db_table = 'lqa_job'


class JobExtra(BaseAttrModel):
    job_id = models.BigIntegerField(primary_key=True, verbose_name='job id')
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    test_app_file_path = models.CharField(max_length=128, default='', verbose_name='测试app存储路径')
    test_case_file_path = models.CharField(max_length=128, default='', verbose_name='测试用例存储路径')
    proj_res_type = models.CharField(choices=JobResTypeEnum, default=JobResTypeEnum.GIT, max_length=16, verbose_name='项目资源')
    proj_res_repo = models.CharField(max_length=128, default='', verbose_name='项目资源仓库')
    proj_res_br = models.CharField(max_length=32, default='', verbose_name='项目资源分支')
    proj_res_ver = models.CharField(max_length=32, default='', verbose_name='项目资源版本')
    proj_res_file_path = models.CharField(max_length=64, default='', verbose_name='项目资源其他')
    trans_res_type = models.CharField(choices=JobResTypeEnum, default=JobResTypeEnum.GIT, max_length=16, verbose_name='翻译资源')
    trans_res_repo = models.CharField(max_length=128, default='', verbose_name='翻译资源仓库')
    trans_res_br = models.CharField(max_length=32, default='', verbose_name='翻译资源分支')
    trans_res_ver = models.CharField(max_length=32, default='', verbose_name='翻译资源版本')
    trans_res_file_path = models.CharField(max_length=64, default='', verbose_name='翻译资源其他')

    class Meta:
        db_table = 'lqa_job_extra'


class JobDevice(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    job_id = models.BigIntegerField(verbose_name='job id')
    execute_pc = models.CharField(max_length=64, verbose_name='执行的机器')
    language = models.IntegerField(verbose_name='还原的语言')
    status = models.CharField(max_length=32, verbose_name='状态')
    editor_nums = models.IntegerField(verbose_name='编辑器数量')

    class Meta:
        db_table = 'lqa_job_device'
        constraints = [models.UniqueConstraint(fields=['job_id', 'execute_pc', 'language'], name='idx__job_pc_language')]
