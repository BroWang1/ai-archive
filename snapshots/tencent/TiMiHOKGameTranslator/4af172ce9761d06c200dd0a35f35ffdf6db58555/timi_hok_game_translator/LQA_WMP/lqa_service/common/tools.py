# -*- coding: utf-8 -*-
"""
# @file: tools.py
# @desc: 图像数据处理通用工具模块, 提供以下接口:
#        - base64_to_mat: 将 base64 格式的图像数据解码为 OpenCV ndarray 格式,
#                         支持灰度图 (gray)、带 alpha 通道 (alpha) 两种解码模式
#        - mat_to_base64: 将 OpenCV ndarray 格式的图像数据编码 (JPEG) 并转换为 base64 字符串
#        - img_draw_rect: 在图像上绘制标记框, 支持标准矩形框 (4维坐标 x1,y1,x2,y2)
#                         和非标准四边形框 (8维坐标, 4个点) 两种绘制方式, 可自定义颜色和线宽样式
"""
import base64
import cv2
import numpy as np


def base64_to_mat(base64_img, gray=False, alpha=False):
    """ 数据base64转ndarray
    :param base64_img: str, base64 格式的图像数据
    :param gray: bool, 标记是否是灰度图
    :param alpha: bool, 标记数据是否带有 alpha 通道
    :return: ndarray 格式的图像数据
    """
    if base64_img is None:
        return None
    img_b64decode = base64.b64decode(base64_img)
    # np.fromstring 的二进制模式在 numpy>=1.22 已废弃、2.x 中移除, 改用 frombuffer
    img_array = np.frombuffer(img_b64decode, np.uint8)
    if gray:
        trans_type = cv2.IMREAD_GRAYSCALE
    elif alpha:
        trans_type = -1
    else:
        trans_type = cv2.COLOR_BGR2RGB
    img = cv2.imdecode(img_array, trans_type)
    return img


def mat_to_base64(img):
    """ 数据 ndarray 转 base64
    :param img: ndarray, ndarray 格式的图像数据
    :return: base64 格式的图像数据
    """
    if img is None:
        return None
    # ndarray.tostring() 在 numpy 2.x 中已移除, 改用等价的 tobytes()
    image = cv2.imencode('.jpg', img)[1].tobytes()
    base64_img = base64.b64encode(image).decode()
    return base64_img


def img_draw_rect(img, rect, draw_style=((0, 0, 255), 1)):
    """标记图像
    :param img: ndarray, 图像
    :param rect: x1, y1, x2, y2, 标记位置 (标准矩形框), 非标框 4 个点 8 维向量
    :param draw_style: tuple, 绘制样式, 取值 DrawStyle, 包括颜色, 线条 size
    :return: img, 标记后的图像
    """
    if rect:
        if len(rect) == 4:
            x1, y1, x2, y2 = rect
            cv2.rectangle(img, (x1, y1), (x2, y2), draw_style[0], draw_style[1])

        if len(rect) == 8:
            rect_array = np.array(rect)
            rect_reshape = rect_array.reshape(-1, 2, 1)
            cv2.polylines(img, [rect_reshape], isClosed=True, color=draw_style[0], thickness=draw_style[1])  # 红色多边形

    return img
