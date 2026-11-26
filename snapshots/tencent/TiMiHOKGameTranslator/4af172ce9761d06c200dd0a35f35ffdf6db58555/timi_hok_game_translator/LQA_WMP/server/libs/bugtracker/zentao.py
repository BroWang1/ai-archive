"""
禅道 (ZenTao) 开源版 RESTful API v1 适配
文档: https://www.zentao.net/book/api/setting-369.html

项目配置:
  base_url   禅道地址, 如 http://zentao.example.com (不含 /api.php)
  username   API 账号 (需要 Bug 模块的创建/解决/关闭/激活权限, 并关闭 “首次登录强制修改密码”)
  api_key    该账号的密码
  product    产品 ID (数字)
  extra      可选 JSON:
     bug_type          Bug 类型, 默认 others (codeerror/config/install/security/performance/standard/automation/designdefect/others)
     default_build     未选择 “发现版本” 时的影响版本, 默认 trunk (主干)
     project_id        禅道项目 ID, 填写后可拉取该项目的版本列表作为 “发现版本” 选项
     execution_id      禅道执行 ID (可选, 创建 Bug 时关联)
     priority_map / severity_map  覆盖 LQA -> 禅道 优先级(1~4)/严重程度(1~4)映射

说明: 禅道 v1 API 未提供附件上传接口, 截图会以 <img> 形式嵌入重现步骤中,
      需要在 .env 中配置 PUBLIC_URL, 且禅道用户的浏览器能访问 LQA 的 /media/ 路径
"""
from typing import Dict, List

import settings
from libs import cache, storage
from libs.util import md5
from .base import BugTracker, BugTrackerError, BugPayload, TrackerBug

PRIORITY_MAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}
SEVERITY_MAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}
BUG_TYPES = (('codeerror', '代码错误'), ('config', '配置相关'), ('install', '安装部署'), ('security', '安全相关'),
             ('performance', '性能问题'), ('standard', '标准规范'), ('automation', '测试脚本'),
             ('designdefect', '设计缺陷'), ('others', '其他'))
TOKEN_TTL = 60 * 20


def _account(user) -> str:
    """禅道返回的用户字段可能是对象 {account, realname} 也可能是字符串"""
    if isinstance(user, dict):
        return user.get('account', '') or ''
    return user or ''


