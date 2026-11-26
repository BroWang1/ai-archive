"""通知抽象层。

通知器是可插拔的消息推送渠道（WeCom / Slack / Email / Console）。
由于只是辅助能力，调用站都用 ``try/except`` 包裹，任一渠道失败不会阻断流水线。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class NotificationMessage:
    """传递给 :class:`Notifier` 的结构化消息。"""

    text: str
    title: str = ""
    mentioned: tuple = ()
    extra: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = {}


class Notifier(abc.ABC):
    """所有通知渠道的基类。"""

    notifier_name: str = ""

    def __init__(self, *, extra: Optional[Dict[str, Any]] = None) -> None:
        self.extra: Dict[str, Any] = dict(extra or {})

    @abc.abstractmethod
    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:
        """发送一条通知；实现时建议不因瞬时错误抛异常。"""


__all__ = ["NotificationMessage", "Notifier"]
