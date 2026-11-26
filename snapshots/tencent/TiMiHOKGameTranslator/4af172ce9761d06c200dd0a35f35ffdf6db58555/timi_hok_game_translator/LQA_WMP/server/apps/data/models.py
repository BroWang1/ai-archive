from django.db import models

from apps.project.models import Module, Project
from libs import BaseAttrModel
from libs.defs import ReviewedEnum


class Data(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    job_id = models.BigIntegerField(default=0, verbose_name='任务id')
    module = models.ForeignKey(Module, null=True, on_delete=models.DO_NOTHING)
    name = models.TextField(default='', verbose_name='ui页面路径')
    resource_version = models.CharField(max_length=100, default='', verbose_name='资源版本')
    device = models.JSONField(default=dict, verbose_name='设备信息')
    file_path = models.CharField(max_length=128, default='', verbose_name='保存数据的文件路径')
    shot_img_path = models.CharField(max_length=128, default='', verbose_name='截图文件路径')
    reviewed = models.IntegerField(choices=ReviewedEnum, default=ReviewedEnum.EMPTY,
                                   verbose_name='审核，0：未审核(无审核记录)，1：系统自动审核，2：人工审核')

    class Meta:
        # app_label = 'data'
        db_table = 'lqa_data'
        indexes = [
            models.Index(fields=["job_id"], name='idx_data_job')
        ]


class ImagerResource(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=255, default='', verbose_name='图片名')
    resource_version = models.CharField(max_length=255, default='', verbose_name='资源版本')
    resources_path = models.CharField(max_length=255, default='', verbose_name='资源路径')
    md5 = models.CharField(max_length=100, default='', verbose_name='md5')
    file_path = models.CharField(max_length=255, default='', verbose_name='图片存储路径')

    class Meta:
        # app_label = 'image_resources'
        db_table = 'lqa_image_resource'
        constraints = [
            models.UniqueConstraint(fields=['name', 'md5'], name='idx_unique_name_md5')
        ]
