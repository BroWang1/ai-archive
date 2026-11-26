# -*- coding: utf-8 -*-
"""
# @file: ocr_provider/cvtest.py
# @desc: CVTest OCR 适配模块 (内网自建服务, 向后兼容历史接口), 提供 CvtestOcr provider 实现:
#   - name='cvtest', remote=True, 通过 HTTP 调用内网自建的 OCR 识别服务
#
#   通信协议:
#     POST {OCR_URL}
#     headers: {"project-method": "<project>_ocr"}
#               project 由调用方传入或取配置 OCR_DEFAULT_PROJECT; 缺失该请求头会被服务端
#               判为 "No authorization"
#     body:    {"img_base64": "...", "location": null, "projectid": <OCR_PROJECT_ID, 默认19998>}
#     resp:    {"errCode": 0, "data": [{"area": [x1,y1,x2,y2], "result": "文本"}, ...]}
#
#   错误处理与重试:
#     - errCode == 0 且 data 非空: 识别成功, 返回 data
#     - errCode == 0 但 data 为空: 通常是鉴权失败 (project-method 缺失或项目未授权),
#                                 抛出 OcrError 并提示检查请求头及项目授权
#     - errCode == -2: 服务侧繁忙, 按 RETRY_INTERVAL(0.6s) 间隔重试, 最多 MAX_RETRY(10) 次
#     - 其他 errCode: 直接抛出 OcrError, 附带 errCode 与 errMsg
#     - HTTP 非 200 / 响应非 JSON / 请求异常: 均包装为 OcrError 抛出
#
#   相关配置: OCR_URL (服务地址)、OCR_TIMEOUT (请求超时, 默认 60s)、
#            OCR_PROJECT_ID (默认项目ID, 默认19998)、OCR_DEFAULT_PROJECT (默认项目标识)
"""
import time
import logging

import requests

from .base import OcrProvider, OcrError

logger = logging.getLogger('handle')

MAX_RETRY = 10
RETRY_INTERVAL = 0.6


class CvtestOcr(OcrProvider):
    """内网 CVTest OCR 服务"""

    name = 'cvtest'
    remote = True

    def recognize(self, img_base64, project=None):
        url = self.config.get('url')
        if not url:
            raise OcrError('未配置 OCR_URL')
        timeout = int(self.config.get('timeout', 60))
        project_id = int(self.config.get('project_id', 19998))

        data = {'img_base64': img_base64, 'location': None, 'projectid': project_id}
        headers = {}
        # 该服务依赖 project-method 请求头鉴权, 缺失时返回 No authorization 且 data 为 null
        project = project or self.config.get('default_project')
        if project:
            headers['project-method'] = '%s_ocr' % project

        last_err = None
        for attempt in range(MAX_RETRY):
            try:
                resp = requests.post(url=url, json=data, headers=headers, timeout=timeout)
            except requests.RequestException as err:
                raise OcrError('OCR 服务请求失败: %s' % err) from err
            if resp.status_code != 200:
                raise OcrError('OCR 服务返回 HTTP %s' % resp.status_code)
            try:
                payload = resp.json()
            except ValueError as err:
                raise OcrError('OCR 服务返回非 JSON') from err

            err_code = payload.get('errCode')
            if err_code == 0:
                result = payload.get('data')
                if result is None:
                    # errCode=0 但 data 为空, 通常是鉴权失败, 历史实现会静默返回 None
                    raise OcrError(
                        'OCR 服务未返回数据: %s (请确认请求头 project-method 及项目授权)'
                        % (payload.get('err_msg') or payload.get('errMsg') or '未知原因')
                    )
                return result
            if err_code == -2:  # 服务侧繁忙, 可重试
                last_err = payload.get('errMsg')
                logger.warning('OCR 重试 %s/%s: %s', attempt + 1, MAX_RETRY, last_err)
                time.sleep(RETRY_INTERVAL)
                continue
            raise OcrError('OCR 服务错误 errCode=%s %s' % (err_code, payload.get('errMsg')))
        raise OcrError('OCR 服务重试 %s 次仍失败: %s' % (MAX_RETRY, last_err))
