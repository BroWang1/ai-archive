# -*- coding: utf-8 -*-
"""
# @file: gen_samples.py
# @desc: 合成测试样例生成器

真实游戏截图涉及版权, 未随仓库发布, 本脚本用 OpenCV 合成一组
结构等价的样例 (深色背景 + 面板 + 文本, 模拟游戏 UI), 供
`tests/smoke_test.py` 开箱即用, 也可供 `test_lqa.py` /
`batch_test_lqa.py` 等手动指定目录测试

内置样例场景 (CASES):
    0  case_normal              正常界面, 文本均在标准框内, 预期无异常
    1  case_overflow            标准框远小于文本实际占用区域, 可能触发超框
                                 (类型2, 实际是否判定还取决于 OCR 识别结果与阈值)
    2  case_no_trans            文本含 ##/N/A 等未翻译标记, 预期检出漏译 (类型1)
    3  case_missing_text_str    标注数据 textStr 缺失/空串, 验证不应导致服务崩溃
    4  case_overlap             两个标准文本框在 x 轴上相交, 可能触发重叠 (类型4)
    5  case_dense                密集文本场景 (HUD/列表), 用于压力测试
    6  case_no_key               非中文界面混入标注的简体中文 (textStr),
                                 预期检出漏 key (类型3, 基于简繁体字符集比对)

生成结果:
    tests/test/<N>/screenShot.png     合成截图
    tests/test/<N>/v3_result.json     标准文本框(text)/图像框(image)标注,
                                       四点坐标格式 (左上->左下->右下->右上)

用法:
    python tests/gen_samples.py              # 生成到默认目录 tests/test/
    python tests/gen_samples.py --out DIR    # 指定输出目录
    python tests/gen_samples.py --force      # 覆盖已存在的样例 (默认跳过已存在的case)

生成完成后可执行 `python tests/smoke_test.py 127.0.0.1:8086` 批量回归测试
"""
import os
import sys
import json
import argparse

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(BASE_DIR, 'tests', 'test')

FONT = cv2.FONT_HERSHEY_SIMPLEX
BG = (38, 34, 30)          # 深色背景, 接近游戏 UI
PANEL = (70, 62, 52)
TEXT_COLOR = (236, 240, 245)


def _corners(x1, y1, x2, y2):
    """转为标注要求的四点格式: 左上 -> 左下 -> 右下 -> 右上"""
    return [
        {'x': float(x1), 'y': float(y1)},
        {'x': float(x1), 'y': float(y2)},
        {'x': float(x2), 'y': float(y2)},
        {'x': float(x2), 'y': float(y1)},
    ]


def _put_text(img, text, x, y, scale=0.7, thickness=2, color=TEXT_COLOR):
    """绘制文本并返回其实际包围盒"""
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, thickness)
    cv2.putText(img, text, (x, y + th), FONT, scale, color, thickness, cv2.LINE_AA)
    return [x, y, x + tw, y + th + baseline]


