# -*- coding: utf-8 -*-
"""
# @file: image_processing.py
# @desc: 图像前景区域提取相关数据处理模块, 提供以下枚举和 ImageProcessing 类:
#        - ZeroType: 坐标原点类型 (左上角/左下角)
#        - PositionType: 位置表示类型 (像素坐标/比例坐标)
#        - ImageProcessing.coordinate_trans: 根据指定的坐标原点 (zero_type) 和表示方式 (position_type),
#                     对矩形区域坐标 (x1,y1,x2,y2) 进行转换
#        - ImageProcessing.get_extraction_rect: 根据 alpha 通道图像及阈值, 扫描计算出非透明
#                     前景内容的最小外接矩形区域, 并处理边界坐标
#        - ImageProcessing.single_image_extraction: 对单张四通道 (RGBA) 图像提取前景区域,
#                     当图像整体透明度偏低时自适应调整阈值, 再按指定坐标原点/表示方式输出结果
#        - ImageProcessing.image_extraction: 批量处理多张图像 (以图像名为 key 的字典),
#                     逐一调用 single_image_extraction 提取前景区域并汇总返回
"""
from enum import Enum
import cv2
import numpy as np
from common.tools import base64_to_mat


class ZeroType(Enum):
    """坐标原点类型"""
    LEFT_TOP = 0  # 左上角为原点
    LEFT_BOTTOM = 1  # 左下角为原点


class PositionType(Enum):
    """位置表示类型"""
    PIXEL = 0  # 像素坐标
    SCALE = 1  # 比例坐标


class ImageProcessing:
    """图形处理类"""

    @staticmethod
    def coordinate_trans(rect, h, w, zero_type=0, position_type=0):
        """  坐标变换, 根据 zero_type 和 position_type 转换坐标
        :param rect: tuple 或者 list, 四维向量表示区域, 左上角右下角双点定位 (x1, y1, x2, y2)
        :param h: int, 图像高度
        :param w: int, 图像宽度
        :param zero_type: int, 标记坐标原点方式, 默认 0, 取值 ZeroType
        :param position_type: int, 标记位置表示方式, 默认 0, 取值 PositionType
        :return: 转化后的坐标 (x1, y1, x2, y2)
        """
        if zero_type == ZeroType.LEFT_TOP.value:
            x1, y1, x2, y2 = rect
        elif zero_type == ZeroType.LEFT_BOTTOM.value:
            x1, y1, x2, y2 = rect
            y1 = h - y1
            y2 = h - y2
        else:
            return None
        if position_type == PositionType.PIXEL.value:
            return int(x1), int(y1), int(x2), int(y2)
        elif position_type == PositionType.SCALE.value:
            x1 = round(x1/w, 4)
            y1 = round(y1/h, 4)
            x2 = round(x2/w, 4)
            y2 = round(y2/h, 4)
            return x1, y1, x2, y2
        else:
            return None

    @staticmethod
    def get_extraction_rect(img_alpha, alpha_t):
        """ 计算前景提取区域
        :param img_alpha: ndarray, alpha通道图像数据
        :param alpha_t: int, alpha通道数据阈值
        :return: rect, 提取的位置
        """
        h, w = img_alpha.shape
        h_list = []
        w_list = []
        for j in range(h):
            for i in range(w):
                if img_alpha[j, i] > alpha_t:
                    h_list.append(j)
                    w_list.append(i)
        if len(w_list) > 0 and len(h_list) > 0:
            x1 = np.min(w_list)
            y1 = np.min(h_list)
            x2 = np.max(w_list)
            y2 = np.max(h_list)
        else:
            x1 = 0
            y1 = 0
            x2 = w
            y2 = h
        # 处理边界坐标
        if x1 + 1 == 1:
            x1 = 0
        if y1 + 1 == 1:
            y1 = 0
        if x2 + 1 >= w:
            x2 = w
        if y2 + 1 >= h:
            y2 = h
        rect = (x1, y1, x2, y2)
        return rect

    @staticmethod
    def single_image_extraction(img_base64, zero_type=0, position_type=0, alpha_t=50):
        """ 单图像前景提取
        :param img_base64: str, base64 格式的图像数据
        :param zero_type: int, 标记坐标原点方式, 支持左下角和左上角原点
        :param position_type: int, 标记位置表示方式, 支持像素和小数比例表示
        :param alpha_t: int, alpha通道数据阈值
        :return: {图像名: 图像位置，...}
        """
        rect_res = None
        if img_base64 is None:
            return rect_res
        img = base64_to_mat(img_base64, alpha=True)
        if img.shape[2] != 4:
            return rect_res
        # 提取 alpha 通道数据
        _, _, _, a = cv2.split(img)
        h, w = a.shape
        max_a = max([max(item) for item in a.tolist()])
        a_t = alpha_t
        if max_a < a_t:
            a_t = int(max_a / 3 * 2)
        rect = ImageProcessing.get_extraction_rect(a, a_t)
        # 根据坐标原点和位置标记类型参数进行坐标转化
        rect_res = ImageProcessing.coordinate_trans(rect, h, w, zero_type=zero_type, position_type=position_type)
        if not rect_res:
            rect_res = rect
        return rect_res

    @staticmethod
    def image_extraction(img_base64, zero_type=0, position_type=0, alpha_t=50):
        """ 提取图像前景的实际区域, 支持多张图片批量处理 (四通道图像)
        :param img_base64: dict, 待处理的图像数据 {图像名: base64 图像数据, ...}
        :param zero_type: int, 标记坐标原点方式, 默认 0, 取值 ZeroType
        :param position_type: int, 标记位置表示方式, 默认0, 取值 PositionType
        :param alpha_t: int, alpha 通道数据阈值
        :return: 提取后的结果 {图像名: 图像位置, ...}
        """
        res = {
            "image_extraction": {}
        }
        if img_base64 is None:
            return res
        for item in img_base64:
            rect_res = ImageProcessing.single_image_extraction(img_base64[item],
                                                               zero_type=zero_type,
                                                               position_type=position_type,
                                                               alpha_t=alpha_t)
            if rect_res:
                res['image_extraction'].update({item: rect_res})
        return res
