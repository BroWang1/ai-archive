"""
lqa 后端项目的 WSGI 配置文件

该文件将 WSGI 可调用对象以模块级变量 `application` 的形式暴露出来,
供 WSGI 服务器 (如 Gunicorn/uWSGI) 加载并处理 HTTP 请求

同时导入 celery_app, 确保 Django 应用启动时 Celery 实例已初始化
(用于异步任务处理)

更多关于本文件的说明, 参见:
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

application = get_wsgi_application()


from celery_app import app as celery_app