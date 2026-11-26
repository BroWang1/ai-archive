# -*- coding: utf-8 -*-
"""
# @file: smoke_test.py
# @desc: 本地冒烟测试: 用 tests/test/ 下的样例批量调用 lqa_check 接口

读取 tests/test/ 目录下各样例子目录 (由 `tests/gen_samples.py` 生成,
每个子目录含 screenShot.png + v3_result.json), 依次携带
project-method 请求头调用 /image/lqa_check/ 接口, 统计每个样例的:
    - 请求是否成功 (HTTP 状态码、success 字段)
    - 接口响应耗时
    - 是否判定为 overframe (存在异常)
    - 检出的异常类型数量及前 5 个类型 id (check_detail)
    - 是否返回了标记图 (mark_img)

偏向服务级健康检查 (service smoke test): 只验证接口能否正常跑通、
不报错、不超时, 不对具体检测结果的正确性做断言, 若样例目录
不存在或为空, 会提示先运行 gen_samples.py 生成样例

用法:
    python tests/smoke_test.py [host:port] [project]

参数说明:
    host:port   LQA 服务地址, 默认 127.0.0.1:8086
    project     project-method 请求头中的项目标识, 默认 lqa
                (实际请求头为 "<project>_lqa")

例:
    python tests/smoke_test.py 127.0.0.1:8086 lqa

退出码: 0 表示全部样例通过, 1 表示存在失败样例或样例目录缺失/为空
"""
import os
import sys
import json
import time
import base64

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(BASE_DIR, 'tests', 'test')


def run_case(url, headers, case_path):
    img_file = os.path.join(case_path, 'screenShot.png')
    json_file = os.path.join(case_path, 'v3_result.json')
    if not (os.path.exists(img_file) and os.path.exists(json_file)):
        return None

    with open(img_file, 'rb') as f:
        img_base64 = base64.b64encode(f.read()).decode('ascii')
    with open(json_file, 'rb') as f:
        rect_locations = json.load(f)

    body = {
        'img_base64': img_base64,
        'rect_locations': rect_locations,
        'language': None,
        'supervised': None,
    }
    start = time.time()
    resp = requests.post(url, json=body, headers=headers, timeout=300)
    cost = time.time() - start
    if resp.status_code != 200:
        return {'ok': False, 'msg': 'HTTP %s' % resp.status_code, 'cost': cost}

    data = json.loads(resp.text)
    if not data.get('success'):
        return {'ok': False, 'msg': data.get('err_msg'), 'cost': cost}

    result = data.get('result') or {}
    detail = result.get('check_detail') or {}
    return {
        'ok': True,
        'cost': cost,
        'overframe': result.get('overframe'),
        'detail_count': len(detail),
        'types': sorted(detail.keys())[:5],
        'has_mark_img': bool(result.get('mark_img')),
    }


def main():
    hostport = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1:8086'
    project = sys.argv[2] if len(sys.argv) > 2 else 'lqa'
    url = 'http://%s/image/lqa_check/' % hostport
    headers = {'project-method': '%s_lqa' % project}

    if not os.path.isdir(CASE_DIR):
        print('未找到样例目录: %s' % CASE_DIR)
        print('\n真实游戏截图涉及版权未随仓库发布, 请先生成合成样例:')
        print('    python tests/gen_samples.py')
        return 1

    cases = sorted(os.listdir(CASE_DIR), key=lambda x: int(x) if x.isdigit() else 1 << 30)
    passed = failed = skipped = 0
    print('目标: %s  project-method: %s\n' % (url, headers['project-method']))
    for name in cases:
        case_path = os.path.join(CASE_DIR, name)
        if not os.path.isdir(case_path):
            continue
        res = run_case(url, headers, case_path)
        if res is None:
            skipped += 1
            continue
        if res['ok']:
            passed += 1
            print('[PASS] case %-4s %.2fs overframe=%-5s 异常数=%-3d %s'
                  % (name, res['cost'], res['overframe'], res['detail_count'],
                     ','.join(res['types']) if res['types'] else ''))
        else:
            failed += 1
            print('[FAIL] case %-4s %.2fs %s' % (name, res['cost'], res['msg']))

    if passed == 0 and failed == 0:
        print('样例目录为空: %s' % CASE_DIR)
        print('\n请先生成合成样例: python tests/gen_samples.py')
        return 1

    print('\n合计: 通过 %d, 失败 %d, 跳过 %d' % (passed, failed, skipped))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
