"""不对接外部系统: 缺陷只记录在 LQA 平台内 (lqa_bug 表)"""
from typing import Dict, List

from libs.util import datetime_ms
from .base import BugTracker, BugPayload, TrackerBug

STATUS_OPEN = 'open'
STATUS_CLOSED = 'closed'


class LocalTracker(BugTracker):
    type = 'none'
    label = '平台内记录'
    remote = False

    @staticmethod
    def _model():
        from apps.bug.models import Bug
        return Bug

    def _append_comment(self, bug_id, text, status=None):
        Bug = self._model()
        bug = Bug.objects.filter(pk=int(bug_id)).first()
        if not bug:
            return
        comments = list(bug.comments or [])
        comments.append({'at': datetime_ms().strftime('%Y-%m-%d %H:%M:%S'), 'text': text})
        mapping = {'comments': comments}
        if status:
            mapping['status'] = status
        Bug.update_db(bug.id, mapping)

    def create_bug(self, payload: BugPayload, attachments: List[str]) -> str:
        return str(payload.lqa_bug_id)

    def get_bugs(self, bug_ids: List[str]) -> Dict[str, TrackerBug]:
        Bug = self._model()
        pks = [int(i) for i in bug_ids if str(i).isdigit()]
        ret = {}
        for row in Bug.objects.filter(pk__in=pks).values('id', 'title', 'status', 'current_owner', 'reporter'):
            ret[str(row['id'])] = TrackerBug(
                id=str(row['id']), title=row['title'], status=row['status'],
                is_open=row['status'] != STATUS_CLOSED, assignee=row['current_owner'], reporter=row['reporter'],
            )
        return ret

    def close_bug(self, bug_id: str, comment: str):
        self._append_comment(bug_id, comment, STATUS_CLOSED)

    def reopen_bug(self, bug_id: str, comment: str, attachments: List[str], assignee: str = ''):
        self._append_comment(bug_id, comment, STATUS_OPEN)
