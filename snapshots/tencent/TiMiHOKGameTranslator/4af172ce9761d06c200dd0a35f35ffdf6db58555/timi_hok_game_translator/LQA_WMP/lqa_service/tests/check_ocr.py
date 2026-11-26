# -*- coding: utf-8 -*-
"""
# @file: check_ocr.py
# @desc: OCR provider 自检工具

独立于 LQA 业务逻辑, 用于快速验证某个 OCR provider 是否能正常工作,
依次检测以下几个层面:
    1. provider 能否成功初始化 (依赖库是否安装、必要配置是否齐全,
       如密钥/服务地址等缺失会在此阶段报错)
    2. 该 provider 是否为 "空实现" (capable=False, 即 OCR_PROVIDER=none),
       是则提示 OCR 为可选能力, 服务仍可启动, 仅错译/文本超框检测会被跳过
    3. 真实端到端识别连通性: 构造一张内置测试图 (写有 "LQA123") 调用
       recognize() 做一次真实识别, 验证本地模型推理 或 远程服务的
       网络连通性/鉴权/返回格式是否正常

用法:
    python tests/check_ocr.py              # 检测当前 OCR_PROVIDER 配置
    python tests/check_ocr.py paddleocr    # 指定 provider (不受环境变量/缓存影响)
    python tests/check_ocr.py --list       # 列出 common/ocr_provider 中已注册的全部 provider

退出码: 0 表示检测通过 (含 [SKIP] 空实现的情况), 1 表示初始化失败或识别调用失败
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.ocr_provider import PROVIDERS, get_provider, OcrError  # noqa: E402


def main():
    args = sys.argv[1:]
    if args and args[0] in ('--list', '-l'):
        print('可选 OCR_PROVIDER:')
        for name in sorted(PROVIDERS):
            print('  -', name)
        return 0

    name = args[0] if args else None
    try:
        provider = get_provider(name=name, cache=False)
    except OcrError as err:
        print('[FAIL] 初始化失败: %s' % err)
        return 1

    print('provider = %s (远程服务: %s)' % (provider.name, provider.remote))
    if not getattr(provider, 'capable', True):
        print('[SKIP] %s' % provider.test_connection())
        print('       OCR 为可选能力, 当前不影响服务启动;'
              '仅「错译」与「文本超文本框」检测会被跳过')
        return 0
    try:
        print('[OK]', provider.test_connection())
        return 0
    except OcrError as err:
        print('[FAIL] %s' % err)
        print('       OCR 为可选能力: 服务仍可启动, 但「错译」与'
              '「文本超文本框」检测将被跳过')
        return 1
    except Exception as err:  # pylint: disable=broad-except
        print('[FAIL] %s: %s' % (type(err).__name__, err))
        return 1


if __name__ == '__main__':
    sys.exit(main())
