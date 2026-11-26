# -*- coding: utf-8 -*-
"""
# @file: lqa_supervised.py
# @desc: LQA 本地化文本异常检测——半监督处理模块, 提供 Supervised 类实现以下能力:
#        - get_supervised_data/get_over_frame_supervised_data: 解析人工审核的监督数据 (supervised),
#                     按漏译/超框 (文本超文本框、文本超图像框)/漏key/文本框重叠/错译/
#                     non_problem/非标准框等类型分类提取
#        - judge_location_change: 对比当前图像与历史图像的差异区域, 过滤出发生变化的检测区域,
#                     未变化区域可直接复用历史检测结果
#        - extract_history_result_by_other_type/extract_history_result_by_over_frame_type/
#          extract_history_result: 根据历史检测结果 (history_result), 在两次检测图像的相同 (未变化)
#                     区域上保留历史异常标记, 并在结果图上绘制对应的标注框
#        - preprocessing: 结合历史图像和历史检测结果, 预处理待检测的文本框/图像框列表,
#                     过滤掉未发生变化的区域, 减少重复检测
#        - preprocessing_errs: 处理预处理阶段直接产生的异常 (如脏数据/非标准框等),
#                     直接绘制标注并写入检测结果详情, 无需进入后续常规检测流程
"""
import cv2
import numpy as np
from task.lqa_config import LqaCheckType, LqaCheckSubType, DrawStyle
from task.lqa_processing import LqaProcessing
from task.lqa_abnormal import LqaAbnormal
from common.tools import img_draw_rect


