# -*- coding: utf-8 -*-
"""
# @file: batch_test_lqa.py
# @desc: LQA 本地化异常检测批量测试脚本 (用于调参、优化算法时批量查看效果), 提供:
#        - test: 单个样例测试, 读取指定目录下的 screenShot.png(截图) + result.json(标准框标注)
#                     + 可选 supervised.json(半监督数据), 调用 /image/lqa_check/ 接口,
#                     并支持将返回的 mark_img(检测标记图)/rect_img(标准框标注图)
#                     本地弹窗展示(show_img)和/或保存到磁盘(save_img)
#        - batch_test: 批量测试入口, 遍历 data_dir 下所有子目录, 对每个包含完整
#                     screenShot.png + result.json 的子目录调用 test 执行检测,
#                     并在每次请求间 sleep(1) 避免过快请求
#        - 服务地址可通过环境变量 LQA_TEST_HOST / LQA_TEST_PORT 覆盖 (默认 127.0.0.1:8086),
#          测试数据目录可通过 LQA_TEST_DATA_DIR 指定 (默认 tests/test/)
"""
import os
import json
import base64
import time
import requests
import cv2
from common.tools import base64_to_mat


def test(data_dir, img_dir, img_path, json_file_path, show_img=True, save_img=False, language=None,
         supervised_file_path=None):
    """lqa 本地化异常检测
    :param data_dir: str, 测试数据目录
    :param img_dir: str, 数据子文件夹
    :param img_path: str, 图片路径
    :param json_file_path: str, 标准信息文件路径
    :param show_img: bool, 是否显示结果图像
    :param save_img: bool, 是否保存结果图像
    :param language: 测试语种
    :param supervised_file_path: str, 半监督信息文件路径
    :return:
    """

    host = os.getenv("LQA_TEST_HOST", "127.0.0.1")
    port = int(os.getenv("LQA_TEST_PORT", "8086"))

    fd = open(img_path, "rb")
    img_base64 = base64.b64encode(fd.read()).decode("ascii")
    load_f = open(json_file_path, 'rb')
    rect_locations = json.load(load_f)
    supervised_data = None
    if supervised_file_path:
        supervised_f = open(supervised_file_path, 'rb')
        supervised_data = json.load(supervised_f)

    path = "/image/lqa_check/"
    body = {
        "img_base64": img_base64,
        "rect_locations": rect_locations,
        "language": language,
        "supervised": supervised_data

    }
    url = f"http://{host}:{port}{path}"
    res = requests.post(url, json=body)
    if res.status_code == 200:
        res_dict = res.json()
        if res_dict["success"]:
            result = res_dict["result"]
            mark_img = base64_to_mat(result["mark_img"])
            rect_img = base64_to_mat(result["rect_img"])
            if save_img:
                mark_img_save_path = os.path.join(data_dir, img_dir, 'mark_img_ocr_finetuning_overlap.png')
                rect_img_save_path = os.path.join(data_dir, img_dir, 'rect_img_ocr_finetuning_overlap.png')
                cv2.imwrite(mark_img_save_path, mark_img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
                cv2.imwrite(rect_img_save_path, rect_img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
            if show_img:
                cv2.namedWindow("mark_img", cv2.WINDOW_NORMAL)
                cv2.imshow("mark_img", mark_img)
                cv2.namedWindow("rect_img", cv2.WINDOW_NORMAL)
                cv2.imshow("rect_img", rect_img)
                cv2.waitKey()
        else:
            print(res_dict["err_msg"])
    else:
        print(res.status_code)


def batch_test(data_dir, show_img=True, save_img=False, language=None):
    """ 批量测试
    :param data_dir: str, 测试数据路径
    :param show_img: bool, 是否显示结果图像
    :param save_img: bool, 是否保存结果图像
    :param language: 测试语种
    :return:
    """
    supervised_file_path = os.path.join(data_dir, 'supervised.json')
    for path, dirs, _ in os.walk(data_dir):
        for img_dir in dirs:
            img_path = os.path.join(path, img_dir, 'screenShot.png')
            json_file_path = os.path.join(path, img_dir, 'result.json')
            if os.path.exists(img_path) and os.path.exists(json_file_path):
                if supervised_file_path is None or not os.path.exists(supervised_file_path):
                    supervised_file_path = None
                test(data_dir, img_dir, img_path, json_file_path,  show_img=show_img, save_img=save_img,
                     language=language, supervised_file_path=supervised_file_path)
                time.sleep(1)


if __name__ == '__main__':
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test')
    batch_test(os.getenv('LQA_TEST_DATA_DIR', default_dir),
               show_img=False, save_img=True, language=None)
