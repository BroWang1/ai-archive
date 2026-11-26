# -*- coding: utf-8 -*-
"""
# @file: ocr_provider/paddle.py
# @desc: PaddleOCR 适配模块, 提供两个 OCR provider 实现:
#   - PaddleOcrLocal (name='paddleocr')
#       本进程内直接加载 PaddleOCR 模型进行识别 (离线, 无需外部服务)
#       依赖: pip install paddleocr paddlepaddle
#       相关配置: OCR_LANG (识别语言，默认 ch)、OCR_USE_GPU (是否启用 GPU, 默认 false)
#       模型以类变量缓存 (_engine), 同进程内仅加载一次, 兼容新旧版本 PaddleOCR 的初始化参数差异
#   - PaddleOcrHttp (name='paddleocr_http')
#       调用 PaddleOCR 官方 hubserving / PaddleX 部署的 HTTP 服务进行远程识别
#       相关配置: OCR_URL (服务地址, 必填)、OCR_TIMEOUT (请求超时时间, 默认 60s)
#       期望响应格式: {"results": [[{"text": "abc", "text_region": [[x,y],...]}, ...]]}
#
# PaddleOCR 对中日韩、拉丁语系支持较好, 可离线部署, 是一般场景下的推荐选择
# 通过环境变量 OCR_PROVIDER 设置为 paddleocr 或 paddleocr_http 以启用对应实现
"""
import base64
import logging

import requests

from .base import OcrProvider, OcrError, quad_to_box, base64_to_ndarray

logger = logging.getLogger('handle')


class PaddleOcrLocal(OcrProvider):
    """进程内加载 PaddleOCR 模型 (离线, 无需外部服务)"""

    name = 'paddleocr'
    remote = False

    _engine = None

    def _get_engine(self):
        if PaddleOcrLocal._engine is not None:
            return PaddleOcrLocal._engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as err:
            raise OcrError(
                '未安装 PaddleOCR, 请执行: pip install paddleocr paddlepaddle'
            ) from err
        lang = self.config.get('lang', 'ch')
        use_gpu = str(self.config.get('use_gpu', 'false')).lower() == 'true'
        kwargs = {'lang': lang, 'show_log': False, 'use_angle_cls': True}
        try:
            PaddleOcrLocal._engine = PaddleOCR(use_gpu=use_gpu, **kwargs)
        except TypeError:
            # 新版本 PaddleOCR 移除了 use_gpu / show_log 参数
            PaddleOcrLocal._engine = PaddleOCR(lang=lang)
        logger.info('PaddleOCR 本地引擎已加载 lang=%s use_gpu=%s', lang, use_gpu)
        return PaddleOcrLocal._engine

    def recognize(self, img_base64, project=None):
        engine = self._get_engine()
        img = base64_to_ndarray(img_base64)
        try:
            raw = engine.ocr(img)
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('PaddleOCR 识别失败: %s' % err) from err

        results = []
        if not raw:
            return results
        # 兼容 [[...]] 与 [...] 两种返回层级
        lines = raw[0] if raw and isinstance(raw[0], list) else raw
        for line in lines or []:
            if not line:
                continue
            try:
                points, (text, _score) = line[0], line[1]
            except (ValueError, IndexError, TypeError):
                continue
            if not text:
                continue
            results.append({'area': quad_to_box(points), 'result': text})
        return results


class PaddleOcrHttp(OcrProvider):
    """PaddleOCR hubserving / PaddleX HTTP 服务

    期望响应形如:

        {"results": [[{"text": "abc", "text_region": [[x,y],...]}, ...]]}
    """

    name = 'paddleocr_http'
    remote = True

    def recognize(self, img_base64, project=None):
        url = self.config.get('url')
        if not url:
            raise OcrError('未配置 OCR_URL (PaddleOCR HTTP 服务地址)')
        timeout = int(self.config.get('timeout', 60))
        try:
            resp = requests.post(url, json={'images': [img_base64]}, timeout=timeout)
        except requests.RequestException as err:
            raise OcrError('PaddleOCR 服务请求失败: %s' % err) from err
        if resp.status_code != 200:
            raise OcrError('PaddleOCR 服务返回 HTTP %s' % resp.status_code)
        try:
            payload = resp.json()
        except ValueError as err:
            raise OcrError('PaddleOCR 服务返回非 JSON') from err

        groups = payload.get('results') or []
        if groups and isinstance(groups[0], list):
            items = groups[0]
        else:
            items = groups
        results = []
        for item in items or []:
            text = item.get('text')
            region = item.get('text_region') or item.get('text_box_position')
            if not text or not region:
                continue
            results.append({'area': quad_to_box(region), 'result': text})
        return results
