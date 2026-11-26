# -*- coding: utf-8 -*-
"""
# @file: log.py
# @desc: 日志配置初始化模块, 提供以下能力:
#        - get_logger: 创建并配置名为 'handle' 的 logger, 日志级别为 INFO;
#                      日志目录通过环境变量 LOG_PATH 指定 (默认 ./log), 不存在时自动创建;
#                      日志输出到文件 log_lqa.log, 格式包含时间、级别、文件名、函数名、行号及消息内容
#        - logger: 模块加载时创建的全局 logger 实例, 供其他模块直接导入使用
"""
import os
import logging


def get_logger():
    _logger = logging.getLogger('handle')
    log_path = os.environ.get('LOG_PATH', './log')
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    _logger.setLevel(logging.INFO)
    fh = logging.FileHandler('{}/log_lqa.log'.format(log_path))
    fh.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s %(funcName)s %(lineno)s - %(message)s"))
    _logger.addHandler(fh)
    return _logger


logger = get_logger()
