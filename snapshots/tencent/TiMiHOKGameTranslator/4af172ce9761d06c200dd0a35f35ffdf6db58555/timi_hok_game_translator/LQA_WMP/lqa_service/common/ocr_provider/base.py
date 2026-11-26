# -*- coding: utf-8 -*-
"""
# @file: ocr_provider/base.py
# @desc: OCR 适配层抽象接口模块, 定义所有 OCR provider 必须遵循的统一规范, 包括:
#        - OcrError: OCR 调用失败的统一异常类型, 各 provider 在识别失败/配置缺失时抛出
#        - base64_to_ndarray: base64 图像数据解码为 OpenCV BGR ndarray, 供本地推理类
#                     provider (EasyOCR/RapidOCR/Tesseract/PaddleOCR本地) 使用
#        - quad_to_box: 将任意四点多边形坐标 (如 PaddleOCR/EasyOCR 返回的文本框顶点)
#                     转换为轴对齐的矩形包围盒 [x1, y1, x2, y2]
#        - OcrProvider: provider 抽象基类, 约定子类属性 (name 标识、remote 是否依赖远程
#                     服务、capable 是否具备真实识别能力) 及抽象方法 recognize;
#                     并提供默认的 test_connection 自检方法, 通过识别一张内置测试图
#                     验证 provider 是否正常工作
#        - NullOcr: 空实现 provider(name='none'), 用于显式关闭 OCR 能力; 选用后不会
#                     产生任何识别调用, 依赖 OCR 的检测项 (错译、文本超框) 自动跳过,
#                     其余不依赖 OCR 的检测照常进行
#
# LQA 的超框/漏译检测依赖 OCR 返回「文本内容 + 精确边界框」, 因此只接受能同时
# 给出两者的 OCR 服务, 各 provider 的 recognize 方法需统一返回以下格式 (与历史
# 接口保持一致):
#     [{"area": [x1, y1, x2, y2], "result": "识别出的文本"}, ...]
"""
from abc import ABC, abstractmethod
import base64
import logging

import numpy as np
import cv2

logger = logging.getLogger('handle')


class OcrError(Exception):
    """OCR 调用失败"""


def base64_to_ndarray(img_base64):
    """base64 -> BGR ndarray"""
    raw = base64.b64decode(img_base64)
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise OcrError('图像解码失败')
    return img


def quad_to_box(points):
    """任意多边形顶点 -> 轴对齐包围盒 [x1, y1, x2, y2]

    PaddleOCR / EasyOCR 等返回的是四点多边形, 需转为 LQA 需要的矩形
    """
    xs = [int(round(float(p[0]))) for p in points]
    ys = [int(round(float(p[1]))) for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


class OcrProvider(ABC):
    """OCR 提供方抽象基类"""

    name = 'base'
    #: 是否依赖外部网络服务
    remote = True
    #: 是否提供真实 OCR 能力 (NullOcr 为 False)
    capable = True

    def __init__(self, config=None):
        self.config = config or {}

    @abstractmethod
    def recognize(self, img_base64, project=None):
        """识别整图文字

        :param img_base64: str, base64 编码的图像
        :param project: str, 调用方项目标识 (部分服务用于鉴权/路由, 可忽略)
        :return: list[dict], [{"area": [x1,y1,x2,y2], "result": "文本"}, ...]
        :raises OcrError: 调用失败
        """

    def test_connection(self):
        """连通性自检, 返回描述信息字符串"""
        img = np.full((48, 160, 3), 255, np.uint8)
        cv2.putText(img, 'LQA123', (6, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        ok, buf = cv2.imencode('.png', img)
        if not ok:
            raise OcrError('测试图编码失败')
        data = self.recognize(base64.b64encode(buf).decode('ascii'))
        texts = [d.get('result', '') for d in (data or [])]
        return '连接正常, 识别到 %d 个文本块: %s' % (len(texts), texts[:5])


class NullOcr(OcrProvider):
    """空实现: 显式声明「不使用 OCR」(OCR_PROVIDER=none)

    OCR 在本服务中是可选能力, 选用本 provider 时不会产生任何识别调用,
    依赖 OCR 的检测项 (错译、文本超框) 自动跳过, 其余检测照常进行
    """

    name = 'none'
    remote = False
    capable = False

    def recognize(self, img_base64, project=None):
        return []

    def test_connection(self):
        return '已显式关闭 OCR (OCR_PROVIDER=none), 依赖 OCR 的检测项将跳过'
