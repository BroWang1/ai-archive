# -*- coding: utf-8 -*-
"""
# @file: portal.py
# @desc: 服务入口文件, 创建 Flask app 并注册 LQA 相关 blueprint;
#        调试模式下直接启动开发服务器, 生产模式下由 gunicorn 加载本模块的 app 对象启动
"""
from flask import Flask
from config import baseconfig
from handles.handle_lqa import app_lqa
from common.log import logger

app = Flask(__name__)
app.register_blueprint(app_lqa)


# 仅在直接运行本文件时启动开发服务器
# 不能放在模块级: gunicorn --preload 会 import 本模块, 模块级 app.run()
# 会阻塞 master 进程导致容器无法启动
if __name__ == '__main__':
    if baseconfig.DEBUG_MODE:
        logger.info("debug mode started")
        app.run("0.0.0.0", 8086, debug=True)
    else:
        logger.info("debug mode off, serve with: gunicorn -c config/gunicorn_config.py portal:app")
        app.run("0.0.0.0", 8086, debug=False)
