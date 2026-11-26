# -*- coding: utf-8 -*-
"""
# @file: ocr_provider/cloud.py
# @desc: 云厂商 OCR 适配模块, 提供以下 provider 实现:
#   - TencentCloudOcr (name='tencentcloud')
#       腾讯云通用印刷体识别 GeneralBasicOCR
#       依赖: pip install tencentcloud-sdk-python-ocr
#       相关配置: OCR_SECRET_ID / OCR_SECRET_KEY / OCR_REGION (默认 ap-guangzhou)
#   - BaiduOcr (name='baidu')
#       百度智能云通用文字识别 (含位置信息)
#       相关配置: OCR_API_KEY / OCR_SECRET_KEY
#       内部通过 OAuth2 client_credentials 方式获取 access_token 并缓存 (类变量 _token)
#   - AzureOcr (name='azure')
#       Azure AI Vision Read API
#       相关配置: OCR_HOST (服务 endpoint) / OCR_API_KEY
#
# 这些服务均返回文本内容及对应边界框 (area: [x1,y1,x2,y2]), 满足 LQA 超框检测对
# 文本精确定位的要求, 均为按量计费的远程调用 (remote=True), 批量识别时需注意
# 云厂商侧的成本与 QPS 限制, 避免触发限流或产生高额费用
"""
import json
import logging

import requests

from .base import OcrProvider, OcrError, quad_to_box

logger = logging.getLogger('handle')


class TencentCloudOcr(OcrProvider):
    """腾讯云通用印刷体识别 GeneralBasicOCR

    需要 pip install tencentcloud-sdk-python-ocr
    配置: OCR_SECRET_ID / OCR_SECRET_KEY / OCR_REGION
    """

    name = 'tencentcloud'
    remote = True

    def recognize(self, img_base64, project=None):
        secret_id = self.config.get('secret_id')
        secret_key = self.config.get('secret_key')
        if not (secret_id and secret_key):
            raise OcrError('未配置 OCR_SECRET_ID / OCR_SECRET_KEY')
        try:
            from tencentcloud.common import credential
            from tencentcloud.ocr.v20181119 import ocr_client, models
        except ImportError as err:
            raise OcrError(
                '未安装腾讯云 SDK, 请执行: pip install tencentcloud-sdk-python-ocr'
            ) from err

        try:
            cred = credential.Credential(secret_id, secret_key)
            client = ocr_client.OcrClient(cred, self.config.get('region', 'ap-guangzhou'))
            req = models.GeneralBasicOCRRequest()
            req.from_json_string(json.dumps({'ImageBase64': img_base64}))
            resp = client.GeneralBasicOCR(req)
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('腾讯云 OCR 调用失败: %s' % err) from err

        results = []
        for item in resp.TextDetections or []:
            text = item.DetectedText
            poly = item.Polygon
            if not text:
                continue
            if poly:
                results.append({'area': quad_to_box([(p.X, p.Y) for p in poly]), 'result': text})
            elif item.ItemPolygon:
                p = item.ItemPolygon
                results.append({
                    'area': [p.X, p.Y, p.X + p.Width, p.Y + p.Height],
                    'result': text,
                })
        return results


class BaiduOcr(OcrProvider):
    """百度智能云通用文字识别 (含位置信息)

    配置: OCR_API_KEY / OCR_SECRET_KEY
    """

    name = 'baidu'
    remote = True

    TOKEN_URL = 'https://aip.baidubce.com/oauth/2.0/token'
    OCR_API = 'https://aip.baidubce.com/rest/2.0/ocr/v1/general'

    _token = None

    def _get_token(self):
        if BaiduOcr._token:
            return BaiduOcr._token
        api_key = self.config.get('api_key')
        secret_key = self.config.get('secret_key')
        if not (api_key and secret_key):
            raise OcrError('未配置 OCR_API_KEY / OCR_SECRET_KEY')
        try:
            resp = requests.post(self.TOKEN_URL, params={
                'grant_type': 'client_credentials',
                'client_id': api_key,
                'client_secret': secret_key,
            }, timeout=30)
            BaiduOcr._token = resp.json()['access_token']
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('百度 OCR 获取 token 失败: %s' % err) from err
        return BaiduOcr._token

    def recognize(self, img_base64, project=None):
        token = self._get_token()
        try:
            resp = requests.post(
                self.OCR_API,
                params={'access_token': token},
                data={'image': img_base64, 'recognize_granularity': 'small'},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=int(self.config.get('timeout', 60)),
            )
            payload = resp.json()
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('百度 OCR 调用失败: %s' % err) from err

        if 'error_code' in payload:
            raise OcrError('百度 OCR 错误 %s: %s' % (payload['error_code'], payload.get('error_msg')))

        results = []
        for item in payload.get('words_result') or []:
            text = item.get('words')
            loc = item.get('location') or {}
            if not text or not loc:
                continue
            x, y = int(loc.get('left', 0)), int(loc.get('top', 0))
            w, h = int(loc.get('width', 0)), int(loc.get('height', 0))
            results.append({'area': [x, y, x + w, y + h], 'result': text})
        return results


class AzureOcr(OcrProvider):
    """Azure AI Vision Read API

    配置: OCR_HOST(endpoint) / OCR_API_KEY
    """

    name = 'azure'
    remote = True

    def recognize(self, img_base64, project=None):
        import base64 as _b64

        endpoint = (self.config.get('host') or '').rstrip('/')
        api_key = self.config.get('api_key')
        if not (endpoint and api_key):
            raise OcrError('未配置 OCR_HOST(endpoint) / OCR_API_KEY')
        url = '%s/computervision/imageanalysis:analyze' % endpoint
        try:
            resp = requests.post(
                url,
                params={'features': 'read', 'api-version': '2024-02-01'},
                headers={
                    'Ocp-Apim-Subscription-Key': api_key,
                    'Content-Type': 'application/octet-stream',
                },
                data=_b64.b64decode(img_base64),
                timeout=int(self.config.get('timeout', 60)),
            )
            payload = resp.json()
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('Azure OCR 调用失败: %s' % err) from err

        if resp.status_code != 200:
            raise OcrError('Azure OCR 返回 HTTP %s: %s' % (resp.status_code, payload))

        results = []
        blocks = (payload.get('readResult') or {}).get('blocks') or []
        for block in blocks:
            for line in block.get('lines') or []:
                text = line.get('text')
                poly = line.get('boundingPolygon') or []
                if not text or not poly:
                    continue
                results.append({
                    'area': quad_to_box([(p['x'], p['y']) for p in poly]),
                    'result': text,
                })
        return results
