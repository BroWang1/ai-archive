"""
创建/重置超级管理员

python manage.py init_admin --username admin --password 'Admin@123456'
  也可通过环境变量 LQA_ADMIN_USERNAME / LQA_ADMIN_PASSWORD 传入（便于容器启动时自动初始化）
  --if-not-exists  已存在任意超级管理员时跳过
"""
import os

from django.core.management.base import BaseCommand, CommandError
from pydantic import TypeAdapter, ValidationError

from apps.user.models import User
from apps.user.schemas import Password, Username
from libs.defs import SwitchEnum, UserStatusEnum


class Command(BaseCommand):
    help = '创建或重置超级管理员账号'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('LQA_ADMIN_USERNAME', 'admin'))
        parser.add_argument('--password', default=os.environ.get('LQA_ADMIN_PASSWORD', ''))
        parser.add_argument('--if-not-exists', action='store_true', help='已存在超级管理员时跳过')

    def handle(self, *args, **options):
        if options['if_not_exists'] and User.objects.filter(is_admin=SwitchEnum.ON).exists():
            self.stdout.write('已存在超级管理员，跳过')
            return
        try:
            username = TypeAdapter(Username).validate_python(options['username'])
            password = TypeAdapter(Password).validate_python(options['password'])
        except ValidationError as err:
            raise CommandError(f'参数不合法: {err.errors()[0]["msg"]}')

        user = User.objects2.filter(name=username).first()
        created = user is None
        if created:
            user = User(name=username, name_zh=username)
        user.is_delete = 0
        user.is_admin = SwitchEnum.ON
        user.status = UserStatusEnum.ACTIVE
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'超级管理员 {username} {"已创建" if created else "密码已重置"}'))
