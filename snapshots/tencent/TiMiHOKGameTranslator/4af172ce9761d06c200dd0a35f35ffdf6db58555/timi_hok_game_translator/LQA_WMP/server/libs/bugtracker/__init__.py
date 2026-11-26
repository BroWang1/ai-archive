"""
缺陷系统适配层

用法:
    from libs import bugtracker
    tracker = bugtracker.get_tracker(project_id)
    external_id = tracker.create_bug(payload, [abs_img_path])
"""
from typing import Optional

from .base import BugTracker, BugTrackerError, BugPayload, TrackerBug, html_to_text

TRACKER_TYPES = (
    ('none', '平台内记录'),
    ('bugzilla', 'Bugzilla'),
    ('zentao', '禅道'),
)


def _tracker_class(tracker_type):
    if tracker_type == 'bugzilla':
        from .bugzilla import BugzillaTracker
        return BugzillaTracker
    if tracker_type == 'zentao':
        from .zentao import ZentaoTracker
        return ZentaoTracker
    from .local import LocalTracker
    return LocalTracker


def get_tracker(project_id: int, config: Optional[dict] = None) -> BugTracker:
    """
    获取项目当前配置的缺陷系统客户端
    :param project_id: 项目ID
    :param config: 不传则读取项目配置 ProjectConfigBugTracker (用于 “测试连接” 时传入未保存的配置)
    配置不完整时抛出 BugTrackerError
    """
    if config is None:
        from apps.project.service import ProjCfgService
        config = ProjCfgService.get_bug_tracker(project_id) or {}
    return _tracker_class(config.get('tracker_type') or 'none')(project_id, config)
