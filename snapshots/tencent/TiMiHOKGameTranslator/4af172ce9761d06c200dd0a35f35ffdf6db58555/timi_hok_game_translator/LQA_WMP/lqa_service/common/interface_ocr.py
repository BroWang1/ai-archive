# -*- coding: utf-8 -*-
"""
# @file: interface_ocr.py
# @desc: OCR 能力统一接口模块, 对接 common/ocr_provider 实现, 提供以下能力:
#        - ocr_available: 检测当前 OCR 能力是否可用 (带缓存), 未配置 OCR 时返回 False 而非报错,
#                         便于调用方据此降级处理
#        - ocr: 统一 OCR 识别入口, 具体识别逻辑由 OCR_PROVIDER 配置决定 (见 ocr_provider 模块),
#               OCR 为可选能力, 未配置/调用失败时捕获异常并返回 None, 由调用方判空后
#               跳过依赖 OCR 的检测项, 而非视为服务错误
#        - find_lcsubstr: 查找两个字符串的最长公共子串 (动态规划)
#        - find_lcseque: 查找两个字符串的最长公共子序列 (动态规划+回溯),
#                        可用于比对 OCR 识别文本与标准文本的相似度
"""
import traceback
from common.log import logger
from common.ocr_provider import get_provider, is_available, OcrError


def find_lcsubstr(s1, s2):
    """ 查找最长公共子串
    :param s1: str, 字符串
    :param s2: str, 字符串
    :return: 最长公共子串
    """
    m = [[0 for i in range(len(s2) + 1)] for j in range(len(s1) + 1)]
    mmax = 0
    p = 0
    for i in range(len(s1)):
        for j in range(len(s2)):
            if s1[i] == s2[j]:
                m[i + 1][j + 1] = m[i][j] + 1
                if m[i + 1][j + 1] > mmax:
                    mmax = m[i + 1][j + 1]
                    p = i + 1
    return s1[p - mmax:p], mmax


def find_lcseque(s1, s2):
    """查找最长公共子序列
    :param s1: str, 字符串
    :param s2: str, 字符串
    :return: 最长公共子序列
    """
    # 生成字符串长度加 1 的 0 矩阵, m 用来保存对应位置匹配的结果
    m = [[0 for x in range(len(s2) + 1)] for y in range(len(s1) + 1)]
    # d 用来记录转移方向
    d = [[None for x in range(len(s2) + 1)] for y in range(len(s1) + 1)]

    for p1 in range(len(s1)):
        for p2 in range(len(s2)):
            if s1[p1] == s2[p2]:  # 字符匹配成功, 则该位置的值为左上方的值加 1
                m[p1 + 1][p2 + 1] = m[p1][p2] + 1
                d[p1 + 1][p2 + 1] = 'ok'
            elif m[p1 + 1][p2] > m[p1][p2 + 1]:  # 左值大于上值, 则该位置的值为左值, 并标记回溯时的方向
                m[p1 + 1][p2 + 1] = m[p1 + 1][p2]
                d[p1 + 1][p2 + 1] = 'left'
            else:  # 上值大于左值, 则该位置的值为上值, 并标记方向 up
                m[p1 + 1][p2 + 1] = m[p1][p2 + 1]
                d[p1 + 1][p2 + 1] = 'up'
    (p1, p2) = (len(s1), len(s2))
    s = []
    while m[p1][p2]:  # 不为 None 时
        c = d[p1][p2]
        if c == 'ok':  # 匹配成功, 插入该字符, 并向左上角找下一个
            s.append(s1[p1 - 1])
            p1 -= 1
            p2 -= 1
        if c == 'left':  # 根据标记, 向左找下一个
            p2 -= 1
        if c == 'up':  # 根据标记, 向上找下一个
            p1 -= 1
    s.reverse()
    return ''.join(s), len(s)


def ocr_available(force=False):
    """OCR 能力是否可用 (带缓存, 未配置 OCR 时返回 False 而非报错)

    :param force: True 时忽略缓存重新探测
    :return: (bool, str) 是否可用、描述信息
    """
    return is_available(force=force)


def ocr(img_base64, location=None, project_id=19998, project=None):
    """OCR 识别接口 (具体实现由 OCR_PROVIDER 决定, 见 common/ocr_provider)

    OCR 为可选能力: 未配置或不可用时返回 None, 调用方需判空并跳过
    依赖 OCR 的检测项, 而非视作错误

    :param img_base64: str, base64 格式的图像数据
    :param location: list, 保留参数, 当前实现统一识别整图后再按标准框过滤
    :param project_id: int, 保留参数, cvtest provider 通过配置项传入
    :param project: str, 调用方项目标识 (部分服务用于鉴权/路由)
    :return: 识别结果 [{"area": [x1, y1, x2, y2], "result": '{text}'}, ..., {}]
             失败或未配置时返回 None (调用方需判空)
    """
    try:
        return get_provider().recognize(img_base64, project=project)
    except OcrError as ex:
        # 配置缺失/鉴权失败/服务不可用等可预期错误, 打印明确原因便于排障
        logger.error('OCR 调用失败: %s', ex)
        return None
    except Exception as ex:  # pylint: disable=broad-except
        logger.error(ex)
        logger.error(traceback.format_exc())
        return None
