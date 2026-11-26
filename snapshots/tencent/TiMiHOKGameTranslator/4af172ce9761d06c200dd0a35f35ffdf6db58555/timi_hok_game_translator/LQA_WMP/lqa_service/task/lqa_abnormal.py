# -*- coding: utf-8 -*-
"""
# @file: lqa_abnormal.py
# @desc: LQA 本地化异常检测核心判断逻辑模块, 提供以下三个类:
#        - ErrorTrans: 错译检测类, 根据错译标记词 (error_trans_marks) 判断文本/OCR 结果是否命中错译,
#                     并支持从全图 OCR 结果中过滤出所有错译候选项
#        - OverlapText: 重叠文本框处理类, 当多个标准文本框存在重叠 (合并为一个外接矩形) 时,
#                     通过 OCR 识别该区域并按重叠面积归属各子文本框, 必要时对 OCR 结果做二值化
#                     细分割 (split_ocr), 再逐一判断子文本框是否存在错译/超框/重叠等异常
#        - LqaAbnormal: 异常检测主类, 汇总各类判断方法:
#                     * no_trans: 漏译检测 (命中漏译标记词)
#                     * no_key: 漏key检测 (简繁体字符集比对, 识别出简体中文残留)
#                     * custom_abnormal: 自定义 non_problem 标记检测
#                     * error_trans: 错译检测 (全局/单文本框两种模式)
#                     * text_overframe/ocr_image_overlap: 文本超文本框、文本与图像框重叠的碰撞检测
#                     * judge_single_text/judge_single_text_no_ocr: 对单个文本框执行全部类型检测
#                       (分别对应依赖 OCR 识别定位 和 已知精确坐标两种模式)
#                     * judge_single_independent_text: 对无重叠的独立文本框做 OCR 位置校准后再检测
#                     * judge_single_group_overlap_text: 对一组重叠文本框做 OCR 识别、归属判断及检测
#                     * update_check_type_detail/update_check_res: 统一记录检测结果详情,
#                       并在结果图上绘制对应的标注框 (需排除已被人工监督确认的数据)
"""
import cv2
import json
import numpy as np
from config.baseconfig import NO_TRANS_MARK_LIST, SIMPLIFIED_CHINESE_SET, TRADITIONAL_CHINESE_SET, \
    ERROR_TRANS_MARK_LIST, NON_PROBLEM_MARK
from common.tools import img_draw_rect, mat_to_base64
from common.interface_ocr import ocr
from task.lqa_config import LqaCheckType, LqaCheckSubType, Language, DrawStyle
from task.lqa_processing import LqaProcessing


class ErrorTrans:
    """错译检测类"""

    @staticmethod
    def error_trans_mark(text_str, error_trans_marks):
        """判断文本是否包含错误翻译标记
        :param text_str: str, 文本字符串
        :param error_trans_marks: str, 错译标识
        :return: have_error_trans_mark, bool, 是否包含错译标记词条
        """
        have_error_trans_mark = False
        if not text_str:  # 标准数据未提供文本内容, 无从判断
            return have_error_trans_mark
        if error_trans_marks not in ['', None]:  # 项目自定义
            error_trans_marks_list = json.loads(error_trans_marks)
        else:
            error_trans_marks_list = ERROR_TRANS_MARK_LIST  # 默认
        for mask in error_trans_marks_list:
            if isinstance(mask, list):  # 多标记组合
                cnt = 0
                for item in mask:
                    if item in text_str:
                        cnt += 1
                if cnt == len(mask):
                    have_error_trans_mark = True
                    break
            else:
                if mask in text_str:
                    have_error_trans_mark = True
                    break
        return have_error_trans_mark

    @staticmethod
    def filter_error_trans_ocr_data(all_ocr_dict, error_trans_marks):
        """从检测图像所有 ocr 结果中, 过滤出包含错误翻译标记的数据
        :param all_ocr_dict: dict, 全图 ocr 识别结果
        :param error_trans_marks: str, 错译标识
        :return: all_ocr_error_trans_dict, dict, 所有包含错误翻译标记的 ocr 识别结果
        """
        all_ocr_error_trans_dict = {}
        for ocr_result in all_ocr_dict:
            if ErrorTrans.error_trans_mark(ocr_result, error_trans_marks):
                all_ocr_error_trans_dict[ocr_result] = all_ocr_dict[ocr_result]
        return all_ocr_error_trans_dict

    @staticmethod
    def all_error_trans(text_location, ocr_data):
        """全图文本框区域检测错译
        :param text_location: list, 文本位置信息
        :param ocr_data: dict, ocr识别结果
        :return: bool, 是否错译
        """
        for ocr_str in ocr_data:
            for ocr_location in ocr_data[ocr_str]:
                # 文本区域与错译 ocr_data 发生碰撞
                is_overlap, ratio, _ = LqaProcessing.overlap(text_location, ocr_location, x_t=0, y_t=0)
                if is_overlap and ratio > 0.3:
                    return True
        return False

    @staticmethod
    def single_error_trans(ocr_data, error_trans_marks):
        """局部文本框区域检测错译
        :param ocr_data: dict, ocr识别结果
        :param error_trans_marks: str, 错译标识
        :return: bool, 是否错译
        """
        if isinstance(ocr_data, list):
            for item in ocr_data:
                ocr_result = item['result']
                if ErrorTrans.error_trans_mark(ocr_result, error_trans_marks):
                    return True
        elif isinstance(ocr_data, dict) and 'result' in ocr_data:
            ocr_result = ocr_data['result']
            if ErrorTrans.error_trans_mark(ocr_result, error_trans_marks):
                return True
        return False


