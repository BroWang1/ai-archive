from django.db import models

from libs import BaseAttrModel
from libs.defs import (BugPriorityEnum, BugSeverityEnum, BugBillStatusEnum, BugRegressStatusEnum,
                       BugTrackerTypeEnum)
from apps.job.models import Job
from apps.project.models import Project


class Bug(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    job = models.ForeignKey(Job, on_delete=models.DO_NOTHING)
    image_id = models.IntegerField(default=0, verbose_name='image_id')

    # 提单状态
    bill_status = models.IntegerField(choices=BugBillStatusEnum, default=BugBillStatusEnum.INIT, verbose_name='提单结果')
    bill_text = models.TextField(default='', verbose_name='提交bug返回的错误信息')
    # 回归状态
    regress_status = models.IntegerField(choices=BugRegressStatusEnum, default=BugRegressStatusEnum.INIT)
    regress_job_ids = models.JSONField(default=list, verbose_name="回归任务id")

    key_in_bug = models.TextField(default='', verbose_name='ai识别的结果')
    celery_task_id = models.CharField(max_length=64, default='', verbose_name='celery_task id')

    raw_image_path = models.CharField(max_length=255, default='', verbose_name='原始图片路径')
    ai_image_path = models.CharField(max_length=255, default='', verbose_name='AI识别返回的图片路径')

    # 缺陷系统
    tracker = models.CharField(max_length=16, choices=BugTrackerTypeEnum, default=BugTrackerTypeEnum.NONE,
                               verbose_name='提交时使用的缺陷系统')
    external_id = models.CharField(max_length=64, default='', verbose_name='缺陷系统中的缺陷ID')
    external_url = models.CharField(max_length=255, default='', verbose_name='缺陷系统中的缺陷链接')
    status = models.CharField(max_length=32, default='open', verbose_name='缺陷状态（平台内记录模式使用）')
    comments = models.JSONField(default=list, verbose_name='处理记录')

    title = models.CharField(max_length=255, verbose_name='标题')
    reporter = models.CharField(max_length=64, default='', verbose_name='创建者人')
    current_owner = models.CharField(max_length=255, default='', verbose_name='处理人')
    priority = models.IntegerField(choices=BugPriorityEnum, default=BugPriorityEnum.EMPTY, verbose_name='优先级')
    severity = models.IntegerField(choices=BugSeverityEnum, default=BugSeverityEnum.EMPTY, verbose_name='严重程度')
    version_report = models.CharField(max_length=64, default='', verbose_name='发现版本')
    version_fix = models.CharField(max_length=64, default='', verbose_name='修复版本')
    release_id = models.CharField(max_length=64, default='', verbose_name='发布计划')
    description = models.TextField(default='', verbose_name='描述')

    class Meta:
        db_table = 'lqa_bug'
