"""
后端接口冒烟测试 (不依赖外部系统)
用法:
    python scripts/smoke_test.py http://127.0.0.1:8000 admin Admin123456
会在库中创建以 smoke_ 开头的测试项目与用户
"""
import sys
import time
import uuid

import requests

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
ADMIN, ADMIN_PWD = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ('admin', 'Admin123456')

_passed = 0


def check(cond, title, resp=None):
    global _passed
    if not cond:
        detail = f' -> HTTP {resp.status_code} {resp.text[:300]}' if resp is not None else ''
        print(f'[FAIL] {title}{detail}')
        sys.exit(1)
    _passed += 1
    print(f'[ OK ] {title}')


def api(s, method, path, **kw):
    return s.request(method, BASE + path, timeout=20, **kw)


def main():
    suffix = uuid.uuid4().hex[:6]
    anon = requests.Session()

    r = api(anon, 'GET', '/api/user/entity')
    check(r.status_code == 401 and r.json()['code'] == 1003, '未登录访问返回 401/1003', r)

    r = api(anon, 'POST', '/api/user/login', json={'username': ADMIN, 'password': 'wrong-pass1'})
    check(r.json()['code'] == 1003 and '还可尝试' in r.json()['msg'], '错误密码登录被拒绝并提示剩余次数', r)

    admin = requests.Session()
    r = api(admin, 'POST', '/api/user/login', json={'username': ADMIN, 'password': ADMIN_PWD})
    check(r.json()['code'] == 0, '超级管理员登录', r)
    r = api(admin, 'GET', '/api/user/entity')
    user = r.json()['data']['user']
    check(user['is_admin'] == 1 and 'password' not in user, '获取当前用户 (不返回密码哈希)', r)

    # ---- 注册
    username = f'smoke_{suffix}'
    r = api(anon, 'POST', '/api/user/register', json={'username': username, 'password': '123'})
    check(r.json()['code'] == 1001, '弱密码注册被拒绝', r)
    r = api(anon, 'POST', '/api/user/register', json={'username': username, 'password': 'Smoke12345', 'name_zh': '冒烟'})
    check(r.json()['code'] == 0, '自助注册', r)
    r = api(anon, 'POST', '/api/user/register', json={'username': username, 'password': 'Smoke12345'})
    check(r.json()['code'] != 0, '重复用户名注册被拒绝', r)

    member = requests.Session()
    r = api(member, 'POST', '/api/user/login', json={'username': username, 'password': 'Smoke12345'})
    check(r.json()['code'] == 0, '新用户登录', r)
    r = api(member, 'GET', '/api/user/permission')
    check(r.json()['data']['projects'] == [], '新注册用户没有任何项目 (需管理员分配)', r)

    # ---- 项目
    code = f'smoke_{suffix}'
    r = api(admin, 'POST', '/api/project/entity', json={
        'code': code, 'name': f'冒烟项目{suffix}', 'project_type': 2, 'project_phase': 3, 'game_type': 1,
        'team': 'QA', 'cvtest_project': 'demo'})
    check(r.json()['code'] == 0, '创建项目', r)
    project_id = r.json()['data']['project']['id']

    r = api(member, 'GET', f'/api/project/config?project_id={project_id}&cate=BugTracker')
    check(r.json()['code'] == 1006, '非项目成员不能读取项目配置', r)

    r = api(admin, 'GET', '/api/user/list', params={'name': username, 'info_type': 0})
    uid = r.json()['data']['list'][0]['id']
    r = api(admin, 'PATCH', '/api/user/entity', json={'id': uid, 'roles': [f'{project_id}_2']})
    check(r.json()['code'] == 0, '管理员为新用户分配 “测试人员” 角色', r)
    r = api(member, 'GET', '/api/user/permission')
    check([p['id'] for p in r.json()['data']['projects']] == [project_id], '成员获得项目权限', r)

    # ---- 缺陷系统配置 (密钥掩码)
    r = api(admin, 'PATCH', '/api/project/config?cate=BugTracker', json={
        'project_id': project_id, 'tracker_type': 'bugzilla', 'base_url': 'http://127.0.0.1:9',
        'api_key': 'secret-key', 'product': 'P', 'component': 'C'})
    check(r.json()['code'] == 0 and r.json()['data']['config']['api_key'] == '******', '保存缺陷系统配置 (返回掩码)', r)
    r = api(admin, 'PATCH', '/api/project/config?cate=BugTracker', json={
        'project_id': project_id, 'tracker_type': 'bugzilla', 'base_url': 'http://127.0.0.1:9',
        'api_key': '******', 'product': 'P2', 'component': 'C'})
    r = api(member, 'GET', f'/api/project/config?project_id={project_id}&cate=BugTracker')
    cfg = r.json()['data']['list'][0]
    check(cfg['api_key'] == '******' and cfg['product'] == 'P2', '回传掩码不覆盖已保存的密钥', r)
    r = api(member, 'POST', '/api/bug/tracker_test', json={'project_id': project_id, 'tracker_type': 'bugzilla'})
    check(r.json()['code'] == 1006, '非项目管理员不能测试缺陷系统连接', r)
    r = api(admin, 'POST', '/api/bug/tracker_test', json={
        'project_id': project_id, 'tracker_type': 'bugzilla', 'base_url': 'http://127.0.0.1:9',
        'api_key': '******', 'product': 'P2'})
    check(r.json()['code'] == 1000 and 'Bugzilla' in r.json()['msg'], '缺陷系统不可达时返回明确错误', r)
    r = api(admin, 'PATCH', '/api/project/config?cate=BugTracker', json={'project_id': project_id, 'tracker_type': 'none'})
    r = api(member, 'GET', f'/api/bug/tracker_meta?project_id={project_id}')
    check(r.json()['data']['type'] == 'none', '切换为 “平台内记录”', r)

    # ---- 还原执行 (Webhook)
    r = api(admin, 'PATCH', '/api/project/config?cate=Other', json={
        'project_id': project_id, 'webhook_url': 'not-a-url'})
    check(r.json()['code'] == 1001, 'Webhook 地址格式校验', r)
    r = api(admin, 'PATCH', '/api/project/config?cate=Other', json={
        'project_id': project_id, 'webhook_url': 'https://ci.example.com/job/lqa/buildWithParameters?JOB={{job_id}}',
        'webhook_method': 'POST', 'webhook_headers': '{"Authorization": "Bearer t-{{project_code}}"}',
        'webhook_body': '{"job": "{{job_id}}", "langs": "{{language_values}}", "name": "任务-{{job_name}}"}',
        'editor_path': 'C:/Unity/Editor/Unity.exe'})
    check(r.json()['code'] == 0, '保存 Webhook 配置', r)

    # ---- 任务
    today = time.strftime('%Y-%m-%d 00:00:00')
    r = api(member, 'POST', '/api/job/entity', json={
        'project_id': project_id, 'discern': 1, 'name': f'smoke job {suffix}', 'languages': [2, 6],
        'plan_start_at': today, 'plan_end_at': today, 'trans_res_type': 'git'})
    check(r.json()['code'] == 0, '成员创建任务', r)
    job_id = r.json()['data']['job']['id']

    r = api(member, 'POST', '/api/job/action', json={'action': 'start', 'job_id': job_id})
    data = r.json()['data']
    trigger = data.get('trigger', {})
    check(r.json()['code'] == 0 and trigger.get('url') ==
          f'https://ci.example.com/job/lqa/buildWithParameters?JOB={job_id}', '开始任务: 返回渲染后的 Webhook 地址', r)
    check(trigger['headers']['Authorization'] == f'Bearer t-{code}' and trigger['body']['job'] == job_id
          and trigger['body']['langs'] == [2, 6] and trigger['body']['name'] == f'任务-smoke job {suffix}',
          'Webhook 请求头/请求体变量替换 (保留原始类型)', r)

    r = api(member, 'POST', '/api/job/action', json={'action': 'started', 'job_id': job_id, 'build_id': '#42'})
    check(r.json()['code'] == 0, 'Webhook 调用成功后回调 started', r)
    r = api(member, 'GET', '/api/job/entity', params={'job_id': job_id})
    job = r.json()['data']['job']
    check(job['status'] == 2 and job['build_id'] == '#42', '任务状态变为执行中', r)
    r = api(member, 'POST', '/api/job/action', json={'action': 'start', 'job_id': job_id})
    check(r.json()['code'] != 0, '执行中的任务不能再次开始', r)
    r = api(member, 'POST', '/api/job/action', json={'action': 'stop', 'job_id': job_id})
    check(r.json()['code'] == 0, '结束任务', r)

    outsider = requests.Session()
    other = f'smoke_o_{suffix}'
    api(anon, 'POST', '/api/user/register', json={'username': other, 'password': 'Smoke12345'})
    api(outsider, 'POST', '/api/user/login', json={'username': other, 'password': 'Smoke12345'})
    r = api(outsider, 'POST', '/api/job/action', json={'action': 'start', 'job_id': job_id})
    check(r.json()['code'] == 1006, '非项目成员不能操作任务', r)

    # ---- 密码 / 禁用
    r = api(member, 'POST', '/api/user/password', json={'old_password': 'bad', 'new_password': 'Smoke67890'})
    check(r.json()['code'] != 0, '原密码错误时不能修改密码', r)
    r = api(member, 'POST', '/api/user/password', json={'old_password': 'Smoke12345', 'new_password': 'Smoke67890'})
    check(r.json()['code'] == 0, '修改密码', r)
    r = api(admin, 'POST', '/api/user/reset_password', json={'id': uid, 'new_password': 'Reset12345'})
    check(r.json()['code'] == 0, '超管重置密码', r)
    r = api(requests.Session(), 'POST', '/api/user/login', json={'username': username, 'password': 'Reset12345'})
    check(r.json()['code'] == 0, '使用重置后的密码登录', r)
    r = api(admin, 'PATCH', '/api/user/entity', json={'id': uid, 'status': 0})
    check(r.json()['code'] == 0, '超管禁用账号', r)
    r = api(member, 'GET', '/api/user/entity')
    check(r.json()['code'] == 1003, '被禁用账号的会话立即失效', r)
    r = api(requests.Session(), 'POST', '/api/user/login', json={'username': username, 'password': 'Reset12345'})
    check(r.json()['code'] == 1003 and '禁用' in r.json()['msg'], '被禁用账号不能登录', r)

    # ---- 登出
    r = api(admin, 'POST', '/api/user/logout')
    check(r.json()['code'] == 0, '退出登录', r)
    r = api(admin, 'GET', '/api/user/entity')
    check(r.json()['code'] == 1003, '退出后会话失效', r)

    print(f'\n全部通过: {_passed} 项')


if __name__ == '__main__':
    main()
