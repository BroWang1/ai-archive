# -*- coding: utf-8 -*-
"""
# @file: test_image_extraction.py
# @desc: 图像前景提取服务 HTTP 接口测试脚本 (基于 unittest), 提供 ImageExtractionTestCase 类:
#        - batch_test: 遍历指定数据目录下所有 .png 图片, 批量读取并转为 base64,
#                     汇总为 {文件名: base64图像数据, ...} 字典, 作为批量请求数据
#        - setUp: 准备测试数据 (调用 batch_test), 并设置默认坐标参数
#                     zero_type=1(左下角为原点)、position_type=1(比例坐标)、alpha_t=0
#        - test_image_extraction: 携带批量图像数据调用 /image/image_extraction/
#                     接口, 打印返回的各图像前景提取结果 (image_extraction字段)
#
#        与 test_image_extractation_local.py 的区别: 本脚本经过真实 HTTP 请求,
#        用于验证接口层 (Flask 路由、请求/响应序列化) 是否正常工作, 而非仅验证
#        底层算法逻辑
#
#        服务地址与测试数据目录均可通过环境变量覆盖:
#          LQA_TEST_HOST / LQA_TEST_PORT / LQA_TEST_DATA_DIR
#
#        用法: python tests/test_image_extractation.py (或 python -m unittest)
"""
import os
import base64
import unittest
import requests


class ImageExtractionTestCase(unittest.TestCase):
    # 可通过环境变量覆盖: LQA_TEST_HOST / LQA_TEST_PORT / LQA_TEST_DATA_DIR
    host = os.getenv("LQA_TEST_HOST", "127.0.0.1")
    port = int(os.getenv("LQA_TEST_PORT", "8086"))

    def batch_test(self, data_dir):
        """ 生成批量测试数据
        :param data_dir: str, 测试数数据目录
        :return: dict, 测试数据 (base64 图像)
        """
        img_base64_batch = {}
        for path, _, files in os.walk(data_dir):
            for file in files:
                if file.endswith('.png'):
                    img_path = os.path.join(path, file)
                    f = open(img_path, "rb")
                    img_base64 = base64.b64encode(f.read()).decode("ascii")
                    if img_base64:
                        img_base64_batch[file] = img_base64
                    f.close()
        return img_base64_batch

    def setUp(self):
        data_dir = os.getenv(
            "LQA_TEST_DATA_DIR",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test'))
        self.img_base64 = self.batch_test(data_dir)
        self.zero_type = 1
        self.position_type = 1
        self.alpha_t = 0

    def test_image_extraction(self):
        path = "/image/image_extraction/"
        body = {
            "img_base64": self.img_base64,
            "zero_type": self.zero_type,
            "position_type": self.position_type,
            "alpha_t": self.alpha_t
        }
        url = f"http://{self.host}:{self.port}{path}"
        print(url)
        res = requests.post(url, json=body)
        print(res.status_code)
        if res.status_code == 200:
            res_dict = res.json()
            if res_dict["success"]:
                result = res_dict["result"]['image_extraction']
                print(result)
            else:
                print(res_dict["err_msg"])
        else:
            print(res.status_code)


if __name__ == '__main__':
    unittest.main()