class Supervised:
    """监督处理 (历史测试数据)"""

    @staticmethod
    def get_supervised_data(data):
        """ 获取各类监督数据
        :param data: dict, 监督数据
        :return: 各类监督数据列表
        """
        no_trans_list = []  # 漏译
        over_frame_text_text_list = []  # 文本超文本框
        over_frame_text_image_list = []  # 文本超图像框
        no_key_list = []  # 漏 key
        overlap_list = []  # 文本框重叠
        error_trans_list = []  # 错译
        non_problem_list = []  # non_problem
        non_rectangle_list = []  # non_problem
        if data:
            if str(LqaCheckType.NO_TRANS.value) in data:
                no_trans_list = data[str(LqaCheckType.NO_TRANS.value)]
            if str(LqaCheckType.NO_KEY.value) in data:
                no_key_list = data[str(LqaCheckType.NO_KEY.value)]
            if str(LqaCheckType.OVERLAP.value) in data:
                overlap_list = data[str(LqaCheckType.OVERLAP.value)]
            if str(LqaCheckType.OVER_FRAME.value) in data:
                over_frame_text_text_list, over_frame_text_image_list = Supervised.get_over_frame_supervised_data(data)
            if str(LqaCheckType.ERROR_TRANS.value) in data:
                error_trans_list = data[str(LqaCheckType.ERROR_TRANS.value)]
            if str(LqaCheckType.NON_PROBLEM.value) in data:
                non_problem_list = data[str(LqaCheckType.NON_PROBLEM.value)]
            if str(LqaCheckType.NON_RECTANGLE.value) in data:
                non_rectangle_list = data[str(LqaCheckType.NON_RECTANGLE.value)]
        return no_trans_list, over_frame_text_text_list, over_frame_text_image_list, no_key_list, overlap_list,\
               error_trans_list, non_problem_list, non_rectangle_list

    @staticmethod
    def get_over_frame_supervised_data(data):
        """ 获取超框类型监督数据
        :param data: dict, 监督数据
        :return: 各类监督数据列表
        """
        over_frame_text_text_list = []  # 文本超文本框
        over_frame_text_image_list = []  # 文本超图像框
        if str(LqaCheckSubType.OVER_FRAME_TEXT_TEXT.value) in data[str(LqaCheckType.OVER_FRAME.value)]:
            over_frame_text_text_list = data[str(LqaCheckType.OVER_FRAME.value)][
                str(LqaCheckSubType.OVER_FRAME_TEXT_TEXT.value)]
        if str(LqaCheckSubType.OVER_FRAME_TEXT_IMAGE.value) in data[str(LqaCheckType.OVER_FRAME.value)]:
            over_frame_text_image_list = data[str(LqaCheckType.OVER_FRAME.value)][
                str(LqaCheckSubType.OVER_FRAME_TEXT_IMAGE.value)]
        return over_frame_text_text_list, over_frame_text_image_list

    @staticmethod
    def judge_location_change(sub_img, location_list, need_coordinate_trans=True, need_judge_rectangle=False):
        """ 对比和提取历史先验数据的图像变更区域
        :param sub_img: ndarray, 两次测试图像的差图
        :param location_list: list, 原始检测区域信息
        :param need_coordinate_trans: bool, 是否需要进行单位转换
        :param need_judge_rectangle: bool, 是否需要进行标准框检查
        :return: res_location_list, list, 过滤发生变化的检测区域
        """
        h, _ = sub_img.shape[:2]
        res_location_list = []
        for item in location_list:
            if need_coordinate_trans:  # 坐标转换
                if need_judge_rectangle:
                    is_rectangle = LqaProcessing.judge_rectangle(item)
                    location = LqaProcessing.coordinate_trans(item, h, is_rectangle)
                else:
                    location = LqaProcessing.coordinate_trans(item, h)

            else:
                location = item

            if len(location) != 4:  # 非标区域直接当作变更区域
                res_location_list.append(item)
            else:
                x1, y1, x2, y2 = location
                location_img = sub_img[y1:y2, x1:x2]
                if location_img.any() and np.max(location_img) > 0:
                    res_location_list.append(item)
        return res_location_list

    @staticmethod
    def extract_history_result_by_other_type(type_id, diff_img, sub_img, history_result, check_detail):
        """ 提取历史非超框类型数据
        :param type_id: int, 异常类型 id
        :param diff_img: ndarray, 结果绘制图
        :param sub_img: ndarray, 两次测试图像的差图
        :param history_result: dict, 历史检测结果
        :param check_detail: dict, 检测结果详细信息
        :return: diff_img, 结果绘制图
                 check_detail, 检测结果详细信息
        """
        draw_style = None
        # 非超框异常
        for item in history_result[type_id]:
            if len(item[1]) == 4:  # 非标框不处理了, 重新检测
                x1, y1, x2, y2 = item[1]
                location_list = [item[1]]
                judge_res = Supervised.judge_location_change(sub_img, location_list,
                                                             need_coordinate_trans=False)
                if len(judge_res) <= 0:  # 对比历史检测结果的相同区域, 结果进行保留
                    check_detail = LqaAbnormal.update_check_type_detail(check_detail, int(type_id), item)
                    if int(type_id) == LqaCheckType.NO_TRANS.value:
                        draw_style = DrawStyle.NO_TRANS.value
                    if int(type_id) == LqaCheckType.NO_KEY.value:
                        draw_style = DrawStyle.NO_KEY.value
                    if int(type_id) == LqaCheckType.OVERLAP.value:
                        draw_style = DrawStyle.OVERLAP.value
                    if draw_style:
                        cv2.rectangle(diff_img, (x1, y1), (x2, y2), draw_style[0], draw_style[1])
        return diff_img, check_detail

    @staticmethod
    def extract_history_result_by_over_frame_type(type_id, diff_img, sub_img, history_result, check_detail):
        """ 提取历史超框数据
        :param type_id: int, 异常类型 id
        :param diff_img: ndarray, 结果绘制图
        :param sub_img: ndarray, 两次测试图像的差图
        :param history_result: dict, 历史检测结果
        :param check_detail: dict, 检测结果详细信息
        :return: diff_img, 结果绘制图
                 check_detail, 检测结果详细信息
        """
        # 超框异常: 分为文本超文本框, 文本超图像框
        frame_data = history_result[type_id]
        for sub_type_id in frame_data:
            for item in frame_data[sub_type_id]:
                x1, y1, x2, y2 = item[1]
                location_list = [item[1]]
                if len(item) > 2:
                    location_list.append([item[2]])
                judge_res = Supervised.judge_location_change(sub_img, location_list,
                                                             need_coordinate_trans=False)
                if len(judge_res) <= 0:  # 对比历史检测结果的相同区域, 结果进行保留
                    check_detail = LqaAbnormal.update_check_type_detail(check_detail,
                                                                        int(type_id),
                                                                        item,
                                                                        int(sub_type_id))
                    draw_style = DrawStyle.OVER_FRAME.value
                    if draw_style:
                        cv2.rectangle(diff_img, (x1, y1), (x2, y2), draw_style[0], draw_style[1])
        return diff_img, check_detail

    @staticmethod
    def extract_history_result(diff_img, sub_img, history_result, check_detail):
        """ 根据历史检测结果, 提取并保留 2 次检测图像相同区域的结果
        :param diff_img: ndarray, 结果绘制图
        :param sub_img: ndarray, 两次测试图像的差图
        :param history_result: dict, 历史检测结果
        :param check_detail: dict, 检测结果详细信息
        :return: diff_img, 结果绘制图
                 check_detail, 检测结果详细信息
        """
        if history_result:
            # 逐类处理结果数据
            for type_id in history_result:
                # 非超框异常
                if type_id != str(LqaCheckType.OVER_FRAME.value):
                    diff_img, check_detail = Supervised.extract_history_result_by_other_type(type_id,
                                                                                             diff_img,
                                                                                             sub_img,
                                                                                             history_result,
                                                                                             check_detail)
                else:  # 超框异常
                    diff_img, check_detail = Supervised.extract_history_result_by_over_frame_type(type_id,
                                                                                                  diff_img,
                                                                                                  sub_img,
                                                                                                  history_result,
                                                                                                  check_detail)
        return diff_img, check_detail

    @staticmethod
    def preprocessing(img, diff_img, rect_locations, history_img, history_result):
        """ 半监督数据预处理
        :param img: ndarray, 待检测图像
        :param diff_img: ndarray, 结果绘制图
        :param rect_locations: list, 待检测图像文本、图像框信息
        :param history_img: ndarray, 历史检测图像
        :param history_result: dict, 历史检测结果
        :return: text_location_list, 预处理后需要检测的文本框信息
                 image_location_list, 预处理后需要检测的图像框信息
                 diff_img, 结果绘制图
                 check_detail, 检测结果详细信息
        """
        check_detail = {}
        text_location_list_temp = rect_locations.get("text", [])
        image_location_list_temp = rect_locations.get("image", [])
        if history_img is None or img.shape != history_img.shape:
            return text_location_list_temp, image_location_list_temp, diff_img, check_detail
        else:
            sub = img - history_img
            text_location_list = Supervised.judge_location_change(sub, text_location_list_temp,
                                                                  need_judge_rectangle=True)
            image_location_list = Supervised.judge_location_change(sub, image_location_list_temp)
            diff_img, check_detail = Supervised.extract_history_result(diff_img, sub, history_result, check_detail)
            return text_location_list, image_location_list, diff_img, check_detail

    @staticmethod
    def preprocessing_errs(lqa_img, rect_locations, gt_text_info, check_detail):
        """ 预处理的异常 ———— 只需要直接绘制结果和返回错误
        :param lqa_img: ndarray, 结果绘制图
        :param rect_locations: list, 待检测图像文本、图像框信息
        :param gt_text_info: dict, 处理的上报文本信息
        :param check_detail:  dict, 检测结果
        :return: lqa_img, 预处理后的 lqa_img
                 check_detail, 预处理后的检测结果详细信息
        """
        gt_text_locations = gt_text_info['gt_text_locations']
        dirty_text_ids = gt_text_info['dirty_text_ids']
        non_rectangle_ids = gt_text_info['non_rectangle_ids']
        pre_errs = gt_text_info['preprocessing_errs']
        for i in range(len(gt_text_locations)):
            if i in pre_errs:  # 有预检测异常
                errs = pre_errs[i]
                text_str = rect_locations['text'][i].get("textStr")
                err_rect = gt_text_locations[i]
                detail_data = [text_str, list(err_rect)]
                if i not in dirty_text_ids and i not in non_rectangle_ids:  # 矩形
                    lqa_img = img_draw_rect(lqa_img, err_rect, DrawStyle.PRE_ERR.value)
                if i in non_rectangle_ids:  # 非矩形
                    lqa_img = img_draw_rect(lqa_img, err_rect, DrawStyle.PRE_ERR.value)
                for item_err in errs:
                    if item_err not in check_detail:
                        check_detail[item_err] = []
                    if detail_data not in check_detail[item_err]:
                        check_detail[item_err].append(detail_data)

        return lqa_img, check_detail


if __name__ == '__main__':
    pass
