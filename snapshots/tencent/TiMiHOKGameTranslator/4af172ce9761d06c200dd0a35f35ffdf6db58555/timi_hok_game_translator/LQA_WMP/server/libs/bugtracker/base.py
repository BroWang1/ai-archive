"""
缺陷系统适配层: 抽象接口

每个项目在 “项目设置 > 基础配置 > 缺陷系统” 中选择一种缺陷系统:
  - none      仅在平台内记录 (不对接外部系统)
  - bugzilla  Bugzilla 5.x REST API
  - zentao    禅道开源版 RESTful API v1
"""
import html
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import requests

logger = logging.getLogger('bugtracker')


class BugTrackerError(Exception):
    """调用外部缺陷系统失败"""


@dataclass
class TrackerBug:
    """统一的缺陷信息结构"""
    id: str
    title: str = ''
    status: str = ''
    is_open: bool = True
    assignee: str = ''
    resolver: str = ''
    reporter: str = ''
    priority: str = ''
    severity: str = ''
    url: str = ''
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class BugPayload:
    """提交缺陷时的统一参数 (与具体缺陷系统无关)"""
    lqa_bug_id: int
    title: str
    description: str                 # HTML
    priority: int = 0                # libs.defs.BugPriorityEnum
    severity: int = 0                # libs.defs.BugSeverityEnum
    version_report: str = ''         # 发现版本
    version_fix: str = ''            # 修复版本/里程碑
    release_id: str = ''             # 发布计划
    assignees: List[str] = field(default_factory=list)   # LQA 用户名
    reporter: str = ''
    custom_fields: Dict[str, str] = field(default_factory=dict)


def html_to_text(content: str) -> str:
    """把提单描述 (HTML) 转换为纯文本, 供不支持富文本的缺陷系统使用"""
    if not content:
        return ''
    text = re.sub(r'(?i)<br\s*/?>', '\n', content)
    text = re.sub(r'(?i)</(p|div|li|tr|h\d)>', '\n', text)
    text = re.sub(r'(?i)<img[^>]*src=["\']([^"\']+)["\'][^>]*>', r'[\1]', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class BugTracker(ABC):
    type: str = ''
    label: str = ''
    #: 是否对接外部系统 (none 为 False)
    remote: bool = True

    def __init__(self, project_id: int, config: Optional[dict] = None):
        self.project_id = project_id
        self.config = config or {}
        self.extra = self.config.get('extra') or {}
        self.base_url = (self.config.get('base_url') or '').rstrip('/')
        self.timeout = int(self.extra.get('timeout', 20))

    # ---------------------------------------------------------------- HTTP
    def _http(self, method, url, expect_json=True, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.Timeout as err:
            raise BugTrackerError(f'{self.label} 请求超时 (>{self.timeout}s): 请检查「系统地址」是否可达, 或在高级配置中调大 timeout') from err
        except requests.ConnectionError as err:
            raise BugTrackerError(f'{self.label} 无法连接到服务器: 请检查「系统地址」是否正确、网络是否通畅 ({err.__class__.__name__})') from err
        except requests.RequestException as err:
            raise BugTrackerError(f'{self.label} 请求失败: {err}') from err
        if resp.status_code >= 400:
            raise BugTrackerError(self._format_http_error(resp))
        if not expect_json:
            return resp
        try:
            return resp.json()
        except ValueError as err:
            raise BugTrackerError(self._format_non_json_error(resp)) from err

    # 返回了 HTML / 纯文本等非 JSON 内容时, 给出更友好的说明
    def _format_non_json_error(self, resp):
        content_type = (resp.headers.get('Content-Type') or '').lower()
        body = (resp.text or '').strip()
        snippet = body[:120].replace('\n', ' ').replace('\r', ' ')
        looks_like_html = 'html' in content_type or body[:15].lower().lstrip().startswith(('<!doctype', '<html'))
        if looks_like_html:
            return (f'{self.label} 服务地址返回了网页 (HTML) 而非 API 响应, 通常意味着地址填错了, 请检查:\n'
                    f'1) 「系统地址」应填服务根地址 (如 http://zentao.example.com), 不要带页面路径、查询参数(?xxx=)或 #锚点\n'
                    f'2) 该地址指向的确实是 {self.label} 服务, 而不是其他系统 (如 TAPD、Jira 等)\n'
                    f'3) 服务未被反向代理拦截到登录页')
        # 非 HTML 的异常响应
        if not body:
            return f'{self.label} 返回了空响应 (Content-Type: {content_type or "未知"}), 请检查服务是否正常'
        return f'{self.label} 返回非 JSON 内容 (Content-Type: {content_type or "未知"}): {snippet}'

    # HTTP 状态码 >=400 的错误: 按常见状态给出中文说明
    def _format_http_error(self, resp):
        status = resp.status_code
        body = (resp.text or '').strip()
        content_type = (resp.headers.get('Content-Type') or '').lower()
        # 尝试从 JSON 响应里提取错误信息; 非 JSON 时截取前 200 字符
        detail = ''
        if 'json' in content_type:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    detail = str(data.get('message') or data.get('error') or data.get('msg') or '').strip()
                if not detail:
                    detail = body[:200]
            except ValueError:
                detail = body[:200]
        else:
            detail = body[:200].replace('\n', ' ').replace('\r', ' ')
        status_hint = {
            400: '请求参数有误',
            401: '认证失败 (账号/密码或 API Key 不正确)',
            403: '权限不足 (当前账号无该操作权限)',
            404: '资源不存在 (请检查「产品ID」「组件」或「系统地址」是否正确)',
            405: '方法不允许 (接口路径可能错误)',
            500: '对方服务内部错误',
            502: '对方服务网关错误',
            503: '对方服务不可用',
            504: '对方服务网关超时',
        }.get(status, '')
        prefix = f'{self.label} HTTP {status}'
        if status_hint:
            prefix = f'{prefix}（{status_hint}）'
        return f'{prefix}: {detail}' if detail else prefix

    # ---------------------------------------------------------------- 接口
    @abstractmethod
    def create_bug(self, payload: BugPayload, attachments: List[str]) -> str:
        """创建缺陷, 返回外部缺陷ID; attachments 为截图绝对路径"""

    @abstractmethod
    def get_bugs(self, bug_ids: List[str]) -> Dict[str, TrackerBug]:
        """批量查询缺陷, 返回 {外部ID: TrackerBug}, 不存在的ID不返回"""

    @abstractmethod
    def close_bug(self, bug_id: str, comment: str):
        """回归通过: 关闭缺陷"""

    @abstractmethod
    def reopen_bug(self, bug_id: str, comment: str, attachments: List[str], assignee: str = ''):
        """回归不通过: 重新打开缺陷并附上新截图"""

    def bug_url(self, bug_id: str) -> str:
        return ''

    def get_options(self) -> dict:
        """提单下拉选项 (发现版本/修复版本/发布计划)"""
        return {'version_report_list': [], 'version_fix_list': [], 'release_id_list': []}

    def get_fields(self) -> List[dict]:
        """可配置为 “自定义提单字段” 的外部字段 [{key, label, options:[{value,label}]}]"""
        return []

    def test_connection(self) -> str:
        """连通性测试, 成功返回说明文字, 失败抛 BugTrackerError"""
        return 'ok'

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def _options(items):
        return [{'value': str(v), 'label': str(l)} for v, l in items]

    def _map_value(self, key, value, default_map):
        """优先使用项目配置 extra.{key} 中的映射"""
        mapping = {**default_map, **{int(k): v for k, v in (self.extra.get(key) or {}).items()}}
        return mapping.get(int(value or 0))
