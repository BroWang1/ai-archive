#!/usr/bin/env python
"""Django 项目的命令行管理工具, 用于执行各类管理任务
(如启动开发服务器 runserver、数据库迁移 migrate/makemigrations、
创建超级用户 createsuperuser 等)
"""
import os
import sys


def main():
    """执行管理任务"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