class OverlapText:
    """重叠文本框处理类"""

    @staticmethod
    def judge_overlap_ocr_belong(align_res, align_ocr_res, group_id, gt_text_locations):
        """判断重叠文本框中各个 OCR 子项的归属
        :param align_res: list, ocr识别位置信息
        :param align_ocr_res: list, ocr 识别文本信息
        :param group_id: list, 多个重叠文本框聚合的 id 列表
        :param gt_text_locations: dict, 所有文本框信息
        :return: overlap_info, 重叠文本框归属信息
        """
        overlap_info = {}
        for i in range(len(align_res)):
            align_location = align_res[i]
            ocr_res = align_ocr_res[i] if len(align_ocr_res) == len(align_res) else []
            # 过滤合并区域识别出的非文本框内容
            overlap_item_ratio = []
            overlap_item_sub_px = []
            overlap_item_id = []
            for item in group_id:
                is_overlap, ratio, sub_px = LqaProcessing.overlap(gt_text_locations[item], align_location, x_t=0, y_t=0)
                if is_overlap and ratio > 0.3:
                    overlap_item_id.append(item)
                    overlap_item_ratio.append(ratio)
                    overlap_item_sub_px.append(sub_px)
            if len(overlap_item_id) > 0:
                # 计算最大重叠率判断归属
                max_ratio_index = overlap_item_ratio.index(max(overlap_item_ratio))
                belong_id = overlap_item_id[max_ratio_index]
                if belong_id not in overlap_info:
                    overlap_info[belong_id] = []
                overlap_info[belong_id].append({'ocr_res': ocr_res,
                                                'ocr_location': align_location,
                                                'gt_location': gt_text_locations[belong_id],
                                                'ratio': overlap_item_ratio[max_ratio_index],
                                                'sub_px': overlap_item_sub_px[max_ratio_index]})
        return overlap_info

    @staticmethod
    def check_every_overlap_ocr(check_type, rect_img, lqa_img, overlap_info, text_location_list, gt_text_locations,
                                res, check_detail, supervised_info, error_trans_marks):
        """判断重叠文本框中各个 OCR 子项的归属
        :param check_type: list, 检测类型
        :param rect_img: ndarray, 标记图
        :param lqa_img: ndarray, lqa识别结果图
        :param overlap_info: dict, 一组重叠文本框的信息
        :param text_location_list: list, 待测试文本框信息 (去掉脏数据等)
        :param gt_text_locations: list, 标准文本框信息
        :param res: dict, 结果数据
        :param check_detail: dict, 已检测结果详情
        :param supervised_info: dict, 监督信息
        :param error_trans_marks: str, 错译标识
        :return: res, 检测结果数据
                 check_detail, 检测结果详情
                 rect_img, 标记图像
                 lqa_img, 检测结果图像
        """
        # 一组重叠文本框各个对象检测
        for g_id in overlap_info:
            text_location_dict = text_location_list[g_id]
            text_str = text_location_dict.get("textStr")
            # 错译
            check_type_id = LqaCheckType.ERROR_TRANS.value
            if check_type is None or str(check_type_id) in check_type:
                for overlap_item_i in overlap_info[g_id]:
                    is_abnormal = LqaAbnormal.error_trans(text_str,
                                                          overlap_item_i['gt_location'],
                                                          overlap_item_i['ocr_res'],
                                                          error_trans_marks,
                                                          check_type='single')
                    if is_abnormal:
                        detail_data = [text_str, list(gt_text_locations[g_id])]
                        supervised_error_trans = supervised_info['error_trans']
                        res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                                  check_detail,
                                                                                  check_type_id,
                                                                                  detail_data,
                                                                                  supervised_error_trans,
                                                                                  lqa_img,
                                                                                  overlap_item_i['gt_location'],
                                                                                  DrawStyle.ERROR_TRANS.value)
            # 碰撞检测, 文本超过文本框
            type_id = LqaCheckType.OVER_FRAME.value
            sub_type_id = LqaCheckSubType.OVER_FRAME_TEXT_TEXT.value
            check_type_id = str(type_id) + "-" + str(sub_type_id)
            if check_type is None or check_type_id in check_type:
                for overlap_item_i in overlap_info[g_id]:
                    rect_img = img_draw_rect(rect_img, overlap_item_i['ocr_location'],
                                             draw_style=DrawStyle.OVERLAP.value)
                    is_abnormal = LqaAbnormal.text_overframe(overlap_item_i['ocr_location'],
                                                             overlap_item_i['gt_location'],
                                                             t=(5, 5, 5, 5))
                    if is_abnormal:
                        detail_data = [text_str, list(gt_text_locations[g_id])]
                        draw_style = DrawStyle.GT_TEXT.value
                        supervised_over_frame_text_text = supervised_info['over_frame_text_text']
                        res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                                  check_detail,
                                                                                  type_id,
                                                                                  detail_data,
                                                                                  supervised_over_frame_text_text,
                                                                                  lqa_img,
                                                                                  overlap_item_i['gt_location'],
                                                                                  draw_style,
                                                                                  sub_type_id=sub_type_id)
        return res, check_detail, rect_img, lqa_img

    @staticmethod
    def sorted_detail_data(group_text_id, text_location_list, gt_text_locations):
        """结果详情排序
        :param group_text_id: list, 一组重叠文本框对应的索引列表
        :param text_location_list: list, 待测试文本框信息 (去掉脏数据等)
        :param gt_text_locations: list, 标准文本框信息
        :return: detail_data, 排序后的结果详情
        """
        detail_data = []
        for text_id in group_text_id:
            text_location_dict = text_location_list[text_id]
            text_str = text_location_dict.get("textStr")
            detail_data_item = [text_str, list(gt_text_locations[text_id])]
            detail_data.append(detail_data_item)
        detail_data = sorted(detail_data)
        return detail_data

    @staticmethod
    def judge_split(overlap_item):
        """判断文本框是否需要再次细分割
        :param overlap_item: dict, 子文本框
        :return: bool, 是否细分割
        """
        if overlap_item['ratio'] > 0.9 or (overlap_item['sub_px'][0] < 5 and overlap_item['sub_px'][1] < 4):
            return False
        return True

    @staticmethod
    def get_split_tags(binary_img):
        """ 提取二值图像的分割标记
        :param binary_img: ndarray, 二值图像
        :return: split_tags, list, 分割标记
        """
        split_tags = []
        h, w = binary_img.shape[:2]
        for i in range(w):
            split = True
            for j in range(h):
                if binary_img[j][i] > 0:
                    split = False
                    break
            if split:
                split_tags.append(1)
            else:
                split_tags.append(0)
        return split_tags

    @staticmethod
    def get_split_range(split_tags):
        """ 根据分割标记提取分割范围
        :param split_tags, list, 分割标记
        :return: split_range, list, 分割范围
        """
        start = -1
        split_range = []
        for i in range(len(split_tags)):
            if split_tags[i] == 1 and start == -1:
                start = i
            elif (split_tags[i] == 0 or i == len(split_tags) - 1) and start != -1:
                end = i
                split_range.append((end - start, (start, end)))
                start = -1
        return split_range

    @staticmethod
    def get_split_ocr_locations(ocr_location, split_range, k):
        """根据分割目标, 对分割结果排序, 计算分割结果
        :param ocr_location: list, 区域位置
        :param split_range: list, 可能的分割范围
        :param k: int, 分割的子区域数目
        :return: split_ocr_locations, list, 分割结果
        """
        # 根据间隔对预分割线进行排序
        sort_split_range = sorted(split_range, key=lambda x: x[0], reverse=True)
        t_k = min(k - 1, len(sort_split_range))
        top_k = sort_split_range[:t_k]
        sort_top_k = sorted(top_k, key=lambda x: x[1][0])
        split_ocr_locations = []
        for i in range(t_k):
            if i == 0:
                ocr_x = (ocr_location[0], sort_top_k[i][1][0] + ocr_location[0] - 1)
            else:
                ocr_x = (sort_top_k[i - 1][1][1] + ocr_location[0] + 1, sort_top_k[i][1][0] + ocr_location[0] - 1)
            split_ocr_location = (ocr_x[0], ocr_location[1], ocr_x[1], ocr_location[3])
            split_ocr_locations.append(split_ocr_location)
        tail_ocr_x = (sort_top_k[-1][1][1] + ocr_location[0] + 1, ocr_location[2])
        split_ocr_location = (tail_ocr_x[0], ocr_location[1], tail_ocr_x[1], ocr_location[3])
        split_ocr_locations.append(split_ocr_location)
        return split_ocr_locations

    @staticmethod
    def split_ocr(img, ocr_location, k):
        """ ocr 识别结果细分割, 将 ocr_location 区域分为 k 个子区域
        :param img: ndarray, 图像
        :param ocr_location: list, x1,y1,x2,y2 格式
        :param k: int, 分割子串数目
        :return: split_ocr_locations, list, 分割结果
        """
        # 二值化, 计算预分割线
        rect_img = img.copy()
        rect_img = rect_img[ocr_location[1]:ocr_location[3], ocr_location[0]:ocr_location[2]]
        gray_img = cv2.cvtColor(rect_img, cv2.COLOR_BGR2GRAY)
        binary_threshold = np.mean(gray_img)
        _, th = cv2.threshold(gray_img, binary_threshold, 255, cv2.THRESH_BINARY)
        if binary_threshold > 150:
            th = ~th
        # 提取可能分割标记
        split_tags = OverlapText.get_split_tags(th)
        # 提取分割范围
        split_range = OverlapText.get_split_range(split_tags)
        if len(split_range) <= 0:
            return []
        # 根据间隔对预分割线进行排序, 提取分割结果
        split_ocr_locations = OverlapText.get_split_ocr_locations(ocr_location, split_range, k)
        return split_ocr_locations

    @staticmethod
    def recheck_every_overlap_ocr(check_type, img, rect_img, lqa_img, overlap_item, group_id, gt_text_locations,
                                  res, check_detail, detail_data, supervised_info):
        """细粒度判断重叠文本框中的 OCR 子项
        :param check_type: list, 检测类型
        :param img: ndarray, 原测试图
        :param rect_img: ndarray, 标记图
        :param lqa_img: ndarray, lqa 识别结果图
        :param overlap_item: dict, 一组重叠文本框的子文本框
        :param group_id: list, 待测试文本框信息 (去掉脏数据等)
        :param gt_text_locations: list, 标准文本框信息
        :param res: dict, 结果数据
        :param check_detail: dict, 已检测结果详情
        :param detail_data: dict, 检测详情
        :param supervised_info: dict, 监督信息
        :return: res, 检测结果数据
                 check_detail, 检测结果详情
                 rect_img, 标记图像
                 lqa_img, 检测结果图像
        """
        draw_style = DrawStyle.OVERLAP.value
        # 重叠率足够, 无需细分判断
        if not OverlapText.judge_split(overlap_item):
            draw_rect = overlap_item['ocr_location']
            rect_img = img_draw_rect(rect_img, draw_rect, draw_style)

        # 需要细分进行分割
        else:
            split_ocr_rect = overlap_item['ocr_location']
            split_ocr_locations = OverlapText.split_ocr(img, split_ocr_rect, k=len(group_id))
            split_overlap_info = OverlapText.judge_overlap_ocr_belong(split_ocr_locations,
                                                                      [],
                                                                      group_id,
                                                                      gt_text_locations)
            for split_g_id in split_overlap_info:
                for split_item_i in split_overlap_info[split_g_id]:
                    draw_rect = split_item_i['ocr_location']
                    rect_img = img_draw_rect(rect_img, draw_rect, draw_style)
                    if not OverlapText.judge_split(split_item_i):
                        continue
                    else:
                        check_type_id = LqaCheckType.OVERLAP.value
                        supervised_overlap = supervised_info['overlap']
                        if check_type is None or str(check_type_id) in check_type:
                            res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                                      check_detail,
                                                                                      check_type_id,
                                                                                      detail_data,
                                                                                      supervised_overlap,
                                                                                      lqa_img,
                                                                                      draw_rect,
                                                                                      draw_style)
        return res, check_detail, rect_img, lqa_img


