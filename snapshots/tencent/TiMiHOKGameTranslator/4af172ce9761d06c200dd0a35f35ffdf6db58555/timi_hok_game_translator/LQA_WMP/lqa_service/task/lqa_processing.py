# -*- coding: utf-8 -*-
"""
# @file: lqa_processing.py
# @desc: LQA 本地化检测相关数据预处理工具模块, 提供 LqaProcessing 类实现以下能力:
#        - judge_rectangle/coordinate_trans: 判断四点坐标是否为标准矩形框, 并将左下角为原点的
#                     坐标体系转换为图像坐标系 (x1,y1,x2,y2 或 四点坐标)
#        - is_dirty_text/detect_gt_text_locations/detect_gt_image_locations: 提取标准文本框/
#                     图像框位置信息，过滤尺寸异常、越界、空文本等脏数据，并标记非标准 (非矩形) 框
#        - draw_gt_locations: 在图像上绘制标准文本框/图像框及非标准框的标注样式
#        - detect_ocr_data/filter_text_data/get_join_ocr_result: 调用 OCR 识别图像文本,
#                     并按标准文本框归属过滤、聚合 OCR 结果
#        - overlap/rect_collision_detection: 矩形碰撞检测, 判断两个矩形是否存在重叠/碰撞关系
#        - judge_overlap_with_text_i/merge_and_update_overlap/get_overlap_group_data/
#          save_single_group_classify_res/classify_text_location_overlap: 对所有文本框两两判断
#                     重叠关系并分组合并, 将文本框分类为独立文本框和重叠文本框组 (取最小外接矩形)
#        - judge_ocr_location_extend/align_single_ocr_location/align_ocr_location: 根据 OCR
#                     识别结果对文本框区域进行扩展判断和位置微调校准, 提升文本定位精度
#        - shrink_image_box: 基于连通域分析, 将图像框收缩到实际前景内容的最小外接矩形
"""
import math
import cv2
import numpy as np
from common.interface_ocr import ocr
from common.tools import mat_to_base64
from task.lqa_config import DrawStyle
from common.tools import img_draw_rect


