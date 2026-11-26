# -*- coding: utf-8 -*-
"""
# @file: gunicorn_config.py
# @desc: Gunicorn WSGI 服务器配置文件, 用于配置 lqa_service 的启动参数, 包括:
#        - bind: 服务监听地址及端口 (默认 0.0.0.0:8086)
#        - worker_class: worker 工作模式 (默认 gevent 协程模式)
#        - timeout: 请求处理超时时间, 单位秒 (默认 120)
#        - workers: worker 进程数量 (默认 3, 可通过环境变量 GUNICORN_WORKERS 调整)
#        - accesslog/errorlog: 访问日志与错误日志文件路径
#        - loglevel: 日志级别 (默认 info)
"""
import os

bind = os.getenv("BIND", '0.0.0.0:8086')
worker_class = os.getenv("WORK_CLASS", "gevent")
# 注意: 此处历史上误用了 BIND 变量, 设置 BIND 后会导致 int() 解析失败
timeout = int(os.getenv("TIMEOUT", 120))

# os.cpu_count()
workers = int(os.getenv("GUNICORN_WORKERS", 3))
accesslog = os.getenv("ACCESSLOG", "gunicirn_access.log")
errorlog = os.getenv("ERRORLOG", "gunicirn_error.log")
loglevel = os.getenv("LOGLEVEL", "info")
