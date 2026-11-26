"""内置通知器实现。

* :class:`ConsoleNotifier`——通过日志输出。
* :class:`WeComNotifier`——发送到企业微信群机器人 webhook。
* :class:`SlackNotifier`——发送到 Slack incoming webhook。
* :class:`EmailNotifier`——通过 SMTP 发送邮件。

所有网络 IO 都经由 :mod:`requests`（WeCom / Slack）或 :mod:`smtplib`（Email）。
每个通知器自行吸收异常并记告警，不会因为通知失败而中断流水线。
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Dict

from .base import Notifier

logger = logging.getLogger(__name__)


class ConsoleNotifier(Notifier):
    """通过标准 logger 输出通知的实现。"""

    notifier_name = "console"

    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:
        prefix = f"[{title}] " if title else ""
        mention_str = f" (@{', @'.join(mentioned)})" if mentioned else ""
        logger.info("%s%s%s", prefix, text, mention_str)


class WeComNotifier(Notifier):
    """企业微信群机器人通知器。

    webhook 地址通过
    :class:`~TiMi_HOK_Game_Translator.config.schema.NotificationConfig` 的 ``webhook`` 字段传入；
    该字段被视为敏感内容，在 ``config dump`` 输出时会脱敏。
    """

    notifier_name = "wecom"

    def __init__(self, *, webhook: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.webhook = webhook

    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:
        if not self.webhook:
            logger.warning("WeComNotifier has no webhook configured; message dropped.")
            return
        payload: Dict[str, Any] = {
            "msgtype": "text",
            "text": {
                "content": (f"[{title}] " if title else "") + text,
                "mentioned_list": list(mentioned),
            },
        }
        _post(self.webhook, payload, self.notifier_name)


class SlackNotifier(Notifier):
    """发送到 Slack incoming webhook 的通知器。"""

    notifier_name = "slack"

    def __init__(self, *, webhook: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.webhook = webhook

    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:
        if not self.webhook:
            logger.warning("SlackNotifier has no webhook configured; message dropped.")
            return
        payload: Dict[str, Any] = {
            "text": (f"*{title}*\n" if title else "") + text,
        }
        if mentioned:
            payload["text"] = " ".join(f"<@{m}>" for m in mentioned) + " " + payload["text"]
        _post(self.webhook, payload, self.notifier_name)


class EmailNotifier(Notifier):
    """SMTP 邮件通知器。

    需要的 ``extra`` 字段：

    * ``host``——SMTP 主机名（如 ``smtp.example.com``）。
    * ``port``——SMTP 端口号（整数）。
    * ``username`` / ``password``——SMTP 鉴权（开放中继可选）。
    * ``sender``——RFC 5322 发件人地址。
    * ``recipients``——逗号分隔的收件人列表。
    * ``tls``——bool，默认 True。
    """

    notifier_name = "email"

    def notify(self, text: str, *, title: str = "", mentioned: tuple = ()) -> None:
        host = str(self.extra.get("host", ""))
        port = int(self.extra.get("port", 25))
        sender = str(self.extra.get("sender", ""))
        recipients = self.extra.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        if not host or not sender or not recipients:
            logger.warning("EmailNotifier missing host/sender/recipients; message dropped.")
            return

        message = EmailMessage()
        message["Subject"] = title or "TiMi_HOK_Game_Translator notification"
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        body = text
        if mentioned:
            body = body + "\n\nMentions: " + ", ".join(mentioned)
        message.set_content(body)

        try:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if bool(self.extra.get("tls", True)):
                    smtp.starttls()
                username = self.extra.get("username")
                password = self.extra.get("password")
                if username and password:
                    smtp.login(str(username), str(password))
                smtp.send_message(message)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning("EmailNotifier failed to send: %s", exc)


def _post(webhook: str, payload: Dict[str, Any], notifier_name: str) -> None:
    """将 ``payload`` 以 JSON 形式 POST 到 ``webhook``，异常仅记日志不抛出。"""
    try:
        import requests  # 局部导入——测试环境可能未安装
    except ImportError:  # pragma: no cover
        logger.warning("%s notifier requires the 'requests' package.", notifier_name)
        return
    try:
        response = requests.post(webhook, json=payload, timeout=15)
        if response.status_code >= 400:
            logger.warning(
                "%s notifier got HTTP %s: %s",
                notifier_name,
                response.status_code,
                response.text[:200],
            )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 非致命
        logger.warning("%s notifier failed: %s", notifier_name, exc)


__all__ = ["ConsoleNotifier", "EmailNotifier", "SlackNotifier", "WeComNotifier"]
