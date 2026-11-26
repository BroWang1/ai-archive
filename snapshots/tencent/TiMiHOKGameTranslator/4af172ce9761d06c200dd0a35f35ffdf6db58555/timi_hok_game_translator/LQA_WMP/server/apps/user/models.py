from django.contrib.auth.hashers import make_password, check_password
from django.db import models

from apps.project.models import Project
from libs.defs import SwitchEnum, RoleEnum, UserStatusEnum
from libs import BaseAttrModel, BaseModel


class User(BaseAttrModel):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, verbose_name='登录用户名')
    name_zh = models.CharField(max_length=100, default='', verbose_name='显示名称')
    email = models.CharField(max_length=128, default='', verbose_name='邮箱')
    department = models.CharField(max_length=100, default='', verbose_name='部门')
    password = models.CharField(max_length=128, default='', verbose_name='密码哈希')
    status = models.IntegerField(choices=UserStatusEnum, default=UserStatusEnum.ACTIVE, verbose_name='状态')
    is_admin = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='是否超级管理员')
    last_login_at = models.DateTimeField(null=True, blank=True, verbose_name='最后登录时间')
    projects = models.ManyToManyField(Project, through='UserProjectRelationship', related_name='users')
    access_token = models.CharField(max_length=255, default='')

    # 不允许通过接口返回的敏感字段
    SENSITIVE_FIELDS = ('password', 'access_token')

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return bool(self.password) and check_password(raw_password, self.password)

    class Meta:
        db_table = 'lqa_user'


class UserProjectRelationship(BaseModel):
    """角色 用户关系表"""
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, verbose_name='项目')
    user = models.ForeignKey('User', on_delete=models.DO_NOTHING, verbose_name='用户')
    role = models.IntegerField(choices=RoleEnum, verbose_name='角色')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lqa_user_project_relationship'
        constraints = [models.UniqueConstraint(fields=['project_id', 'user_id', 'role'],
                                               name='idx__project_id__user_id__role')]
