# -*- coding: utf-8 -*-
"""
# @file: handle_lqa.py
# @desc: LQA 服务相关 HTTP 接口 (Blueprint: app_lqa), 提供以下能力:
#        - GET  /health                  健康检查接口, 供容器编排探活使用, 并返回 OCR 可用状态
#        - POST /image/lqa_check/        图像本地化异常 (LQA) 检测接口, 支持 OCR 识别定位和已知坐标两种模式,
#                                        可识别未译、错译等问题, 并支持与历史检测结果比对 (supervised)
#        - POST /image/image_extraction/ 图像前景提取接口, 用于从截图中提取前景/文本区域
"""
import time
import json
import traceback
from flask import Blueprint, request
from common.log import logger
from common.interface_ocr import ocr_available
from task.lqa import ImageLqa
from task.image_processing import ImageProcessing

app_lqa = Blueprint('app_lqa', __name__)


# 健康检查 (供容器编排探活使用)
# OCR 是可选能力, 不可用时服务依然健康 (返回 200), 仅在 ocr 字段中体现,
# 便于运维确认当前是否处于降级检测状态
@app_lqa.route("/health", methods=["GET"])
def health():
    try:
        available, message = ocr_available()
    except Exception as ex:  # pylint: disable=broad-except
        available, message = False, str(ex)
    return json.dumps({
        "status": "ok",
        "ocr": {
            "available": available,
            "message": message,
            "degraded": not available,
        },
    }, ensure_ascii=False)


# lqa 本地化异常检测服务接口
@app_lqa.route("/image/lqa_check/", methods=["POST"])
def image_lqa():
    t0 = time.time()
    resp = {
        "success": False,
        "err_msg": None,
        "result": {}
    }
    try:
        project = None
        headers = request.headers.get("project-method", None)
        if headers is not None:
            project = headers.split('_lqa')[0]
        arguments = request.get_json()
        if not arguments:
            resp["err_msg"] = "body is None!"
            return
        img_base64 = arguments.get("img_base64", None)
        rect_locations = arguments.get("rect_locations", None)
        language = arguments.get("language", None)
        supervised = arguments.get("supervised", None)
        check_type = arguments.get("check_type", None)
        history_img_base64 = arguments.get("history_img_base64", None)
        history_result = arguments.get("history_result", None)
        no_trans_marks = arguments.get("no_trans_marks", None)
        error_trans_marks = arguments.get("error_trans_marks", None)
        ocr_detect = arguments.get("ocr_detect", 1)
        if img_base64 is None or rect_locations is None:
            resp["err_msg"] = "img is None!"
            return
        if ocr_detect == 1:  # 文本非精准位置, 需要 ocr 识别
            res = ImageLqa.lqa_check(img_base64, rect_locations, language, supervised, check_type,
                                     history_img_base64, history_result, project, no_trans_marks, error_trans_marks)
        else:  # 文本框已经是文本实际最小外接矩, 不需要识别
            res = ImageLqa.lqa_check_no_ocr(img_base64, rect_locations, language, supervised, check_type,
                                            history_img_base64, history_result, project, no_trans_marks, error_trans_marks)

        resp["success"] = True
        resp["result"] = res
    except Exception as ex:  # pylint: disable=broad-except
        logger.error(traceback.format_exc())
        resp["err_msg"] = str(ex)
    finally:
        t3 = time.time()
        logger.info("request costs %ss" % str(t3 - t0))
        return json.dumps(resp)


# 图像前景提取服务接口
@app_lqa.route("/image/image_extraction/", methods=["POST"])
def image_extraction():
    t0 = time.time()
    resp = {
        "success": False,
        "err_msg": None,
        "result": {}
    }
    try:
        arguments = request.get_json()
        if not arguments:
            resp["err_msg"] = "body is None!"
            return
        img_base64 = arguments.get("img_base64", None)
        zero_type = arguments.get("zero_type", 0)
        position_type = arguments.get("position_type", 0)
        alpha_t = arguments.get("alpha_t", 50)
        if img_base64 is None:
            resp["err_msg"] = "img is None!"
            return
        res = ImageProcessing.image_extraction(img_base64, zero_type, position_type, alpha_t)
        resp["success"] = True
        resp["result"] = res
    except Exception as ex:  # pylint: disable=broad-except
        logger.error(traceback.format_exc())
        resp["err_msg"] = str(ex)
    finally:
        t3 = time.time()
        logger.info("request costs %ss" % str(t3 - t0))
        return json.dumps(resp)
