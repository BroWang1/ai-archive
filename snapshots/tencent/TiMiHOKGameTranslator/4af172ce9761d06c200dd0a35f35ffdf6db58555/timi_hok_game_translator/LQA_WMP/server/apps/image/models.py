from django.db import models

from libs.defs import SwitchEnum, ImageTaskErrorEnum, ImageAiSignErrorEnum
from apps.project.models import Project
from libs import BaseAttrModel


class Image(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    job_id = models.BigIntegerField(default=0, verbose_name='任务id')
    
    data_id = models.BigIntegerField(default=0, verbose_name='data id')
    language = models.IntegerField(verbose_name='需要还原的语言')
    is_latest = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.ON, verbose_name='是否最新')
    iteration = models.IntegerField(default=1, verbose_name='还原次数')
    rect_location = models.TextField(default='', verbose_name='文本框,图像框集合')
    file_name = models.CharField(max_length=255, default='', verbose_name='文件名称') # like 98(job_id)-8821(data_id)-LAN_TW_CHT.png
    file_path = models.CharField(max_length=255, default='', verbose_name='文件名称')
    size = models.CharField(max_length=64, default='', verbose_name='图片尺寸')

    # ai 识别
    ai_sign = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='是否需要识别图片,0不需要,1需要')
    ai_mark_img_path = models.CharField(max_length=255, default='', verbose_name='识别后标记结果图片')
    ai_rect_img_path = models.CharField(max_length=255, default='', verbose_name='识别后标记坐标图片debug使用')
    ai_overframe = models.IntegerField(default=0, verbose_name='是否超框,true代表超框,false代表没有超框')
    ai_check_detail = models.TextField(default='', verbose_name='图片识别返回的文本信息,全量识别时用到')
    ai_sign_suc = models.IntegerField(choices=ImageAiSignErrorEnum, default=ImageAiSignErrorEnum.ERR_NO, verbose_name='识别阶段是否成功,0默认,1成功,2失败')
    ai_bug_types = models.JSONField(default=list, verbose_name='ai识别缺陷类型,1:漏译;2:超框;3:漏key;4:标准框重叠')

    err_msg = models.TextField(default='', verbose_name='错误信息')
    err_type = models.IntegerField(choices=ImageTaskErrorEnum, default=ImageTaskErrorEnum.ERR_NO, verbose_name='图像检测失败类型')

    will_review = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='当存在“标准框重叠”时需要人工审核')
    reviewed = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='是否已审核')  # 跟will_review无关联

    class Meta:
        # app_label = 'image'
        db_table = 'lqa_image'
        # 索引以实际数据库中手动建立的为准
        # indexes = [
        #     models.Index(fields=["job_id", "data_id"], name='idx_image_job_data')
        # ]
        # constraints = [
        #     models.UniqueConstraint(fields=['job_id', 'data_id', 'language'], name='idx_unique_job_data_language')
        # ]


class DataReview(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING)
    data_id = models.BigIntegerField(default=0, verbose_name='data id')
    image_id = models.BigIntegerField(default=0, verbose_name='image id')
    rect_location = models.TextField(default='{}', verbose_name='文本框,图像框集合')
    check_rect_location = models.TextField(default='{}', verbose_name='审核后的文本框,图像框集合')
    dirty_rect_location = models.TextField(default='{}', verbose_name='删除的文本框,图像框集合')
    size = models.CharField(max_length=64, default='', verbose_name='图片尺寸')
    reviewer = models.CharField(default='', max_length=100, verbose_name='审核人')

    class Meta:
        # app_label = 'data_review'
        db_table = 'lqa_data_review'

