"""
Bugzilla 5.x REST API 适配
文档: https://bugzilla.readthedocs.io/en/5.0/api/index.html

项目配置:
  base_url   Bugzilla 地址, 如 https://bugzilla.example.com
  api_key    用户偏好设置 > API Keys 中生成的 Key
  product    产品名称 (必填)
  component  组件名称 (必填)
  extra      可选 JSON:
     default_version   未选择 “发现版本” 时使用的版本, 默认 unspecified
     op_sys / platform 默认 All
     close_status      回归通过时的目标状态, 默认 RESOLVED
     close_resolution  默认 FIXED
     reopen_status     回归失败时的目标状态, 默认 CONFIRMED (Bugzilla 4.0+ 默认工作流)
     priority_map      {"1": "Highest", ...}  覆盖 LQA 优先级 -> Bugzilla 优先级映射
     severity_map      {"1": "critical", ...} 覆盖 LQA 严重程度 -> Bugzilla 严重程度映射
     assignee_field    email(默认, 使用LQA用户邮箱) / name (直接使用LQA用户名)
"""
import base64
import mimetypes
import os
from typing import Dict, List

from .base import BugTracker, BugTrackerError, BugPayload, TrackerBug, html_to_text

PRIORITY_MAP = {1: 'Highest', 2: 'High', 3: 'Normal', 4: 'Low', 5: 'Lowest'}
SEVERITY_MAP = {1: 'critical', 2: 'major', 3: 'normal', 4: 'minor', 5: 'enhancement'}

# 自定义提单字段中可选的标准字段
_STANDARD_FIELDS = ('priority', 'bug_severity', 'op_sys', 'rep_platform', 'keywords', 'version',
                    'target_milestone', 'component')


