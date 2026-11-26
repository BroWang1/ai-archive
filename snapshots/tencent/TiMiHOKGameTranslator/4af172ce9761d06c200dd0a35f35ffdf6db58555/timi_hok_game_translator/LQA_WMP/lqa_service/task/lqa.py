# -*- coding: utf-8 -*-
"""
# @file: lqa.py
# @desc: LQA 本地化文本异常检测核心逻辑模块, 提供 ImageLqa 类实现以下能力:
#        - lqa_check: 基于 OCR 识别的完整检测流程, 支持漏译、超框 (文本超文本框/图像框)、漏key、
#                     文本框重叠、错译、non_problem 自定义、非标准框等多种异常类型检测,
#                     并支持人工半监督数据 (supervised) 和历史检测结果 (history_result) 辅助判断
#        - lqa_check_no_ocr: 不依赖 OCR 的检测流程, 直接使用标注文本框的实际位置进行检测,
#                     适用于文本框已是文本最小外接矩的场景
#        - degrade_check_type: 当 OCR 服务不可用时, 自动将检测类型降级为仅保留不依赖 OCR 的类型
#                     (漏译/文本框与图像框重叠/漏key/文本框重叠/non_problem/非标准框),
#                     跳过依赖 OCR 的类型 (文本超文本框/错译)
"""
from common.tools import base64_to_mat, mat_to_base64
from common.interface_ocr import ocr_available
from common.log import logger
from task.lqa_processing import LqaProcessing
from task.lqa_supervised import Supervised
from task.lqa_abnormal import ErrorTrans, LqaAbnormal
from task.lqa_config import LqaCheckType

#: 必须依赖 OCR 的检测类型; OCR 不可用时自动剔除
#: 2-0 文本超文本框需要 OCR 给出文本实际边界; 5 错译需要 OCR 文本内容
OCR_DEPENDENT_CHECK_TYPES = ('2-0', str(LqaCheckType.ERROR_TRANS.value))

#: 不依赖 OCR 的全部检测类型 (纯几何 / 基于标注 textStr)
#: 1 漏译、2-1 文本框与图像框重叠、3 漏key、4 文本框重叠、6 non_problem、7 非标准框
OCR_FREE_CHECK_TYPES = ('1', '2-1', '3', '4', '6', '7')


def degrade_check_type(check_type):
    """剔除依赖 OCR 的检测类型

    :param check_type: list[str] 或 None (None 表示全部类型)
    :return: (list[str] 降级后的类型, list[str] 被跳过的类型)
    """
    if not check_type:
        return list(OCR_FREE_CHECK_TYPES), list(OCR_DEPENDENT_CHECK_TYPES)
    kept, skipped = [], []
    for item in check_type:
        if str(item) in OCR_DEPENDENT_CHECK_TYPES:
            skipped.append(str(item))
        else:
            kept.append(item)
    return kept, skipped


