# -*- coding: utf-8 -*-
"""
# @file: util_network.py
# @desc: 网络请求响应处理工具模块, 提供统一的 HTTP 响应格式封装:
#        - response: 构造统一结构的 JSON 响应体 (success/err_msg/result),
#                    并支持通过 **args 追加自定义扩展字段, 最终以 Flask jsonify 返回
"""
from flask import jsonify


def response(success=True, err_msg="", result=None, **args):
    """ 网络请求response消息处理
    :param success: bool, http 相应码
    :param err_msg: str, 错误消息
    :param result: 结果数据
    :param args: dict, 其他补充内容
    :return: response 数据
    """
    ret = {
        "success": success,
        "err_msg": err_msg,
        "result": result
    }
    ret.update(args)
    return jsonify(ret)