class BugzillaTracker(BugTracker):
    type = 'bugzilla'
    label = 'Bugzilla'

    def __init__(self, project_id, config=None):
        super().__init__(project_id, config)
        self.api_key = self.config.get('api_key', '')
        self.product = self.config.get('product', '')
        self.component = self.config.get('component', '')
        if not (self.base_url and self.api_key and self.product):
            raise BugTrackerError('Bugzilla 配置不完整：需要地址、API Key、产品')

    def _req(self, method, path, **kwargs):
        headers = kwargs.pop('headers', {})
        headers['X-BUGZILLA-API-KEY'] = self.api_key
        headers.setdefault('Accept', 'application/json')
        data = self._http(method, f'{self.base_url}/rest/{path.lstrip("/")}', headers=headers, **kwargs)
        if isinstance(data, dict) and data.get('error'):
            raise BugTrackerError(f'Bugzilla 错误 {data.get("code")}: {data.get("message")}')
        return data

    # ------------------------------------------------------------------ 账号
    def _account(self, name: str) -> str:
        if not name:
            return ''
        if self.extra.get('assignee_field', 'email') != 'email' or '@' in name:
            return name
        from apps.user.models import User
        email = User.objects.filter(name=name).values_list('email', flat=True).first()
        return email or name

    # ------------------------------------------------------------------ 接口
    def create_bug(self, payload: BugPayload, attachments: List[str]) -> str:
        body = {
            'product': self.product,
            'component': self.component,
            'summary': payload.title[:255],
            'version': payload.version_report or self.extra.get('default_version', 'unspecified'),
            'description': html_to_text(payload.description),
            'op_sys': self.extra.get('op_sys', 'All'),
            'platform': self.extra.get('platform', 'All'),
        }
        if payload.priority:
            body['priority'] = self._map_value('priority_map', payload.priority, PRIORITY_MAP)
        if payload.severity:
            body['severity'] = self._map_value('severity_map', payload.severity, SEVERITY_MAP)
        if payload.version_fix:
            body['target_milestone'] = payload.version_fix
        accounts = [self._account(n) for n in payload.assignees if n]
        if accounts:
            body['assigned_to'] = accounts[0]
            if len(accounts) > 1:
                body['cc'] = accounts[1:]
        for key, value in (payload.custom_fields or {}).items():
            body[key] = value

        data = self._req('POST', 'bug', json=body)
        bug_id = str(data.get('id', ''))
        if not bug_id:
            raise BugTrackerError(f'Bugzilla 未返回缺陷ID: {data}')
        for path in attachments:
            self._upload(bug_id, path, '还原截图')
        return bug_id

    def _upload(self, bug_id, abs_path, summary, comment=''):
        if not abs_path or not os.path.exists(abs_path):
            return
        with open(abs_path, 'rb') as fp:
            content = base64.b64encode(fp.read()).decode()
        body = {
            'ids': [int(bug_id)],
            'data': content,
            'file_name': os.path.basename(abs_path),
            'summary': summary,
            'content_type': mimetypes.guess_type(abs_path)[0] or 'image/png',
        }
        if comment:
            body['comment'] = comment
        self._req('POST', f'bug/{bug_id}/attachment', json=body)

    def get_bugs(self, bug_ids: List[str]) -> Dict[str, TrackerBug]:
        ids = [str(i) for i in bug_ids if i]
        if not ids:
            return {}
        fields = 'id,summary,status,resolution,is_open,assigned_to,creator,priority,severity'
        data = self._req('GET', 'bug', params={'id': ','.join(ids), 'include_fields': fields})
        ret = {}
        for bug in data.get('bugs', []):
            bid = str(bug['id'])
            status = bug.get('status', '')
            if bug.get('resolution'):
                status = f"{status}/{bug['resolution']}"
            ret[bid] = TrackerBug(
                id=bid, title=bug.get('summary', ''), status=status, is_open=bool(bug.get('is_open', True)),
                assignee=bug.get('assigned_to', ''), reporter=bug.get('creator', ''),
                priority=bug.get('priority', ''), severity=bug.get('severity', ''), url=self.bug_url(bid),
            )
        return ret

    def close_bug(self, bug_id: str, comment: str):
        self._req('PUT', f'bug/{bug_id}', json={
            'status': self.extra.get('close_status', 'RESOLVED'),
            'resolution': self.extra.get('close_resolution', 'FIXED'),
            'comment': {'body': comment},
        })

    def reopen_bug(self, bug_id: str, comment: str, attachments: List[str], assignee: str = ''):
        text = html_to_text(comment)
        bug = self.get_bugs([bug_id]).get(str(bug_id))
        if bug and bug.is_open and not bug.status.startswith('RESOLVED'):
            # 缺陷仍处于打开状态 (开发尚未处理), 只追加评论
            self._req('POST', f'bug/{bug_id}/comment', json={'comment': text})
        else:
            body = {'status': self.extra.get('reopen_status', 'CONFIRMED'), 'comment': {'body': text}}
            if assignee:
                body['assigned_to'] = self._account(assignee)
            self._req('PUT', f'bug/{bug_id}', json=body)
        for path in attachments:
            self._upload(bug_id, path, '回归截图')

    def bug_url(self, bug_id: str) -> str:
        return f'{self.base_url}/show_bug.cgi?id={bug_id}' if bug_id else ''

    def get_options(self) -> dict:
        data = self._req('GET', 'product', params={'names': self.product,
                                                   'include_fields': 'name,versions,milestones'})
        products = data.get('products', [])
        if not products:
            raise BugTrackerError(f'Bugzilla 中不存在产品: {self.product}')
        product = products[0]
        versions = [v['name'] for v in product.get('versions', []) if v.get('is_active', True)]
        milestones = [m['name'] for m in product.get('milestones', []) if m.get('is_active', True)]
        return {
            'version_report_list': self._options((v, v) for v in versions),
            'version_fix_list': self._options((m, m) for m in milestones),
            'release_id_list': [],
        }

    def get_fields(self) -> List[dict]:
        data = self._req('GET', 'field/bug')
        fields = []
        for f in data.get('fields', []):
            name = f.get('name', '')
            if not (f.get('is_custom') or name in _STANDARD_FIELDS):
                continue
            options = [{'value': v['name'], 'label': v['name']} for v in (f.get('values') or []) if v.get('name')]
            fields.append({'key': name, 'label': f.get('display_name') or name, 'options': options})
        return fields

    def test_connection(self) -> str:
        self.get_options()      # 校验 API Key 与产品
        try:
            who = self._req('GET', 'whoami')    # 部分 5.0.x 版本不支持, 失败不影响
            return f"连接成功, 当前账号: {who.get('name') or who.get('real_name') or '-'}"
        except BugTrackerError:
            return '连接成功'