class SampleBuilder:
    """逐个构造样例场景"""

    def __init__(self, width=960, height=540):
        self.w, self.h = width, height
        self.img = np.full((height, width, 3), BG, np.uint8)
        self.texts = []
        self.images = []

    def panel(self, x1, y1, x2, y2):
        cv2.rectangle(self.img, (x1, y1), (x2, y2), PANEL, -1)
        cv2.rectangle(self.img, (x1, y1), (x2, y2), (120, 110, 95), 1)
        self.images.append({'corners': _corners(x1, y1, x2, y2)})
        return self

    def text(self, content, x, y, scale=0.7, box=None, text_str=None):
        """绘制文本

        :param box: 显式指定标准框; None 时用文本实际包围盒外扩少许
        :param text_str: 标注中记录的文本; 传 None 模拟 "标准数据缺失文本"
        """
        actual = _put_text(self.img, content, x, y, scale=scale)
        if box is None:
            box = [actual[0] - 4, actual[1] - 4, actual[2] + 4, actual[3] + 4]
        item = {'corners': _corners(*box)}
        if text_str is not False:
            item['textStr'] = content if text_str is None else text_str
        self.texts.append(item)
        return self

    def dump(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        cv2.imwrite(os.path.join(out_dir, 'screenShot.png'), self.img,
                    [cv2.IMWRITE_PNG_COMPRESSION, 3])
        with open(os.path.join(out_dir, 'v3_result.json'), 'w', encoding='utf-8') as f:
            json.dump({'text': self.texts, 'image': self.images}, f,
                      ensure_ascii=False, indent=1)


def case_normal():
    """正常界面: 文本均在框内"""
    b = SampleBuilder()
    b.panel(40, 40, 460, 200)
    b.text('Start Game', 60, 70)
    b.text('Settings', 60, 110)
    b.text('Exit', 60, 150)
    b.panel(500, 40, 900, 200)
    b.text('Player Level 42', 520, 70, scale=0.6)
    b.text('Gold 12800', 520, 110, scale=0.6)
    return b


def case_overflow():
    """超框: 标准框明显小于文本实际占用区域

    注意: 是否判定为超框还取决于 OCR 识别到的实际文本区域与阈值,
    合成图上的表现可能与真实游戏截图不同
    """
    b = SampleBuilder()
    b.panel(40, 40, 500, 220)
    # 标准框只覆盖文本左侧一小段, 文本大幅溢出
    b.text('Confirm Purchase Immediately', 60, 80, scale=0.7, box=[58, 74, 120, 102])
    b.text('OK', 60, 150)
    return b


def case_no_trans():
    """漏译: 包含 ## 等未翻译标记"""
    b = SampleBuilder()
    b.panel(40, 40, 520, 220)
    b.text('##UI_MAIN_TITLE', 60, 70)
    b.text('N/A', 60, 115)
    b.text('Normal Text', 60, 160)
    return b


def case_missing_text_str():
    """标准数据缺失 textStr: 验证空值不应导致崩溃"""
    b = SampleBuilder()
    b.panel(40, 40, 520, 220)
    b.text('Hello World', 60, 70, text_str=False)   # 不写入 textStr
    b.text('Second Line', 60, 120, text_str='')     # 显式空串
    return b


def case_overlap():
    """文本框重叠: 两个标准框在 x 轴上相交"""
    b = SampleBuilder()
    b.panel(40, 40, 600, 240)
    b.text('Attack Power', 60, 80, box=[56, 72, 300, 108])
    b.text('Defense', 200, 90, box=[196, 82, 400, 118])
    return b


def case_no_key():
    """漏 key: 非中文界面中混入简体中文, 触发类型 3

    对应真实场景: 泰文/繁体版本里残留了未替换的简体中文文案
    注意 OpenCV 默认字体不支持中文, 此处用标注文本触发检测,
    图像上以占位符呈现
    """
    b = SampleBuilder()
    b.panel(40, 40, 600, 240)
    # textStr 写入简体中文, 由检测逻辑比对字符集判定
    b.text('[CN]', 60, 80, box=[56, 72, 260, 108], text_str='确认购买')
    b.text('Confirm', 60, 140, box=[56, 132, 260, 168])
    return b


def case_dense():
    """密集文本, 接近真实游戏 HUD"""
    b = SampleBuilder()
    b.panel(30, 30, 930, 110)
    labels = ['HP', 'MP', 'EXP', 'LV', 'ATK', 'DEF', 'SPD']
    for i, label in enumerate(labels):
        b.text(label, 50 + i * 125, 55, scale=0.6)
    b.panel(30, 140, 460, 480)
    for i, name in enumerate(['Inventory', 'Equipment', 'Skills', 'Quests', 'Map']):
        b.text(name, 50, 170 + i * 46, scale=0.65)
    b.panel(500, 140, 930, 480)
    for i, name in enumerate(['Guild', 'Friends', 'Shop', 'Mail', 'Ranking']):
        b.text(name, 520, 170 + i * 46, scale=0.65)
    return b


#: (目录名, 构造函数, 预期说明)
CASES = [
    ('0', case_normal, '正常界面, 预期无异常'),
    ('1', case_overflow, '标准框小于文本, 可能触发超框 (取决于 OCR 与阈值)'),
    ('2', case_no_trans, '含 ## / N/A 标记, 预期检出漏译 (类型1)'),
    ('3', case_missing_text_str, 'textStr 缺失/空, 预期不崩溃且无异常'),
    ('4', case_overlap, '标准框相交, 可能触发重叠'),
    ('5', case_dense, '密集文本压力场景'),
    ('6', case_no_key, '非中文界面混入简体中文, 预期检出漏 key (类型3)'),
]


def main():
    parser = argparse.ArgumentParser(description='生成合成测试样例')
    parser.add_argument('--out', default=DEFAULT_OUT, help='输出目录')
    parser.add_argument('--force', action='store_true', help='覆盖已存在的样例')
    args = parser.parse_args()

    created = skipped = 0
    for name, factory, desc in CASES:
        out_dir = os.path.join(args.out, name)
        marker = os.path.join(out_dir, 'v3_result.json')
        if os.path.exists(marker) and not args.force:
            print('[skip] case %-3s %s' % (name, '已存在 (--force 可覆盖)'))
            skipped += 1
            continue
        factory().dump(out_dir)
        print('[gen ] case %-3s %s' % (name, desc))
        created += 1

    print('\n生成 %d 个, 跳过 %d 个' % (created, skipped))
    if created:
        print('现在可运行: python tests/smoke_test.py 127.0.0.1:8086')
    return 0


if __name__ == '__main__':
    sys.exit(main())