class LqaAbnormal:
    """lqa 数据异常检测类"""

    @staticmethod
    def update_check_type_detail(check_detail, type_id, data, sub_type_id=None):
        """检测结果分类详情
        :param check_detail: dict, 结果分类详情
        :param type_id: int 问题类型 id
        :param data: 记录的详细数据
        :param sub_type_id: int 问题子类型 id
        :return: res, 更新后的结果数据
                 check_detail, 更新后的检测结果详情
                 img, 标记后的图像
        """
        if not check_detail:
            check_detail = {}

        if type_id not in check_detail:
            if sub_type_id is None:
                check_detail[type_id] = []
            else:
                check_detail[type_id] = {}
        if sub_type_id is None:
            if data not in check_detail[type_id]:
                check_detail[type_id].append(data)
        else:
            if sub_type_id not in check_detail[type_id]:
                check_detail[type_id][sub_type_id] = []
            if data not in check_detail[type_id][sub_type_id]:
                check_detail[type_id][sub_type_id].append(data)

        return check_detail

    @staticmethod
    def update_check_res(res, check_detail, type_id, detail_data, supervised_detail_data,
                         img, draw_rect, draw_style, sub_type_id=None):
        """标记异常
        :param res: dict, 结果数据
        :param check_detail: dict, 已检测结果详情
        :param type_id: int, 异常检测类型 id
        :param detail_data: list, 待记录数据
        :param supervised_detail_data: list, 监督数据列表
        :param img: ndarray, 图像
        :param draw_rect: x1, y1, x2, y2, 标记位置
        :param draw_style: tuple, 绘制样式, 取值 DrawStyle, 包括颜色, 线条 size
        :param sub_type_id: int, 异常检测子类型 id
        :return: res, 更新后的结果数据
                 check_detail, 更新后的检测结果详情
                 img, 标记后的图像
        """
        if detail_data not in supervised_detail_data:
            res["overframe"] = True
            check_detail = LqaAbnormal.update_check_type_detail(check_detail, type_id, detail_data,
                                                                sub_type_id=sub_type_id)
            img = img_draw_rect(img, draw_rect, draw_style=draw_style)
        return res, check_detail, img

    @staticmethod
    def no_key(text_str, language):
        """简体中文漏 key 检测
        :param text_str: str, 待检测文本
        :param language: int, 语言 int
        :return: is_abnormal, bool, 是否异常
        """
        is_abnormal = False
        traditional_chinese = False
        if not text_str:  # 标准数据未提供文本内容, 无从判断
            return is_abnormal
        ocr_set = set(list(text_str))
        # 判断有繁体字
        traditional_intersection = ocr_set & TRADITIONAL_CHINESE_SET
        if traditional_intersection:
            traditional_chinese = True
        #  判断有简体中文
        simple_intersection = ocr_set & SIMPLIFIED_CHINESE_SET
        # 异常判断: 1.没有繁体中文但存在简体中文 2.外语误识别的中文
        if not traditional_chinese and simple_intersection:
            if language == Language.ja_JP.value:
                if len(simple_intersection) == len(ocr_set):
                    is_abnormal = True
            else:
                if len(simple_intersection) >= 1:
                    is_abnormal = True
        return is_abnormal

    @staticmethod
    def no_trans(text_str, no_trans_marks):
        """漏译检测
        :param text_str: str, 待检测文本
        :param no_trans_marks: str, 漏译标识
        :return: is_abnormal, bool, 是否异常
        """
        is_abnormal = False
        if not text_str:  # 标准数据未提供文本内容, 无从判断
            return is_abnormal
        if no_trans_marks not in ['', None]:  # 项目自定义
            no_trans_marks_list = json.loads(no_trans_marks)
        else:
            no_trans_marks_list = NO_TRANS_MARK_LIST  # 默认
        for no_trans_mask in no_trans_marks_list:
            if no_trans_mask in text_str:
                is_abnormal = True
                break
        return is_abnormal

    @staticmethod
    def custom_abnormal(text_str, tag_text=NON_PROBLEM_MARK):
        """自定义类型 non_problem 检测
        :param text_str: str, 待检测文本
        :param tag_text: str, 自定义命中的标记文本
        :return: over_frame, bool, 是否异常
        """
        is_abnormal = False
        if not text_str:  # 标准数据未提供文本内容, 无从判断
            return is_abnormal
        if tag_text in text_str:
            is_abnormal = True
        return is_abnormal

    @staticmethod
    def error_trans(text_str, text_location, ocr_data, error_trans_marks, check_type='all'):
        """错误翻译检测
        :param text_str: str, 待检测文本
        :param text_location: list, 待检测文本位置 [ x_min, y_min, x_max, y_max]
        :param ocr_data: ocr 识别结果数据
        :param error_trans_marks: str, 错译标识
        :param check_type: str, all 全局, single, 单文本框
        :return: is_abnormal, bool, 是否异常

        """
        is_abnormal = False
        # 标注数据不存在错译, 可以直接返回, 无需检测
        if not ErrorTrans.error_trans_mark(text_str, error_trans_marks):
            return is_abnormal
        if ocr_data and text_location and len(text_location) == 4:
            if check_type == 'all' and text_location not in [[], None]:  # 全局图像检测
                is_abnormal = ErrorTrans.all_error_trans(text_location, ocr_data)
            if check_type == 'single':  # 单文本框检测
                is_abnormal = ErrorTrans.single_error_trans(ocr_data, error_trans_marks)
        return is_abnormal

    @staticmethod
    def text_overframe(ocr_location, text_location, t=(0, 0, 0, 0)):
        """文本超文本框
        :param ocr_location: list, 识别的文本区域 [ x_min, y_min, x_max, y_max]
        :param text_location: list, 待检测文本位置 [ x_min, y_min, x_max, y_max]
        :param t: 上下左右阈值
        :return: bool, 是否异常
        """
        # 直接碰撞检测
        return LqaProcessing.rect_collision_detection(ocr_location, text_location, t)

    @staticmethod
    def ocr_image_overlap(img, gt_image_info, ocr_location):
        """文本和图像重叠检测
        :param img: ndarray, 图像
        :param gt_image_info: dict, 标准图像框信息
        :param ocr_location: dict, 文本框位置坐标 (x1, y1, x2, y2)
        :return: collision, bool, 是否碰撞
                image_location, 发生碰撞的图像框位置坐标 (x1, y1, x2, y2)
        """
        collision = False
        image_location = None
        gt_image_locations = gt_image_info['gt_image_locations']
        dirty_image_ids = gt_image_info['dirty_image_ids']
        for i in range(len(gt_image_locations)):
            if i in dirty_image_ids:  # 脏图像框数据不检测
                continue
            image_location = gt_image_locations[i]
            # 碰撞检测, 文本本身超过图像框
            collision = LqaProcessing.rect_collision_detection(ocr_location, image_location, t=(5, 5, 5, 5))
            if collision:
                rectified_image_location = LqaProcessing.shrink_image_box(img, image_location)
                collision = LqaProcessing.rect_collision_detection(ocr_location,
                                                                   rectified_image_location,
                                                                   t=(5, 5, 5, 5))
                if collision:
                    break
        return collision, image_location

    @staticmethod
    def judge_single_text(check_type, language, text_index, img, gt_image_info, gt_text_locations,
                          classify_text_location_res, all_ocr_dict, all_ocr_error_trans_dict,
                          no_trans_list, over_frame_text_text_list, over_frame_text_image_list,
                          no_key_list, error_trans_list, non_problem_list, non_rectangle_list,
                          text_location_list, lqa_img, rect_img, res, check_detail,
                          no_trans_marks, error_trans_marks, non_rectangle=False, project=None):
        """针对每一个文本框做判断和检查
        :param check_type: list, 异常检测类型
        :param language: int, 语种 id
        :param text_index: int, 处理的第 text_index 个文本框
        :param img: ndarray, 原图像
        :param gt_image_info: dict, 标准图像框信息
        :param gt_text_locations: list, 标准文本框位置信息
        :param classify_text_location_res: dict, 文本框分类结果
        :param all_ocr_dict: dict, 全图 ocr 识别结果
        :param all_ocr_error_trans_dict, dict, 所有包含错误翻译标记的 ocr 识别结果
        :param no_trans_list: list, 半监督漏译信息
        :param over_frame_text_text_list: list, 半监督文本超框信息
        :param over_frame_text_image_list: list, 半监督文本超图像框信息
        :param no_key_list: list, 半监督漏 key 信息
        :param error_trans_list: list, 半监督错译信息
        :param non_problem_list: list, 半监督 non_problem 信息
        :param non_rectangle_list: list, 半监督 non_rectangle 信息
        :param text_location_list: list, 半监督预处理后的文本信息
        :param lqa_img: ndarray, 结果图像
        :param rect_img: ndarray, 标记图像
        :param res: dict, 结果
        :param check_detail: dict, 结果详情
        :param no_trans_marks: str, 漏译标识
        :param error_trans_marks: str, 错译标识
        :param non_rectangle: bool, 非标框, 默认都是标准框, 非标框不做碰撞检测
        :param project: str, 指定调用项目
        :return: res, check_detail, rect_img, lqa_img
        """
        # 判断每一个文本框

        text_location_dict = text_location_list[text_index]
        text_str = text_location_dict.get("textStr")
        detail_data = [text_str, list(gt_text_locations[text_index])]

        # 非标准框检测标记
        check_type_id = LqaCheckType.NON_RECTANGLE.value
        if check_type is None or str(check_type_id) in check_type:
            if non_rectangle:
                draw_style = DrawStyle.NON_RECTANGLE.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          non_rectangle_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 自定义类型检测 non_problem 标记
        check_type_id = LqaCheckType.NON_PROBLEM.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.custom_abnormal(text_str, tag_text=NON_PROBLEM_MARK)
            if is_abnormal:
                draw_style = DrawStyle.NON_PROBLEM.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          non_problem_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 漏译检测
        check_type_id = LqaCheckType.NO_TRANS.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.no_trans(text_str, no_trans_marks)
            if is_abnormal:
                draw_style = DrawStyle.NO_TRANS.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          no_trans_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)
        # 漏key检测
        check_type_id = LqaCheckType.NO_KEY.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.no_key(text_str, language)
            if is_abnormal:
                draw_style = DrawStyle.NO_KEY.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          no_key_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 错译-全局判断
        check_type_id = LqaCheckType.ERROR_TRANS.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.error_trans(text_str,
                                                  gt_text_locations[text_index],
                                                  all_ocr_error_trans_dict,
                                                  error_trans_marks,
                                                  check_type='all')
            if is_abnormal:
                draw_style = DrawStyle.ERROR_TRANS.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          error_trans_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 独立无重叠的文本框 (排除非标框)
        if not non_rectangle and text_index in classify_text_location_res['independent_id']:
            x1, y1, x2, y2 = gt_text_locations[text_index]
            text_location = (x1, y1, x2, y2)
            res, check_detail, rect_img, lqa_img = LqaAbnormal.judge_single_independent_text(
                check_type, text_index, text_location, text_str, img, gt_image_info, gt_text_locations, all_ocr_dict,
                over_frame_text_text_list, over_frame_text_image_list, error_trans_list,
                lqa_img, rect_img, res, check_detail, error_trans_marks, project=project)
        return res, check_detail, rect_img, lqa_img

    @staticmethod
    def judge_single_independent_text(check_type, text_index, text_location, text_str,
                                      img, gt_image_info, gt_text_locations, all_ocr_dict,
                                      over_frame_text_text_list, over_frame_text_image_list, error_trans_list,
                                      lqa_img, rect_img, res, check_detail, error_trans_marks, project=None):
        """检测每一个独立文本框
        :param check_type: list, 异常检测类型
        :param text_index: int, 处理的第 text_index 个文本框
        :param text_location: 文本位置信息
        :param text_str: str, 文本内容
        :param img: ndarray, 原图像
        :param gt_image_info: dict, 标准图像框信息
        :param gt_text_locations: list, 标准文本框位置信息
        :param all_ocr_dict: dict, 全图ocr识别结果
        :param over_frame_text_text_list: list, 半监督文本超框信息
        :param over_frame_text_image_list: list, 半监督文本超图像框信息
        :param error_trans_list: list, 半监督错译信息
        :param lqa_img: ndarray, 结果图像
        :param rect_img: ndarray, 标记图像
        :param res: dict, 结果
        :param check_detail: dict, 结果详情
        :param error_trans_marks: str, 错译标识
        :param project: str, 指定调用项目
        :return: res, check_detail, rect_img, lqa_img
        """
        # 判断单个文本框
        detail_data = [text_str, list(gt_text_locations[text_index])]
        # 判断是否需要扩展
        extend, img_location, text_data = LqaProcessing.judge_ocr_location_extend(img, text_location, text_str,
                                                                                  project=project)
        if text_data is None or img_location is None:
            return res, check_detail, rect_img, lqa_img
        # 文本框 ocr 位置校准微调
        align_res, _ = LqaProcessing.align_ocr_location(text_location, img_location, text_data, all_ocr_dict,
                                                        extend=extend)
        if len(align_res) != 1:
            return res, check_detail, rect_img, lqa_img
        # 文本框 ocr 位置校准微调
        ocr_x1, ocr_y1, ocr_x2, ocr_y2 = align_res[0]
        rect_img = img_draw_rect(rect_img, align_res[0], draw_style=DrawStyle.OCR.value)

        # 错译-单文本框检测
        check_type_id = LqaCheckType.ERROR_TRANS.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.error_trans(text_str,
                                                  gt_text_locations[text_index],
                                                  text_data,
                                                  error_trans_marks,
                                                  check_type='single')
            if is_abnormal:
                draw_style = DrawStyle.ERROR_TRANS.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          error_trans_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 文本超文本框检测
        type_id = LqaCheckType.OVER_FRAME.value
        sub_type_id = LqaCheckSubType.OVER_FRAME_TEXT_TEXT.value
        check_type_id = str(type_id) + "-" + str(sub_type_id)
        if check_type is None or check_type_id in check_type:
            is_abnormal = LqaAbnormal.text_overframe((ocr_x1, ocr_y1, ocr_x2, ocr_y2), text_location,
                                                     t=(5, 5, 5, 5))
            if is_abnormal:
                draw_style = DrawStyle.GT_TEXT.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          type_id,
                                                                          detail_data,
                                                                          over_frame_text_text_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style,
                                                                          sub_type_id=sub_type_id)
        # 文本框和图像框重叠
        type_id = LqaCheckType.OVER_FRAME.value
        sub_type_id = LqaCheckSubType.OVER_FRAME_TEXT_IMAGE.value
        check_type_id = str(type_id) + "-" + str(sub_type_id)
        if check_type is None or check_type_id in check_type:
            ocr_location = (ocr_x1, ocr_y1, ocr_x2, ocr_y2)
            collision, image_location = LqaAbnormal.ocr_image_overlap(img, gt_image_info, ocr_location)
            if collision and image_location is not None:
                detail_data = [text_str, list(gt_text_locations[text_index]), list(image_location)]
                draw_style = DrawStyle.GT_TEXT.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          type_id,
                                                                          detail_data,
                                                                          over_frame_text_image_list,
                                                                          lqa_img,
                                                                          ocr_location,
                                                                          draw_style,
                                                                          sub_type_id=sub_type_id)
        return res, check_detail, rect_img, lqa_img

    @staticmethod
    def judge_single_group_overlap_text(check_type, group_index, overlap_group, overlap_group_id,
                                        img,  gt_text_locations, all_ocr_dict,
                                        classify_text_location_res, text_location_list,
                                        overlap_list, over_frame_text_text_list, error_trans_list,
                                        lqa_img, rect_img, res, check_detail, error_trans_marks,
                                        project=None):
        """检测每一组重叠文本框
        :param check_type: list, 异常检测类型
        :param group_index: int, 处理的第 group_index 组文本框
        :param overlap_group: list, 重叠文本框信息
        :param overlap_group_id: list, 重叠文本框分组信息 (记录文本框索引)
        :param img: ndarray, 原图像
        :param gt_text_locations: list, 标准文本框位置信息
        :param all_ocr_dict: dict, 全图 ocr 识别结果
        :param classify_text_location_res: dict, 文本框分类结果
        :param text_location_list: dict, 预处理后文本框信息
        :param overlap_list: list, 半监督文本框重叠信息
        :param over_frame_text_text_list: list, 半监督文本超框信息
        :param error_trans_list: list, 半监督错译信息
        :param lqa_img: ndarray, 结果图像
        :param rect_img: ndarray, 标记图像
        :param res: dict, 结果
        :param check_detail: dict, 结果详情
        :param error_trans_marks: str, 错译标识
        :param project: str, 指定调用项目
        :return: res, check_detail, rect_img, lqa_img
        """
        x1, y1, x2, y2 = overlap_group[group_index]
        group_id = overlap_group_id[group_index]
        img_location = img[y1:y2, x1: x2]
        text_data = ocr(mat_to_base64(img_location), project=project)
        if not text_data:
            return res, check_detail, rect_img, lqa_img
        text_location = (x1, y1, x2, y2)
        align_res, align_ocr_res = LqaProcessing.align_ocr_location(text_location, img_location,
                                                                    text_data, all_ocr_dict,
                                                                    merge_location=False,
                                                                    extend=False)
        # 判断重叠文本框归属
        overlap_info = OverlapText.judge_overlap_ocr_belong(align_res, align_ocr_res, group_id,
                                                            gt_text_locations)
        # OCR 识别结果和重叠文本框数相同
        if len(overlap_info) == len(group_id):
            supervised_info = {'error_trans': error_trans_list,
                               'over_frame_text_text': over_frame_text_text_list
                               }
            res, check_detail, rect_img, lqa_img = OverlapText.check_every_overlap_ocr(check_type,
                                                                                       rect_img,
                                                                                       lqa_img,
                                                                                       overlap_info,
                                                                                       text_location_list,
                                                                                       gt_text_locations,
                                                                                       res,
                                                                                       check_detail,
                                                                                       supervised_info,
                                                                                       error_trans_marks)
        else:
            group_text_id = classify_text_location_res['overlap_group_id'][group_index]
            detail_data = OverlapText.sorted_detail_data(group_text_id, text_location_list, gt_text_locations)
            supervised_info = {'overlap': overlap_list}
            for g_id in overlap_info:
                # 判断每个文本框
                for overlap_item_i in overlap_info[g_id]:
                    res, check_detail, rect_img, lqa_img = OverlapText.recheck_every_overlap_ocr(
                        check_type, img, rect_img, lqa_img, overlap_item_i, group_id, gt_text_locations,
                        res, check_detail, detail_data, supervised_info)
        return res, check_detail, rect_img, lqa_img

    @staticmethod
    def judge_single_text_no_ocr(check_type, language, text_index, img, gt_image_info, gt_text_locations, overlap_dict,
                                 all_ocr_dict, all_ocr_error_trans_dict,
                                 no_trans_list, error_trans_list, over_frame_text_text_list, over_frame_text_image_list,
                                 no_key_list,  non_problem_list, non_rectangle_list,
                                 text_location_list, lqa_img, rect_img, res, check_detail,
                                 no_trans_marks, error_trans_marks, non_rectangle=False, project=None):
        """针对每一个文本框做判断和检查 (精准位置, 无 ocr 检测)
        :param check_type: list, 异常检测类型
        :param language: int, 语种 id
        :param text_index: int, 处理的第 text_index 个文本框
        :param img: ndarray, 原图像
        :param gt_image_info: dict, 标准图像框信息
        :param gt_text_locations: list, 标准文本框位置信息
        :param all_ocr_dict: dict, 全图ocr识别结果
        :param all_ocr_error_trans_dict, dict, 所有包含错误翻译标记的 ocr 识别结果
        :param no_trans_list: list, 半监督漏译信息
        :param error_trans_list: list, 半监督错译信息
        :param over_frame_text_text_list: list, 半监督文本超框信息
        :param over_frame_text_image_list: list, 半监督文本超图像框信息
        :param no_key_list: list, 半监督漏 key 信息
        :param non_problem_list: list, 半监督 non_problem 信息
        :param non_rectangle_list: list, 半监督 non_rectangle 信息
        :param text_location_list: list, 半监督预处理后的文本信息
        :param lqa_img: ndarray, 结果图像
        :param rect_img: ndarray, 标记图像
        :param res: dict, 结果
        :param check_detail: dict, 结果详情
        :param no_trans_marks: str, 漏译标识
        :param error_trans_marks: str, 错译标识
        :param non_rectangle: bool, 非标框, 默认都是标准框, 非标框不做碰撞检测
        :param project: str, 指定调用项目
        :return: res, check_detail, rect_img, lqa_img
        """
        # 判断每一个文本框

        text_location_dict = text_location_list[text_index]
        text_str = text_location_dict.get("textStr")
        detail_data = [text_str, list(gt_text_locations[text_index])]

        # 非标准框检测标记
        check_type_id = LqaCheckType.NON_RECTANGLE.value
        if check_type is None or str(check_type_id) in check_type:
            if non_rectangle:
                draw_style = DrawStyle.NON_RECTANGLE.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          non_rectangle_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 错译-全局判断
        check_type_id = LqaCheckType.ERROR_TRANS.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.error_trans(text_str,
                                                  gt_text_locations[text_index],
                                                  all_ocr_error_trans_dict,
                                                  error_trans_marks,
                                                  check_type='all')
            if is_abnormal:
                draw_style = DrawStyle.ERROR_TRANS.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          error_trans_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 自定义类型检测 non_problem 标记
        check_type_id = LqaCheckType.NON_PROBLEM.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.custom_abnormal(text_str, tag_text=NON_PROBLEM_MARK)
            if is_abnormal:
                draw_style = DrawStyle.NON_PROBLEM.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          non_problem_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        # 漏译检测
        check_type_id = LqaCheckType.NO_TRANS.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.no_trans(text_str, no_trans_marks)
            if is_abnormal:
                draw_style = DrawStyle.NO_TRANS.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          no_trans_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)
        # 漏 key 检测
        check_type_id = LqaCheckType.NO_KEY.value
        if check_type is None or str(check_type_id) in check_type:
            is_abnormal = LqaAbnormal.no_key(text_str, language)
            if is_abnormal:
                draw_style = DrawStyle.NO_KEY.value
                res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                          check_detail,
                                                                          check_type_id,
                                                                          detail_data,
                                                                          no_key_list,
                                                                          lqa_img,
                                                                          gt_text_locations[text_index],
                                                                          draw_style)

        if not non_rectangle:  # 标准文本框
            x1, y1, x2, y2 = gt_text_locations[text_index]

            # 文本框和文本框重叠
            type_id = LqaCheckType.OVER_FRAME.value
            sub_type_id = LqaCheckSubType.OVER_FRAME_TEXT_TEXT.value
            check_type_id = str(type_id) + "-" + str(sub_type_id)
            if check_type is None or check_type_id in check_type:
                is_abnormal = True if len(overlap_dict[text_index]) > 1 else False
                if is_abnormal:
                    draw_style = DrawStyle.GT_TEXT.value
                    res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                              check_detail,
                                                                              type_id,
                                                                              detail_data,
                                                                              over_frame_text_text_list,
                                                                              lqa_img,
                                                                              gt_text_locations[text_index],
                                                                              draw_style,
                                                                              sub_type_id=sub_type_id)

            # 文本框和图像框重叠
            type_id = LqaCheckType.OVER_FRAME.value
            sub_type_id = LqaCheckSubType.OVER_FRAME_TEXT_IMAGE.value
            check_type_id = str(type_id) + "-" + str(sub_type_id)
            if check_type is None or check_type_id in check_type:
                ocr_location = (x1, y1, x2, y2)
                collision, image_location = LqaAbnormal.ocr_image_overlap(img, gt_image_info, ocr_location)
                if collision and image_location is not None:
                    detail_data = [text_str, list(gt_text_locations[text_index]), list(image_location)]
                    draw_style = DrawStyle.GT_TEXT.value
                    res, check_detail, lqa_img = LqaAbnormal.update_check_res(res,
                                                                              check_detail,
                                                                              type_id,
                                                                              detail_data,
                                                                              over_frame_text_image_list,
                                                                              lqa_img,
                                                                              ocr_location,
                                                                              draw_style,
                                                                              sub_type_id=sub_type_id)
        return res, check_detail, rect_img, lqa_img


if __name__ == '__main__':
    pass
