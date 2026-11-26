# -*- coding: utf-8 -*-
"""
# @file: ocr_provider/local_engines.py
# @desc: 其他可离线部署的 OCR 引擎适配模块, 提供以下三个 provider 实现:
#   - EasyOcr (name='easyocr')
#       开源 OCR 引擎, 支持 80+ 语种, 识别结果为四点框
#       依赖: pip install easyocr
#       相关配置: OCR_LANG (逗号分隔的语言列表, 默认 ch_sim,en)、OCR_USE_GPU (是否启用 GPU)
#       引擎以类变量缓存 (_reader), 同进程内仅初始化一次
#   - RapidOcr (name='rapidocr', 默认 provider)
#       PaddleOCR 模型的 ONNXRuntime 推理版, 无需安装 paddle 依赖, 体积小、启动快
#       依赖: pip install rapidocr-onnxruntime
#       引擎以类变量缓存 (_engine), 同进程内仅初始化一次
#   - TesseractOcr (name='tesseract')
#       开源老牌 OCR 引擎
#       依赖: pip install pytesseract, 并需在系统中安装 tesseract 可执行程序及对应语言包
#       相关配置: OCR_TESSERACT_CMD (tesseract 可执行文件路径, 未加入 PATH 时需指定)、
#                 OCR_LANG (识别语言, 默认 chi_sim+eng)
#       注意: 对游戏 UI 这类复杂背景、艺术字体的识别率明显低于 PaddleOCR,
#            仅建议在简单纯色背景场景下使用
#
# 通过环境变量 OCR_PROVIDER 设置为对应 name 值 (easyocr/rapidocr/tesseract) 以启用相应实现
"""
import logging

from .base import OcrProvider, OcrError, quad_to_box, base64_to_ndarray

logger = logging.getLogger('handle')


class EasyOcr(OcrProvider):
    """EasyOCR (开源, 80+ 语种, 返回四点框)

    pip install easyocr
    """

    name = 'easyocr'
    remote = False

    _reader = None

    def _get_reader(self):
        if EasyOcr._reader is not None:
            return EasyOcr._reader
        try:
            import easyocr
        except ImportError as err:
            raise OcrError('未安装 EasyOCR, 请执行: pip install easyocr') from err
        langs = [x.strip() for x in str(self.config.get('lang', 'ch_sim,en')).split(',') if x.strip()]
        use_gpu = str(self.config.get('use_gpu', 'false')).lower() == 'true'
        EasyOcr._reader = easyocr.Reader(langs, gpu=use_gpu, verbose=False)
        logger.info('EasyOCR 引擎已加载 langs=%s gpu=%s', langs, use_gpu)
        return EasyOcr._reader

    def recognize(self, img_base64, project=None):
        reader = self._get_reader()
        img = base64_to_ndarray(img_base64)
        try:
            raw = reader.readtext(img)
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('EasyOCR 识别失败: %s' % err) from err
        results = []
        for item in raw or []:
            try:
                points, text = item[0], item[1]
            except (IndexError, TypeError):
                continue
            if not text:
                continue
            results.append({'area': quad_to_box(points), 'result': text})
        return results


class RapidOcr(OcrProvider):
    """RapidOCR (PaddleOCR 模型的 ONNXRuntime 推理版, 无需 paddle 依赖, 体积小)

    pip install rapidocr-onnxruntime
    """

    name = 'rapidocr'
    remote = False

    _engine = None

    def _get_engine(self):
        if RapidOcr._engine is not None:
            return RapidOcr._engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as err:
            raise OcrError('未安装 RapidOCR, 请执行: pip install rapidocr-onnxruntime') from err
        RapidOcr._engine = RapidOCR()
        logger.info('RapidOCR 引擎已加载')
        return RapidOcr._engine

    def recognize(self, img_base64, project=None):
        engine = self._get_engine()
        img = base64_to_ndarray(img_base64)
        try:
            raw, _elapse = engine(img)
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('RapidOCR 识别失败: %s' % err) from err
        results = []
        for item in raw or []:
            try:
                points, text = item[0], item[1]
            except (IndexError, TypeError):
                continue
            if not text:
                continue
            results.append({'area': quad_to_box(points), 'result': text})
        return results


class TesseractOcr(OcrProvider):
    """Tesseract (开源老牌引擎)

    pip install pytesseract 并安装 tesseract 可执行程序与语言包
    注意: 对游戏 UI 这类复杂背景、艺术字体的识别率明显低于 PaddleOCR,
    仅建议在简单纯色背景场景使用
    """

    name = 'tesseract'
    remote = False

    def recognize(self, img_base64, project=None):
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as err:
            raise OcrError('未安装 pytesseract, 请执行: pip install pytesseract') from err

        cmd = self.config.get('tesseract_cmd')
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        lang = self.config.get('lang', 'chi_sim+eng')
        img = base64_to_ndarray(img_base64)
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=Output.DICT)
        except Exception as err:  # pylint: disable=broad-except
            raise OcrError('Tesseract 识别失败: %s' % err) from err

        results = []
        count = len(data.get('text', []))
        for i in range(count):
            text = (data['text'][i] or '').strip()
            if not text:
                continue
            try:
                conf = float(data['conf'][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            x, y = int(data['left'][i]), int(data['top'][i])
            w, h = int(data['width'][i]), int(data['height'][i])
            results.append({'area': [x, y, x + w, y + h], 'result': text})
        return results
