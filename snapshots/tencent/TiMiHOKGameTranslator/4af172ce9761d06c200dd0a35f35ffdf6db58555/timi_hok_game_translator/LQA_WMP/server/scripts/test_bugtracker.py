"""
缺陷系统适配器测试: 用本地模拟服务验证 Bugzilla / 禅道 适配器的请求格式与状态流转
用法 (需要可用的 MySQL/Redis, 即 .env 配置):
    python scripts/test_bugtracker.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
import django  # noqa: E402

django.setup()

from libs import bugtracker  # noqa: E402
from libs.bugtracker import BugPayload, BugTrackerError  # noqa: E402

CALLS = []


class MockHandler(BaseHTTPRequestHandler):
    bugs = {}
    seq = 100

    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_GET(self):
        self._dispatch('GET', {})

    def do_POST(self):
        self._dispatch('POST', self._body())

    def do_PUT(self):
        self._dispatch('PUT', self._body())

    def _dispatch(self, method, body):
        url = urlparse(self.path)
        CALLS.append((method, url.path, dict(self.headers), body, parse_qs(url.query)))
        if url.path.startswith('/rest/'):
            return self._bugzilla(method, url, body)
        if url.path.startswith('/api.php/v1/'):
            return self._zentao(method, url, body)
        self._send(404, {'error': 'not found'})

    # ------------------------------------------------------------ Bugzilla
    def _bugzilla(self, method, url, body):
        if self.headers.get('X-BUGZILLA-API-KEY') != 'bz-key':
            return self._send(401, {'error': True, 'code': 410, 'message': 'invalid api key'})
        path = url.path[len('/rest/'):]
        if method == 'POST' and path == 'bug':
            MockHandler.seq += 1
            MockHandler.bugs[f'bz{MockHandler.seq}'] = {'status': 'CONFIRMED', 'is_open': True,
                                                         'assigned_to': body.get('assigned_to', '')}
            return self._send(200, {'id': MockHandler.seq})
        if method == 'POST' and path.endswith('/attachment'):
            return self._send(201, {'ids': ['9001']})
        if method == 'POST' and path.endswith('/comment'):
            return self._send(201, {'id': 77})
        if method == 'GET' and path == 'bug':
            ids = parse_qs(url.query)['id'][0].split(',')
            bugs = [{'id': int(i), 'summary': 's', 'status': MockHandler.bugs[f'bz{i}']['status'],
                     'resolution': 'FIXED' if MockHandler.bugs[f'bz{i}']['status'] == 'RESOLVED' else '',
                     'is_open': MockHandler.bugs[f'bz{i}']['is_open'], 'assigned_to': 'dev@example.com',
                     'creator': 'qa@example.com', 'priority': 'High', 'severity': 'major'}
                    for i in ids if f'bz{i}' in MockHandler.bugs]
            return self._send(200, {'bugs': bugs})
        if method == 'PUT' and path.startswith('bug/'):
            bug = MockHandler.bugs[f'bz{path.split("/")[1]}']
            bug['status'] = body['status']
            bug['is_open'] = body['status'] not in ('RESOLVED', 'VERIFIED', 'CLOSED') or body['status'] == 'RESOLVED'
            return self._send(200, {'bugs': [{'id': 1, 'changes': {}}]})
        if method == 'GET' and path == 'product':
            return self._send(200, {'products': [{'name': 'Game', 'versions': [{'name': '1.0', 'is_active': True}],
                                                  'milestones': [{'name': 'M1', 'is_active': True}]}]})
        if method == 'GET' and path == 'whoami':
            return self._send(200, {'name': 'qa@example.com'})
        if method == 'GET' and path == 'field/bug':
            return self._send(200, {'fields': [
                {'name': 'cf_platform', 'display_name': '平台', 'is_custom': True, 'values': [{'name': 'PC'}]},
                {'name': 'short_desc', 'display_name': 'Summary', 'is_custom': False}]})
        self._send(404, {'error': True, 'code': 32000, 'message': f'unknown {method} {path}'})

    # ------------------------------------------------------------ 禅道
    def _zentao(self, method, url, body):
        path = url.path[len('/api.php/v1/'):]
        if method == 'POST' and path == 'tokens':
            if body.get('password') != 'zt-pass':
                return self._send(400, {'error': '登录失败'})
            return self._send(201, {'token': 'zt-token'})
        if self.headers.get('Token') != 'zt-token':
            return self._send(401, {'error': 'Unauthorized'})
        if method == 'POST' and path == 'products/3/bugs':
            MockHandler.seq += 1
            MockHandler.bugs[f'zt{MockHandler.seq}'] = {'status': 'active'}
            return self._send(201, {'id': MockHandler.seq, 'status': 'active'})
        parts = path.split('/')
        if parts[0] == 'bugs' and len(parts) >= 2:
            bug = MockHandler.bugs.get(f'zt{parts[1]}')
            if not bug:
                return self._send(404, {'error': 'not found'})
            if method == 'GET' and len(parts) == 2:
                return self._send(200, {'id': int(parts[1]), 'title': 't', 'status': bug['status'], 'pri': 2,
                                        'severity': 2, 'deleted': False,
                                        'openedBy': {'account': 'qa'}, 'assignedTo': {'account': 'dev'},
                                        'resolvedBy': {'account': 'dev2'} if bug['status'] == 'resolved' else None})
            action = parts[2]
            if action == 'resolve':
                bug['status'] = 'resolved'
            elif action == 'close':
                if bug['status'] != 'resolved':
                    return self._send(400, {'error': '只能关闭已解决的Bug'})
                bug['status'] = 'closed'
            elif action == 'active':
                bug['status'] = 'active'
            return self._send(200, {'id': int(parts[1]), 'status': bug['status']})
        if method == 'GET' and path == 'products/3':
            return self._send(200, {'id': 3, 'name': '游戏A'})
        if method == 'GET' and path == 'products/3/plans':
            return self._send(200, {'plans': [{'id': 8, 'title': '1.0 发布'}]})
        if method == 'GET' and path == 'projects/5/builds':
            return self._send(200, {'builds': [{'id': 12, 'name': 'build-12'}]})
        self._send(404, {'error': f'unknown {method} {path}'})


def last_call(method, path_part):
    for c in reversed(CALLS):
        if c[0] == method and path_part in c[1]:
            return c
    raise AssertionError(f'未找到请求 {method} {path_part}')


def ok(cond, title):
    if not cond:
        print(f'[FAIL] {title}')
        sys.exit(1)
    print(f'[ OK ] {title}')


def main():
    # 确保禅道截图走 <img> 内嵌分支 (不依赖 .env 的 PUBLIC_URL 配置)
    import settings
    settings.PUBLIC_URL = 'http://lqa.test'
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    img = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    img.write(b'\x89PNG\r\n\x1a\nfake')
    img.close()
    payload = BugPayload(lqa_bug_id=1, title='【LQA】漏译', description='<p>步骤<br>1.页面中【KEY】存在 漏译 问题</p>',
                         priority=2, severity=1, version_report='1.0', version_fix='M1', assignees=['dev', 'dev3'],
                         reporter='qa', custom_fields={'cf_platform': 'PC'})

    # ======================================================= Bugzilla
    try:
        bugtracker.get_tracker(1, {'tracker_type': 'bugzilla', 'base_url': base})
        ok(False, 'Bugzilla 缺少配置时报错')
    except BugTrackerError:
        ok(True, 'Bugzilla 缺少配置时报错')
    bz = bugtracker.get_tracker(1, {'tracker_type': 'bugzilla', 'base_url': base + '/', 'api_key': 'bz-key',
                                    'product': 'Game', 'component': 'UI', 'extra': {'assignee_field': 'name'}})
    ok(bz.test_connection().startswith('连接成功'), 'Bugzilla 测试连接')
    bug_id = bz.create_bug(payload, [img.name])
    _, _, headers, body, _ = last_call('POST', '/rest/bug')
    c = [x for x in CALLS if x[0] == 'POST' and x[1] == '/rest/bug'][-1]
    body = c[3]
    ok(body['product'] == 'Game' and body['component'] == 'UI' and body['version'] == '1.0'
       and body['priority'] == 'High' and body['severity'] == 'critical' and body['target_milestone'] == 'M1'
       and body['assigned_to'] == 'dev' and body['cc'] == ['dev3'] and body['cf_platform'] == 'PC'
       and '<' not in body['description'] and '1.页面中【KEY】存在 漏译 问题' in body['description'],
       'Bugzilla 创建缺陷字段映射 (HTML 转纯文本、优先级/严重程度映射、自定义字段)')
    att = last_call('POST', '/attachment')[3]
    ok(att['ids'] == [int(bug_id)] and att['content_type'] == 'image/png' and att['data'], 'Bugzilla 上传截图附件')
    ok(bz.bug_url(bug_id) == f'{base}/show_bug.cgi?id={bug_id}', 'Bugzilla 缺陷链接')
    ok(bz.get_bugs([bug_id])[bug_id].is_open, 'Bugzilla 查询缺陷状态')
    ok(bz.get_options()['version_report_list'] == [{'value': '1.0', 'label': '1.0'}], 'Bugzilla 版本选项')
    ok([f['key'] for f in bz.get_fields()] == ['cf_platform'], 'Bugzilla 自定义字段列表')
    bz.close_bug(bug_id, '回归通过')
    put = last_call('PUT', f'/rest/bug/{bug_id}')[3]
    ok(put['status'] == 'RESOLVED' and put['resolution'] == 'FIXED', 'Bugzilla 回归通过 -> RESOLVED/FIXED')
    bz.reopen_bug(bug_id, '<p>回归不通过</p>', [img.name], 'dev2')
    put = last_call('PUT', f'/rest/bug/{bug_id}')[3]
    ok(put['status'] == 'CONFIRMED' and put['assigned_to'] == 'dev2' and put['comment']['body'] == '回归不通过',
       'Bugzilla 回归不通过 -> 重新打开并指派')
    bz.reopen_bug(bug_id, '仍未修复', [], '')
    ok(last_call('POST', '/comment')[3]['comment'] == '仍未修复', 'Bugzilla 缺陷仍打开时只追加评论')
    bad = bugtracker.get_tracker(1, {'tracker_type': 'bugzilla', 'base_url': base, 'api_key': 'x', 'product': 'Game'})
    try:
        bad.get_options()
        ok(False, 'Bugzilla 错误的 API Key')
    except BugTrackerError as err:
        ok('HTTP 401' in str(err), 'Bugzilla 错误的 API Key 返回明确错误')

    # ======================================================= 禅道
    zt = bugtracker.get_tracker(1, {'tracker_type': 'zentao', 'base_url': base, 'username': 'qa',
                                    'api_key': 'zt-pass', 'product': '3', 'extra': {'project_id': 5}})
    from libs import cache
    cache.get_redis_client().delete(f'{cache.BASE_KEY}{zt._token_key}')
    ok(zt.test_connection() == '连接成功, 产品: 游戏A', '禅道 测试连接 (获取 Token)')
    bug_id = zt.create_bug(payload, [img.name])
    body = last_call('POST', '/products/3/bugs')[3]
    ok(body['pri'] == 2 and body['severity'] == 1 and body['openedBuild'] == ['1.0'] and body['type'] == 'others'
       and body['assignedTo'] == 'dev' and '<p>步骤' in body['steps'] and '<img' in body['steps'],
       '禅道 创建缺陷字段映射 (重现步骤内嵌截图)')
    ok(zt.get_bugs([bug_id, '99999'])[bug_id].status == 'active' and '99999' not in zt.get_bugs(['99999']),
       '禅道 查询缺陷 (不存在的缺陷不返回)')
    opts = zt.get_options()
    ok(opts['version_report_list'][1] == {'value': '12', 'label': 'build-12'}
       and opts['release_id_list'] == [{'value': '8', 'label': '1.0 发布'}], '禅道 版本/计划选项')
    zt.close_bug(bug_id, '回归通过')
    ok(MockHandler.bugs[f'zt{bug_id}']['status'] == 'closed' and last_call('POST', '/resolve'),
       '禅道 回归通过: 激活状态先解决再关闭')
    zt.reopen_bug(bug_id, '<p>回归不通过</p>', [img.name], '')
    active = last_call('POST', f'/bugs/{bug_id}/active')[3]
    ok(MockHandler.bugs[f'zt{bug_id}']['status'] == 'active' and active['openedBuild'] == ['trunk']
       and '回归不通过' in active['comment'], '禅道 回归不通过 -> 激活')

    # Token 过期自动刷新
    cache.get_redis_client().set(f'{cache.BASE_KEY}{zt._token_key}', 'expired-token')
    ok(zt.get_bugs([bug_id])[bug_id].status == 'active', '禅道 Token 失效后自动重新获取')

    os.unlink(img.name)
    server.shutdown()
    print('\n缺陷系统适配器测试全部通过')


if __name__ == '__main__':
    main()
