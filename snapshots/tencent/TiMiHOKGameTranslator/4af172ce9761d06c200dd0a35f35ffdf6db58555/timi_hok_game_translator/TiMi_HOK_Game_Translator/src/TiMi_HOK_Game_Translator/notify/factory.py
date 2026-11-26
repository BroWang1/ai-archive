"""通知器的工厂与注册表。"""

from __future__ import annotations

from typing import Any, Dict, Type

from ..commons import NotifierType
from ..config.schema import NotificationConfig
from .base import Notifier
from .notifiers import ConsoleNotifier, EmailNotifier, SlackNotifier, WeComNotifier


class _NullNotifier(Notifier):
    """静默丢弃全部消息的 :class:`Notifier`。"""

    notifier_name = "none"

    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:  # noqa: D401
        return None


_REGISTRY: Dict[str, Type[Notifier]] = {
    NotifierType.NONE.value: _NullNotifier,
    NotifierType.CONSOLE.value: ConsoleNotifier,
    NotifierType.WECOM.value: WeComNotifier,
    NotifierType.SLACK.value: SlackNotifier,
    NotifierType.EMAIL.value: EmailNotifier,
}


def register_notifier(name: str, notifier_cls: Type[Notifier]) -> None:
    """以 ``name`` 为名注册自定义 :class:`Notifier`。"""
    _REGISTRY[name.lower()] = notifier_cls


def registered_notifiers() -> list:
    """返回当前已注册的通知器名称列表（排序后）。"""
    return sorted(_REGISTRY)


def create_notifier(notification_config: NotificationConfig) -> Notifier:
    """根据 ``notification_config`` 构造具体 :class:`Notifier` 实例。"""
    key = (notification_config.type or "").lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown notification.type '{notification_config.type}'. "
            f"Registered notifiers: {registered_notifiers()}"
        )
    cls = _REGISTRY[key]
    extra: Dict[str, Any] = dict(notification_config.extra or {})

    # 将顶层 webhook 字段合入 ``extra``，使需要 webhook 的渠道（WeCom / Slack）
    # 能一致地拿到它。
    kwargs: Dict[str, Any] = {"extra": extra}
    if key in {NotifierType.WECOM.value, NotifierType.SLACK.value}:
        kwargs["webhook"] = notification_config.webhook

    return cls(**kwargs)


__all__ = ["create_notifier", "register_notifier", "registered_notifiers"]