class ImageLqa:
    """
    本地化异常处理类
    """

    @staticmethod
    def lqa_check(img_base64, rect_locations, language, supervised, check_type, history_img_base64, history_result,
                  project, no_trans_marks, error_trans_marks):
        """v0.1: 文本本身超过文本框
           v0.2: 文本框内没有文本; 文本框内文本包含 ##NoTrans; 文本框和图像框重叠
           v0.3: 新增简体中文漏译, 过滤长条状文本框和图像框
           v0.4: 新增图像框缩小
           v1.1: 新增文本框重叠检测
           v1.2: 优化超框和重叠文本框处理 (细分归属判断)
           v1.3: 新增人工半监督
           v1.4: 新增历史数据先验知识
           v1.5: 新增错误翻译检测
           v1.6: 新增 non_problem 检测
           v1.7: 新增 project, 记录调用项目
        :param project: str, 项目
        :param img_base64: str, 被测图像 base64
        :param rect_locations: dict, 待检测标准的 text 和 image 矩形框位置信息
        :param language: int, 游戏包语言代码序号
        :param supervised: dict, 监督数据 (人工审核)
        :param check_type: list[str], 指定检查类型, 与 LqaCheckType-LqaCheckSubType 一致, 如 ['1','2-0','2-1','3']
        :param history_img_base64: str, 历史图像 base64 (用作对比参考)
        :param history_result: dict, 历史图像检测结果 (用作对比参考)
        :param project: 项目
        :param no_trans_marks: str, 漏译匹配标记
        :param error_trans_marks: str, 错译匹配标记
        :return: res, dict, 检测结果
        """
        # OCR 为可选能力: 不可用时降级走无 OCR 流程, 跳过依赖 OCR 的检测项,
        # 其余检测 (漏译/漏key/框重叠/non_problem/非标准框) 照常返回
        available, ocr_msg = ocr_available()
        if not available:
            kept, skipped = degrade_check_type(check_type)
            logger.warning('OCR 不可用, 降级为无 OCR 检测; 跳过类型 %s (%s)', skipped, ocr_msg)
            res = ImageLqa.lqa_check_no_ocr(img_base64, rect_locations, language, supervised, kept,
                                            history_img_base64, history_result, project,
                                            no_trans_marks, error_trans_marks)
            res["ocr_degraded"] = True
            res["ocr_message"] = ocr_msg
            res["skipped_check_type"] = skipped
            return res

        res = {
            "overframe": False,
            "mark_img": None,
            "rect_img": None,
            "check_detail": None
        }
        img = base64_to_mat(img_base64)
        history_img = base64_to_mat(history_img_base64)
        lqa_img = img.copy()
        rect_img = img.copy()
        text_location_list = rect_locations.get("text", [])
        image_location_list = rect_locations.get("image", [])
        # 提取所有标准文本框信息, 包括位置信息, 过滤脏数据的索引
        gt_text_info = LqaProcessing.detect_gt_text_locations(img, text_location_list, preprocessing=True)
        # 提取所有标准图像框信息
        gt_image_info = LqaProcessing.detect_gt_image_locations(img, image_location_list)
        # 绘制提供的标准框
        rect_img = LqaProcessing.draw_gt_locations(rect_img, gt_text_info, gt_image_info)
        # 预处理数据 (根据历史数据)
        text_location_list, image_location_list, lqa_img, check_detail = Supervised.preprocessing(img,
                                                                                                  lqa_img,
                                                                                                  rect_locations,
                                                                                                  history_img,
                                                                                                  history_result)
        # 预处理的异常 ———— 直接上报的, 只需要直接绘制结果和返回错误
        lqa_img, check_detail = Supervised.preprocessing_errs(lqa_img, rect_locations, gt_text_info, check_detail)

        if len(check_detail) > 0:
            res['overframe'] = True
        # 无数据直接返回
        if len(text_location_list) <= 0 and len(image_location_list) <= 0:
            res["mark_img"] = mat_to_base64(lqa_img)
            res["rect_img"] = mat_to_base64(rect_img)
            res["check_detail"] = check_detail
            return res
        # 获取各类监督信息
        no_trans_list, over_frame_text_text_list, over_frame_text_image_list, no_key_list, overlap_list, \
            error_trans_list, non_problem_list, non_rectangle_list = Supervised.get_supervised_data(supervised)

        # 标准数据预处理: 分类, 过滤脏数据
        # 提取所有标准文本框信息, 包括位置信息, 过滤脏数据的索引
        gt_text_info = LqaProcessing.detect_gt_text_locations(img, text_location_list)
        gt_text_locations = gt_text_info['gt_text_locations']
        # 提取所有标准图像框信息
        gt_image_info = LqaProcessing.detect_gt_image_locations(img, image_location_list)
        # 提取所有 OCR 检测信息
        all_ocr_dict = LqaProcessing.detect_ocr_data(img, gt_text_info, project=project)
        all_ocr_error_trans_dict = ErrorTrans.filter_error_trans_ocr_data(all_ocr_dict, error_trans_marks)
        # 标准文本框划分 (判断是否重叠)
        classify_text_location_res = LqaProcessing.classify_text_location_overlap(gt_text_info)
        for text_index in range(len(gt_text_locations)):
            if text_index in gt_text_info['dirty_text_ids']:  # 脏标准框数据跳过
                continue
            if text_index in gt_text_info['non_rectangle_ids']:  # 非标准框数据
                non_rectangle = True
            else:
                non_rectangle = False
            # 判断每一个文本框
            res, check_detail, rect_img, lqa_img = LqaAbnormal.judge_single_text(
                check_type, language, text_index, img, gt_image_info, gt_text_locations, classify_text_location_res,
                all_ocr_dict, all_ocr_error_trans_dict, no_trans_list, over_frame_text_text_list,
                over_frame_text_image_list, no_key_list, error_trans_list, non_problem_list, non_rectangle_list,
                text_location_list, lqa_img, rect_img, res, check_detail, no_trans_marks, error_trans_marks,
                non_rectangle=non_rectangle, project=project)
        # 处理重叠文本框
        overlap_group = classify_text_location_res['overlap_group']
        overlap_group_id = classify_text_location_res['overlap_group_id']
        if len(overlap_group) > 0:
            # 处理每一组重叠文本框
            for group_index in range(len(overlap_group)):
                res, check_detail, rect_img, lqa_img = LqaAbnormal.judge_single_group_overlap_text(
                    check_type, group_index, overlap_group, overlap_group_id,
                    img, gt_text_locations, all_ocr_dict,
                    classify_text_location_res, text_location_list,
                    overlap_list, over_frame_text_text_list, error_trans_list,
                    lqa_img, rect_img, res, check_detail, error_trans_marks, project=project)
        res["mark_img"] = mat_to_base64(lqa_img)
        res["rect_img"] = mat_to_base64(rect_img)
        res["check_detail"] = check_detail
        return res

    @staticmethod
    def lqa_check_no_ocr(img_base64, rect_locations, language, supervised, check_type, history_img_base64, history_result,
                  project, no_trans_marks, error_trans_marks):
        """
        无 ocr 识别, 直接返回文本框内文本的直接位置
        :param project: str, 项目
        :param img_base64: str, 被测图像 base64
        :param rect_locations: dict, 待检测标准的 text 和 image 矩形框位置信息
        :param language: int, 游戏包语言代码序号
        :param supervised: dict, 监督数据 (人工审核)
        :param check_type: list[str], 指定检查类型, 与 LqaCheckType-LqaCheckSubType 一致, 如 ['1','2-0','2-1','3']
        :param history_img_base64: str, 历史图像 base64 (用作对比参考)
        :param history_result: dict, 历史图像检测结果 (用作对比参考)
        :param project: 项目
        :param no_trans_marks: str, 漏译匹配标记
        :param error_trans_marks: str, 错译匹配标记
        :return: res, dict, 检测结果
        """
        res = {
            "overframe": False,
            "mark_img": None,
            "rect_img": None,
            "check_detail": None
        }
        img = base64_to_mat(img_base64)
        history_img = base64_to_mat(history_img_base64)
        lqa_img = img.copy()
        rect_img = img.copy()
        text_location_list = rect_locations.get("text", [])
        image_location_list = rect_locations.get("image", [])
        # 提取所有标准文本框信息, 包括位置信息, 过滤脏数据的索引
        gt_text_info = LqaProcessing.detect_gt_text_locations(img, text_location_list, preprocessing=True)
        # 提取所有标准图像框信息
        gt_image_info = LqaProcessing.detect_gt_image_locations(img, image_location_list)
        # 绘制标准框
        rect_img = LqaProcessing.draw_gt_locations(rect_img, gt_text_info, gt_image_info)
        # 预处理数据 (根据历史数据)
        text_location_list, image_location_list, lqa_img, check_detail = Supervised.preprocessing(img,
                                                                                                  lqa_img,
                                                                                                  rect_locations,
                                                                                                  history_img,
                                                                                                  history_result)
        # 预处理的异常 ———— 直接上报的, 只需要直接绘制结果和返回错误
        lqa_img, check_detail = Supervised.preprocessing_errs(lqa_img, rect_locations, gt_text_info, check_detail)

        if len(check_detail) > 0:
            res['overframe'] = True
        # 无数据直接返回
        if len(text_location_list) <= 0 and len(image_location_list) <= 0:
            res["mark_img"] = mat_to_base64(lqa_img)
            res["rect_img"] = mat_to_base64(rect_img)
            res["check_detail"] = check_detail
            return res
        # 获取各类监督信息
        no_trans_list, over_frame_text_text_list, over_frame_text_image_list, no_key_list, overlap_list, \
        error_trans_list, non_problem_list, non_rectangle_list = Supervised.get_supervised_data(supervised)

        # 标准数据预处理: 分类, 过滤脏数据
        # 提取所有标准文本框信息, 包括位置信息, 过滤脏数据的索引
        gt_text_info = LqaProcessing.detect_gt_text_locations(img, text_location_list)
        gt_text_locations = gt_text_info['gt_text_locations']
        # 提取所有标准图像框信息
        gt_image_info = LqaProcessing.detect_gt_image_locations(img, image_location_list)

        # 指定错译检查__提取所有OCR检测信息 (只检查一遍, 用于判断是否有错译)
        check_type_id = LqaCheckType.ERROR_TRANS.value
        if not check_type or str(check_type_id) in check_type:
            all_ocr_dict = LqaProcessing.detect_ocr_data(img, gt_text_info, project=project)
            all_ocr_error_trans_dict = ErrorTrans.filter_error_trans_ocr_data(all_ocr_dict, error_trans_marks)
        else:
            all_ocr_dict = {}
            all_ocr_error_trans_dict = {}
        # 所有文本框碰撞检测, 不重复
        dirty_text_ids = gt_text_info['dirty_text_ids']
        overlap_dict = {}
        cnt = len(gt_text_locations)
        for i in range(cnt):
            if i in dirty_text_ids:  # 脏数据过滤, 便于后续检测, 无需处理
                continue
            overlap_dict = LqaProcessing.judge_overlap_with_text_i(overlap_dict, i, gt_text_locations, dirty_text_ids)
        # 判断每一个文本框
        for text_index in range(cnt):
            if text_index in dirty_text_ids:  # 脏标准框数据跳过
                continue
            if text_index in gt_text_info['non_rectangle_ids']:  # 非标准框数据
                non_rectangle = True
            else:
                non_rectangle = False
            res, check_detail, rect_img, lqa_img = LqaAbnormal.judge_single_text_no_ocr(
                check_type, language, text_index, img, gt_image_info, gt_text_locations, overlap_dict,
                all_ocr_dict, all_ocr_error_trans_dict,
                no_trans_list, error_trans_list, over_frame_text_text_list,
                over_frame_text_image_list, no_key_list, non_problem_list, non_rectangle_list,
                text_location_list, lqa_img, rect_img, res, check_detail, no_trans_marks, error_trans_marks,
                non_rectangle=non_rectangle, project=project)

        res["mark_img"] = mat_to_base64(lqa_img)
        res["rect_img"] = mat_to_base64(rect_img)
        res["check_detail"] = check_detail
        return res


if __name__ == '__main__':
    pass