class ZentaoTracker(BugTracker):
    type = 'zentao'
    label = '禅道'

    def __init__(self, project_id, config=None):
        super().__init__(project_id, config)
        self.account = self.config.get('username', '')
        self.password = self.config.get('api_key', '')
        self.product = str(self.config.get('product', '')).strip()
        if not (self.base_url and self.account and self.password and self.product):
            raise BugTrackerError('禅道配置不完整: 需要地址、账号、密码、产品ID')
        self.api = f'{self.base_url}/api.php/v1'
        self._token_key = f'zentao_token:{md5(f"{self.base_url}|{self.account}")}'

    # ------------------------------------------------------------------ token
    def _token(self, refresh=False):
        client = cache.get_redis_client()
        key = f'{cache.BASE_KEY}{self._token_key}'
        if not refresh:
            token = client.get(key)
            if token:
                return token.decode() if isinstance(token, bytes) else token
        data = self._http('POST', f'{self.api}/tokens', json={'account': self.account, 'password': self.password})
        token = data.get('token')
        if not token:
            raise BugTrackerError(f'禅道获取 Token 失败: {data}')
        client.set(key, token, ex=TOKEN_TTL)
        return token

    def _req(self, method, path, retry=True, **kwargs):
        headers = kwargs.pop('headers', {})
        headers['Token'] = self._token()
        try:
            data = self._http(method, f'{self.api}/{path.lstrip("/")}', headers=headers, **kwargs)
        except BugTrackerError as err:
            if retry and 'HTTP 401' in str(err):
                self._token(refresh=True)
                return self._req(method, path, retry=False, **kwargs)
            raise
        if isinstance(data, dict) and data.get('error'):
            raise BugTrackerError(f'禅道错误: {data.get("error")}')
        return data

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _img_html(abs_paths):
        public_url = (getattr(settings, 'PUBLIC_URL', '') or '').rstrip('/')
        parts = []
        for path in abs_paths:
            if not path:
                continue
            url_path = storage.get_url_path(path)
            if public_url:
                parts.append(f'<p><img src="{public_url}{url_path}" alt="screenshot" /></p>')
            else:
                parts.append(f'<p>截图: {url_path} (未配置 PUBLIC_URL, 无法内嵌图片)</p>')
        return ''.join(parts)

    def _builds(self, value):
        return [value or self.extra.get('default_build', 'trunk')]

    # ------------------------------------------------------------------ 接口
    def create_bug(self, payload: BugPayload, attachments: List[str]) -> str:
        body = {
            'title': payload.title[:255],
            'severity': self._map_value('severity_map', payload.severity or 3, SEVERITY_MAP),
            'pri': self._map_value('priority_map', payload.priority or 3, PRIORITY_MAP),
            'type': self.extra.get('bug_type', 'others'),
            'openedBuild': self._builds(payload.version_report),
            'steps': payload.description + self._img_html(attachments),
        }
        if payload.assignees:
            body['assignedTo'] = payload.assignees[0]
        if self.extra.get('execution_id'):
            body['execution'] = int(self.extra['execution_id'])
        if payload.release_id:
            body['plan'] = payload.release_id
        for key, value in (payload.custom_fields or {}).items():
            body[key] = value
        data = self._req('POST', f'products/{self.product}/bugs', json=body)
        bug_id = str(data.get('id', ''))
        if not bug_id:
            raise BugTrackerError(f'禅道未返回缺陷 ID: {data}')
        return bug_id

    def _get_bug(self, bug_id):
        try:
            return self._req('GET', f'bugs/{bug_id}')
        except BugTrackerError as err:
            if 'HTTP 404' in str(err):
                return None
            raise

    def get_bugs(self, bug_ids: List[str]) -> Dict[str, TrackerBug]:
        ret = {}
        for bug_id in [str(i) for i in bug_ids if i]:
            bug = self._get_bug(bug_id)
            if not bug or bug.get('deleted') in (True, 1, '1'):
                continue
            status = bug.get('status', '')
            ret[bug_id] = TrackerBug(
                id=bug_id, title=bug.get('title', ''), status=status, is_open=status != 'closed',
                assignee=_account(bug.get('assignedTo')), resolver=_account(bug.get('resolvedBy')),
                reporter=_account(bug.get('openedBy')), priority=str(bug.get('pri', '')),
                severity=str(bug.get('severity', '')), url=self.bug_url(bug_id),
            )
        return ret

    def close_bug(self, bug_id: str, comment: str):
        bug = self._get_bug(bug_id)
        if not bug:
            raise BugTrackerError(f'禅道缺陷不存在: {bug_id}')
        if bug.get('status') == 'closed':
            return
        if bug.get('status') == 'active':   # 禅道只能关闭 “已解决” 的缺陷
            self._req('POST', f'bugs/{bug_id}/resolve', json={
                'resolution': 'fixed', 'resolvedBuild': self.extra.get('default_build', 'trunk'), 'comment': comment})
        self._req('POST', f'bugs/{bug_id}/close', json={'comment': comment})

    def reopen_bug(self, bug_id: str, comment: str, attachments: List[str], assignee: str = ''):
        bug = self._get_bug(bug_id)
        if not bug:
            raise BugTrackerError(f'禅道缺陷不存在: {bug_id}')
        if bug.get('status') == 'active':   # 仍处于激活状态, 无需重新激活
            return
        body = {'comment': comment + self._img_html(attachments),
                'openedBuild': self._builds('')}
        target = assignee or _account(bug.get('resolvedBy')) or _account(bug.get('assignedTo'))
        if target:
            body['assignedTo'] = target
        self._req('POST', f'bugs/{bug_id}/active', json=body)

    def bug_url(self, bug_id: str) -> str:
        return f'{self.base_url}/bug-view-{bug_id}.html' if bug_id else ''

    def get_options(self) -> dict:
        builds = [('trunk', '主干')]
        if self.extra.get('project_id'):
            data = self._req('GET', f'projects/{self.extra["project_id"]}/builds')
            builds += [(b['id'], b.get('name', b['id'])) for b in data.get('builds', [])]
        plans = []
        try:
            data = self._req('GET', f'products/{self.product}/plans')
            plans = [(p['id'], p.get('title', p['id'])) for p in data.get('plans', [])]
        except BugTrackerError:
            pass
        return {
            'version_report_list': self._options(builds),
            'version_fix_list': [],
            'release_id_list': self._options(plans),
        }

    def get_fields(self) -> List[dict]:
        return [
            {'key': 'type', 'label': 'Bug类型', 'options': self._options(BUG_TYPES)},
            {'key': 'os', 'label': '操作系统', 'options': []},
            {'key': 'browser', 'label': '浏览器', 'options': []},
            {'key': 'keywords', 'label': '关键词', 'options': []},
        ]

    def test_connection(self) -> str:
        self._token(refresh=True)
        product = self._req('GET', f'products/{self.product}')
        return f"连接成功, 产品: {product.get('name', self.product)}"