class LqaProcessing:
    """lqa 数据预处理类"""

    @staticmethod
    def judge_rectangle(location_dict):
        """判断是否是标准文本框
        :param location_dict: dict, 位置信息
        :param height: int, 图像高度
        :return: 判断是否是标准矩形框
        """
        x1 = int(location_dict["corners"][0]["x"])
        y1 = int(location_dict["corners"][0]["y"])
        x2 = int(location_dict["corners"][1]["x"])
        y2 = int(location_dict["corners"][1]["y"])
        x3 = int(location_dict["corners"][2]["x"])
        y3 = int(location_dict["corners"][2]["y"])
        x4 = int(location_dict["corners"][3]["x"])
        y4 = int(location_dict["corners"][3]["y"])
        if x1 != x2 or x3 != x4 or y1 != y4 or y2 != y3:
            return False
        return True

    @staticmethod
    def coordinate_trans(location_dict, height, is_rectangle=True):
        """坐标变换, 提供的标准数据 text 和 image 的矩形框位置信息是以左下角为原点
        :param location_dict: dict, 位置信息
        :param height: int, 图像高度
        :param is_rectangle: bool, 默认标准文本框, 返回思维向量, 否则保持原 4 个点坐标
        :return: 转化后的位置坐标 (x1, y1, x2, y2)
        """
        if is_rectangle:
            x1 = int(location_dict["corners"][1]["x"])
            y1 = height - int(location_dict["corners"][1]["y"])
            x2 = int(location_dict["corners"][3]["x"])
            y2 = height - int(location_dict["corners"][3]["y"])
            trans_location = (x1, y1, x2, y2)
        else:
            x1 = int(location_dict["corners"][0]["x"])
            y1 = height - int(location_dict["corners"][0]["y"])
            x2 = int(location_dict["corners"][1]["x"])
            y2 = height - int(location_dict["corners"][1]["y"])
            x3 = int(location_dict["corners"][2]["x"])
            y3 = height - int(location_dict["corners"][2]["y"])
            x4 = int(location_dict["corners"][3]["x"])
            y4 = height - int(location_dict["corners"][3]["y"])
            trans_location = (x1, y1, x2, y2, x3, y3, x4, y4)
        return trans_location

    @staticmethod
    def is_dirty_text(text_location, text_location_dict, height, width):
        """判断是否是脏文本框 (尺寸不合理、无文本等)
        :param text_location: list, 文本位置
        :param text_location_dict: dict, 文本对应信息
        :param height: int, 图像高
        :param width: int, 图像宽
        :return: bool, 是否是脏数据
        """
        w = text_location[2] - text_location[0]
        h = text_location[3] - text_location[1]
        # 尺度太小
        if w < 13 or h < 13:
            return True
        # 位置不合理
        for i in range(4):
            if text_location[i] < 0:
                return True
        if text_location[0] > width or text_location[2] > width:
            return True
        if text_location[1] > height or text_location[3] > height:
            return True
        # 无文本内容
        text_str = text_location_dict.get("textStr")
        if not text_str or text_str == '':
            return True
        return False

    @staticmethod
    def detect_gt_text_locations(img, text_location_list, preprocessing=False):
        """ 提取所有标准文本框的位置信息, 进行坐标转换
        :param img: ndarray, 图像
        :param text_location_list: list, 标准文本框信息
        :return: gt_text_info, dict, {'gt_text_locations': 文本框信息, 'dirty_text_ids': 脏文本框id,
        'non_rectangle_ids': 非标框, preprocessing_err 预检测异常 {index: [error类型id列表]}}
        """
        # 所有标准文本信息
        height, width = img.shape[:2]
        gt_text_info = {'gt_text_locations': [], 'dirty_text_ids': [], 'non_rectangle_ids': [],
                        'preprocessing_errs': {}}
        text_list_temp = []
        for i in range(len(text_location_list)):
            text_location_dict = text_location_list[i]
            if text_location_dict not in text_list_temp:
                text_list_temp.append(text_location_dict)
            else:
                gt_text_info['dirty_text_ids'].append(i)  # 去重
            is_rectangle = LqaProcessing.judge_rectangle(text_location_dict)
            text_location = LqaProcessing.coordinate_trans(text_location_dict, height, is_rectangle)
            if is_rectangle:
                # 过滤脏数据
                is_dirty = LqaProcessing.is_dirty_text(text_location, text_location_dict, height, width)
                if is_dirty and i not in gt_text_info['dirty_text_ids']:
                    gt_text_info['dirty_text_ids'].append(i)
            else:
                # 过滤非标框
                gt_text_info['non_rectangle_ids'].append(i)
            gt_text_info['gt_text_locations'].append(text_location)

            # 预检测异常
            if preprocessing and text_location_dict.get('preprocessing_err'):
                gt_text_info['preprocessing_errs'].update({i: text_location_dict['preprocessing_err']})
        return gt_text_info

    @staticmethod
    def detect_gt_image_locations(img, image_location_list):
        """提取所有标准图像框的位置信息, 进行坐标转换
        :param img: ndarray, 图像
        :param image_location_list: list, 标准图像框信息
        :return: gt_image_info, dict, {'gt_image_locations': 图像框信息, 'dirty_text_ids': 脏图像框 id}
        """
        height, width = img.shape[:2]
        gt_image_info = {'gt_image_locations': [], 'dirty_image_ids': []}
        image_list_temp = []
        for i in range(len(image_location_list)):
            # image 框
            image_location_dict = image_location_list[i]
            if image_location_dict not in image_list_temp:
                image_list_temp.append(image_location_dict)
            else:
                gt_image_info['dirty_image_ids'].append(i)  # 去重
            image_location = LqaProcessing.coordinate_trans(image_location_dict, height)
            if image_location[2] - image_location[0] < 13 or image_location[3] - image_location[1] < 13 \
                    or image_location[2] < 0 or image_location[3] < 0 \
                    or image_location[0] > width or image_location[1] > height:
                gt_image_info['dirty_image_ids'].append(i)
            gt_image_info['gt_image_locations'].append(image_location)
        return gt_image_info

    @staticmethod
    def draw_gt_locations(rect_img, gt_text_info, gt_image_info):
        """绘制标记标准信息, 包括文本框和图像框
        :param rect_img: ndarray, 图像
        :param gt_text_info: dict, 标准文本框信息
        :param gt_image_info: dict, 标准图像框信息
        :return: 标记后的 rect_img
        """
        gt_text_locations = gt_text_info['gt_text_locations']
        dirty_text_ids = gt_text_info['dirty_text_ids']
        non_rectangle_ids = gt_text_info['non_rectangle_ids']
        for i in range(len(gt_text_locations)):
            if i not in dirty_text_ids and i not in non_rectangle_ids:  # 矩形
                rect_img = img_draw_rect(rect_img, gt_text_locations[i], DrawStyle.GT_TEXT.value)
            if i in non_rectangle_ids:  # 非矩形
                rect_img = img_draw_rect(rect_img, gt_text_locations[i], DrawStyle.NON_RECTANGLE.value)
        gt_image_locations = gt_image_info['gt_image_locations']
        dirty_image_ids = gt_image_info['dirty_image_ids']
        for i in range(len(gt_image_locations)):
            if i not in dirty_image_ids:
                rect_img = img_draw_rect(rect_img, gt_image_locations[i], DrawStyle.GT_IMG.value)
        return rect_img

    @staticmethod
    def detect_ocr_data(img, gt_text_info, project=None):
        """检测图像中所有 ocr, 同时过滤不属于标准框内的结果
        :param img: ndarray, 图像
        :param gt_text_info: dict, 标准文本框信息
        :param project: str, 指定调用项目
        :return: all_ocr_dict, 全图 OCR 识别结果
        """
        # 标准信息
        gt_text_locations = gt_text_info['gt_text_locations']
        dirty_text_ids = gt_text_info['dirty_text_ids']
        non_rectangle_ids = gt_text_info['non_rectangle_ids']
        # 所有检测文本信息
        all_ocr_dict = {}
        text_data = ocr(mat_to_base64(img), project=project)
        if not text_data:  # OCR 未配置/不可用: 返回空结果, 由调用方跳过相关检测
            return all_ocr_dict
        for text_one in text_data:
            ocr_result = text_one["result"]
            if ocr_result and len(ocr_result) <= 0:
                continue
            ocr_x1, ocr_y1, ocr_x2, ocr_y2 = text_one["area"]
            center_x = (ocr_x1 + ocr_x2) / 2
            center_y = (ocr_y1 + ocr_y2) / 2
            for i in range(len(gt_text_locations)):
                if i in dirty_text_ids or i in non_rectangle_ids:  # 脏标准框直接跳过
                    continue
                x1, y1, x2, y2 = gt_text_locations[i]
                if x1 < center_x < x2 and y1 < center_y < y2:
                    if ocr_result not in all_ocr_dict:
                        all_ocr_dict[ocr_result] = []
                    all_ocr_dict[ocr_result].append((ocr_x1, ocr_y1, ocr_x2, ocr_y2))
                    break
        return all_ocr_dict

    @staticmethod
    def filter_text_data(gt_text_info, text_location_list):
        """直接从检测文件中提取 ocr 相关信息, 不需要检测
        :param gt_text_info: 预处理的标准数据, 包括位置信息, 过滤脏数据的索引
        :param text_location_list: list, 半监督预处理后的文本信息
        :return: all_ocr_dict, 全图文本内容
        """
        all_ocr_dict = {}
        gt_text_locations = gt_text_info['gt_text_locations']
        for text_index in range(len(gt_text_locations)):
            if text_index in gt_text_info['dirty_text_ids']:  # 脏标准框数据跳过
                continue
            x1, y1, x2, y2 = gt_text_locations[text_index]
            text_location_dict = text_location_list[text_index]
            text_str = text_location_dict.get("textStr")
            all_ocr_dict[text_str].append((x1, y1, x2, y2))
        return all_ocr_dict

    @staticmethod
    def overlap(rect1, rect2, x_t=10, y_t=5):
        """矩形碰撞检测, 有重叠交集为 True
        :param rect1: 矩形框1位置, x1,y1,x2,y2 格式
        :param rect2: 矩形框2位置, x1,y1,x2,y2 格式
        :param x_t: int, 重叠区域 x方向阈值
        :param y_t: int, 重叠区域 y方向阈值
        :return: bool,是否重叠
                 ratio, str: 和 rect2 的重叠比率
                 (sub_x, sub_y): 和 rect2 的重叠比率
        """
        # 重叠区域
        x_min = max(rect1[0], rect2[0])
        y_min = max(rect1[1], rect2[1])
        x_max = min(rect1[2], rect2[2])
        y_max = min(rect1[3], rect2[3])
        ratio = 0
        sub_x = 0
        sub_y = 0
        if x_max - x_min > x_t and y_max - y_min > y_t:
            ratio = (x_max - x_min) * (y_max - y_min) / (rect2[2] - rect2[0]) / (rect2[3] - rect2[1])
            sub_x = abs((x_max - x_min) - (rect2[2] - rect2[0]))
            sub_y = abs((y_max - y_min) - (rect2[3] - rect2[1]))
            return True, ratio, (sub_x, sub_y)
        else:
            return False, ratio, (sub_x, sub_y)

    @staticmethod
    def judge_overlap_with_text_i(overlap_dict, text_i, text_location_list, dirty_text_ids):
        """判断与 text_i 重叠的文本框, 保存在字典里 (只判断索引大于text_i, 减少重复计算)
        :param overlap_dict: dict, 保存的重叠关系结果
        :param text_i: int, 当前处理的文本框索引
        :param text_location_list: list, 文本位置信息
        :param dirty_text_ids: list, 脏文本框索引列表
        :return: 更新的overlap_dict
        """

        # 存储分类结果: 分别标记独立文本框和重叠文本框位置、索引
        cnt = len(text_location_list)
        overlap_dict[text_i] = [text_i]
        for j in range(cnt):
            if j > text_i and j not in dirty_text_ids:
                # 重叠判断
                is_overlap, _, _ = LqaProcessing.overlap(text_location_list[text_i], text_location_list[j])
                if is_overlap and j not in overlap_dict[text_i]:
                    overlap_dict[text_i].append(j)
        return overlap_dict

    @staticmethod
    def merge_and_update_overlap(temp_overlap_list, i_overlaps):
        """判断是否是一组重叠文本框, 合并更新分组 id
        :param temp_overlap_list: list, 存储分组结果
        :param i_overlaps: list, 第 i 个文本框判断的结果
        :return: 更新后的 temp_overlap_list
        """
        in_others = False
        for k in i_overlaps:
            for j in range(len(temp_overlap_list)):
                if k in temp_overlap_list[j]:
                    in_others = True
                    temp_overlap_list[j].extend(i_overlaps)
                    break
            if in_others:
                break
        if in_others:
            i_overlaps = []
        temp_overlap_list.append(i_overlaps)
        return temp_overlap_list

    @staticmethod
    def get_overlap_group_data(gt_text_info):
        """获得分组的重叠文本框数据
        :param gt_text_info: dict, 标准文本信息
        :return: temp_overlap_dict, dict, 重叠文本框分组数据
        """
        text_location_list = gt_text_info['gt_text_locations']
        dirty_text_ids = gt_text_info['dirty_text_ids']
        non_rectangle_ids = gt_text_info['non_rectangle_ids']
        cnt = len(text_location_list)

        # 判断文本框与后面文本框的重叠关系
        overlap_dict = {}
        for i in range(cnt):
            if i in dirty_text_ids or i in non_rectangle_ids:  # 脏数据过滤, 便于后续检测, 无需处理
                continue
            overlap_dict = LqaProcessing.judge_overlap_with_text_i(overlap_dict, i, text_location_list, dirty_text_ids)

        # 合并文本框结果
        temp_overlap_list = []
        for i in range(cnt):
            if i not in overlap_dict:
                temp_overlap_list.append([])  # 脏数据占位, 保留索引
                continue
            i_overlaps = overlap_dict[i]
            if len(temp_overlap_list) == 0:
                temp_overlap_list.append(i_overlaps)
            else:
                # 判断、合并同组文本框
                temp_overlap_list = LqaProcessing.merge_and_update_overlap(temp_overlap_list, i_overlaps)

        temp_overlap_dict = {}
        for i in range(cnt):
            if len(temp_overlap_list[i]) > 0:
                temp_overlap_dict[i] = list(set(temp_overlap_list[i]))
        return temp_overlap_dict

    @staticmethod
    def save_single_group_classify_res(single_group_overlap, current_index, text_location_list,
                                       classify_text_location_res):
        """根据一组文本框分类结果, 结果格式化和保存
        :param single_group_overlap: dict, 单组重叠文本框 (保存的是对应文本框 index)
        :param current_index: int, 当前处理的文本索引
        :param text_location_list: list, 文本位置信息
        :param classify_text_location_res: dict, 分类结果
        :return:
        """
        x_min_list = []
        y_min_list = []
        x_max_list = []
        y_max_list = []
        for item in single_group_overlap:
            x1, y1, x2, y2 = text_location_list[item]
            x_min_list.append(x1)
            y_min_list.append(y1)
            x_max_list.append(x2)
            y_max_list.append(y2)

        # 独立文本框
        if len(x_min_list) == 1:
            classify_text_location_res['independent'].append((x_min_list[0], y_min_list[0], x_max_list[0],
                                                              y_max_list[0]))
            classify_text_location_res['independent_id'].append(current_index)
        # 有重叠的文本框合并, 最小外接矩形
        elif len(x_min_list) > 1:
            group_x1 = np.min(x_min_list)
            group_y1 = np.min(y_min_list)
            group_x2 = np.max(x_max_list)
            group_y2 = np.max(y_max_list)
            classify_text_location_res['overlap_group'].append((group_x1, group_y1, group_x2, group_y2))
            classify_text_location_res['overlap_group_id'].append(single_group_overlap)
        return classify_text_location_res

    @staticmethod
    def classify_text_location_overlap(gt_text_info):
        """根据文本框是否有重叠进行分类
        :param gt_text_info: dict, 提取的标准文本框信息
        :return: dict, classify_text_location_res, 文本框分类结果信息
        """
        # 存储分类结果: 分别标记独立文本框和重叠文本框位置、索引
        classify_text_location_res = {'independent': [], 'independent_id': [],
                                      'overlap_group': [], 'overlap_group_id': []}
        text_location_list = gt_text_info['gt_text_locations']
        dirty_text_ids = gt_text_info['dirty_text_ids']

        # 是否有文本框需要判断
        cnt = len(text_location_list)
        if cnt - len(dirty_text_ids) <= 0:
            return classify_text_location_res
        # 获得分组的重叠文本框数据
        temp_overlap_dict = LqaProcessing.get_overlap_group_data(gt_text_info)

        # 按照分组的文本框结果, 保存格式化分类结果 (重叠文本框合并处理)
        for i in temp_overlap_dict:
            single_group_overlap = temp_overlap_dict[i]
            if len(single_group_overlap) <= 0:
                continue
            classify_text_location_res = LqaProcessing.save_single_group_classify_res(single_group_overlap,
                                                                                      i,
                                                                                      text_location_list,
                                                                                      classify_text_location_res)
        return classify_text_location_res

    @staticmethod
    def rect_collision_detection(rect1, rect2, t=(0, 0, 0, 0)):
        """矩形碰撞检测, 有交集且不包含为 True
        :param rect1: 矩形框1位置, x1,y1,x2,y2 格式
        :param rect2: 矩形框2位置, x1,y1,x2,y2 格式
        :param t: 上下左右阈值
        :return: bool, 是否存在碰撞
        """
        # 无交集
        if rect1[0] + t[0] > rect2[2] or rect1[2] < rect2[0] + t[1] \
                or rect1[1] + t[2] > rect2[3] or rect1[3] < rect2[1] + t[3]:
            return False
        # 全包含
        if rect2[0] - t[1] <= rect1[0] < rect1[2] <= rect2[2] + t[0] \
                and rect2[1] - t[3] <= rect1[1] < rect1[3] <= rect2[3] + t[2]:
            return False
        return True

    @staticmethod
    def get_join_ocr_result(img, project=None):
        """识别图像的 ocr 结果, 并将结果聚合起来
        :param img: ndarray, 图像数据
        :param project: str, 指定调用项目
        :return: text_data: ocr 识别结果
                 text_str: 聚合文本
        """
        text_str = ''
        text_data = ocr(mat_to_base64(img), project=project)
        if not text_data:
            return None, None
        for text_one in text_data:
            ocr_result = text_one["result"]
            if ocr_result and len(ocr_result) <= 0:
                continue
            text_str += ocr_result
        return text_data, text_str

    @staticmethod
    def judge_ocr_location_extend(img, text_location, text_str, project=None):
        """根据文本框信息和 ocr 识别结果判断文本框是否需要进行扩展
        :param img: ndarray, 图像数据
        :param text_location: 文本位置, x1,y1,x2,y2 格式
        :param text_str: str, 文本内容
        :param project: str, 指定调用项目
        :return: bool, 是否扩展
                 img_location_extend, ndarray, 文本区域图像数据
                 text_data_ext, dict, 文本区域对应的OCR识别结果
        """
        # 原区域提取和识别
        height, width = img.shape[:2]
        x1, y1, x2, y2 = text_location
        img_location = img[y1: y2, x1: x2]
        text_data, text_s = LqaProcessing.get_join_ocr_result(img_location, project=project)
        if not text_data:
            return False, None, None
        # 区域扩展和识别
        img_location_extend = img[max(0, y1 - 5): min(height, y2 + 5), max(0, x1 - 10): min(width, x2 + 10)]
        text_data_ext, text_s_ext = LqaProcessing.get_join_ocr_result(img_location_extend, project=project)
        if not text_data_ext:
            return False, None, None
        # 判断是否扩展 (扩展后是否包含非文本框信息)
        if text_s == text_s_ext or len(text_s_ext) > len(text_str or ''):
            return False, img_location, text_data
        else:
            return True, img_location_extend, text_data_ext

    @staticmethod
    def align_single_ocr_location(text_one, text_data, x1, y1, img_location, all_ocr_dict, align_location_list,
                                  align_ocr_res, extend=False):
        """ocr 识别单个结果微调校准
        :param text_one: dict, 单 ocr 识别结果
        :param text_data: list, ocr 识别结果
        :param x1: int, 文本位置坐标 x_min
        :param y1: int, 文本位置坐标 y_min
        :param img_location: ndarray, 文本区域的图像
        :param all_ocr_dict: dict, 全局 ocr 识别结果
        :param align_location_list: list, 校准的位置信息
        :param align_ocr_res: list, 校准的文本信息
        :param extend: bool, 是否扩展文本区域
        :return: align_location_list, list, 校准的位置信息
                 align_ocr_res, list, 校准的文本信息
        """

        ocr_result = text_one["result"]
        if ocr_result and len(ocr_result) <= 0:
            return align_location_list, align_ocr_res
        ocr_area = text_one["area"]
        ocr_x1, ocr_y1, ocr_x2, ocr_y2 = text_one["area"]
        img = img_location[ocr_y1:ocr_y2, ocr_x1:ocr_x2]
        if 0 in img.shape:
            return align_location_list, align_ocr_res
        # 灰度值判断, 过滤背景区域
        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if np.max(gray_img) < 120 and len(text_data) > 1:
            return align_location_list, align_ocr_res
        # 二值化提取前景, 文本区域微调
        binary_threshold = np.mean(gray_img)
        _, th = cv2.threshold(gray_img, binary_threshold, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary_query = cv2.erode(th, kernel)
        h, w = binary_query.shape
        h_list = []
        w_list = []
        for j in range(h):
            for i in range(w):
                if binary_query[j, i] == 255:
                    h_list.append(j)
                    w_list.append(i)
        if not extend:
            ocr_x1 = ocr_area[0] + max(0, x1)
            ocr_y1 = ocr_area[1] + max(0, y1)
            ocr_x2 = ocr_area[0] + max(0, x1)
            ocr_y2 = ocr_area[1] + max(0, y1)
        else:
            ocr_x1 = ocr_area[0] + max(0, x1 - 10)
            ocr_y1 = ocr_area[1] + max(0, y1 - 5)
            ocr_x2 = ocr_area[0] + max(0, x1 - 10)
            ocr_y2 = ocr_area[1] + max(0, y1 - 5)
        if len(w_list) > 0 :
            ocr_x1 = ocr_x1 + np.min(w_list)
            ocr_y1 = ocr_y1 + np.min(h_list)
            ocr_x2 = ocr_x2 + np.max(w_list)
            ocr_y2 = ocr_y2 + np.max(h_list)
        # 局部识别和全局识别共同校准
        center_x = (ocr_x1 + ocr_x2) / 2
        center_y = (ocr_y1 + ocr_y2) / 2
        align_location = (ocr_x1, ocr_y1, ocr_x2, ocr_y2)
        if ocr_result in all_ocr_dict:
            for item in all_ocr_dict[ocr_result]:
                item_x1, item_y1, item_x2, item_y2 = item
                if item_x1 < center_x < item_x2 and item_y1 < center_y < item_y2:
                    align_ocr_x1 = max(ocr_x1, item_x1)
                    align_ocr_y1 = max(ocr_y1, item_y1)
                    align_ocr_x2 = min(ocr_x2, item_x2)
                    align_ocr_y2 = min(ocr_y2, item_y2)
                    align_location = (align_ocr_x1, align_ocr_y1, align_ocr_x2, align_ocr_y2)
                    break
        if align_location:
            align_location_list.append(align_location)
            align_ocr_res.append(text_one)
        return align_location_list, align_ocr_res

    @staticmethod
    def align_ocr_location(text_location, img_location, text_data, all_ocr_dict, merge_location=True, extend=False):
        """ocr 识别结果微调校准
        :param text_location: 文本位置, x1,y1,x2,y2 格式
        :param img_location: ndarray, 文本区域的图像
        :param text_data: list, ocr 识别结果
        :param all_ocr_dict: dict, 全图像 ocr 识别结果
        :param merge_location: bool, 是否合并检测出来的 ocr 文本区域
        :param extend: bool, 是否扩展文本区域
        :return: align_res, list, 校准的位置信息
                 align_ocr_res, list, 校准的文本信息
        """
        align_location_list = []
        align_ocr_res = []
        x1, y1, _, _ = text_location
        for text_one in text_data:
            align_location_list, align_ocr_res = LqaProcessing.align_single_ocr_location(text_one,
                                                                                         text_data,
                                                                                         x1,
                                                                                         y1,
                                                                                         img_location,
                                                                                         all_ocr_dict,
                                                                                         align_location_list,
                                                                                         align_ocr_res,
                                                                                         extend=extend)
        # 根据 merge_location 判断是否对文本框进行聚合处理
        align_res = []
        if len(align_location_list) > 0:
            if merge_location:
                x1_list = []
                x2_list = []
                y1_list = []
                y2_list = []
                for item in align_location_list:
                    x1_list.append(item[0])
                    y1_list.append(item[1])
                    x2_list.append(item[2])
                    y2_list.append(item[3])

                align_loc = (np.min(x1_list), np.min(y1_list), np.max(x2_list), np.max(y2_list))
                align_res.append(align_loc)
            else:
                align_res = align_location_list
        return align_res, align_ocr_res

    @staticmethod
    def shrink_image_box(img, image_location):
        """缩小图像框
        :param img: ndarray, 图像
        :param image_location: 图像框位置, x1,y1,x2,y2 格式
        :return: 调整后的图像框位置
        """
        h, w = img.shape[:2]
        img_roi_area = img[
                       max(0, image_location[1]): min(h, image_location[3]),
                       max(0, image_location[0]): min(w, image_location[2])
                       ]
        img_roi_area_gray = cv2.cvtColor(img_roi_area, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(img_roi_area_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, _, stats, _ = cv2.connectedComponentsWithStats(th, connectivity=4)
        hh, ww = img_roi_area.shape[:2]
        sss = hh * ww
        distance = 10000000
        min_index = -1
        if stats.shape[0] < 100:
            for i, stat in enumerate(stats):
                s = stat[2] * stat[3]
                if sss * 0.95 > s > 10:
                    stat_center_x, stat_center_y = stat[0] + stat[2] / 2, stat[1] + stat[3] / 2
                    dis = math.sqrt(((stat_center_x - ww / 2) ** 2) + ((stat_center_y - hh / 2) ** 2))
                    if dis < distance:
                        distance = dis
                        min_index = i
            if min_index != -1:
                return stats[min_index][0] + max(0, image_location[0]), \
                       stats[min_index][1] + max(0, image_location[1]), \
                       stats[min_index][0] + stats[min_index][2] + max(0, image_location[0]), \
                       stats[min_index][1] + stats[min_index][3] + max(0, image_location[1])
        return image_location


if __name__ == '__main__':
    pass
