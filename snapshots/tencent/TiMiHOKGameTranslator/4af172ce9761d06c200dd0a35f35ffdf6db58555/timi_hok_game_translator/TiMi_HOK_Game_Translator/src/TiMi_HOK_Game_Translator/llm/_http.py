"""LLM provider 共享的 HTTP 工具。

目的：
    - 使用 ``requests.Session`` 复用 TCP/TLS 连接，大幅降低每次调用的开销
      （尤其对 HTTPS 翻译 API，减少 ~100ms 的 TLS 握手时间）；
    - 统一的 JSON POST 封装，所有 provider 共享超时/重试友好的行为；
    - 不新增外部依赖——``requests`` 已是框架硬依赖。
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional  # pylint: disable=unused-import

import requests
from requests.adapters import HTTPAdapter

_SESSION_LOCK = threading.Lock()
_SESSIONS: Dict[str, requests.Session] = {}


def get_session(pool_key: str, *, pool_maxsize: int = 32) -> requests.Session:
    """按 ``pool_key`` 获取一个共享 ``requests.Session``。

    同一个 key 全局复用一个连接池；每个 provider 实例应传入稳定的 key
    （例如 ``f"{provider_name}:{api_base}"``）以共享连接。

    参数：
        pool_key: 连接池命名空间。
        pool_maxsize: HTTPAdapter 的 ``pool_maxsize``；并发线程多时适当调大。
    返回：
        懒加载的 ``requests.Session``；线程安全。
    """
    sess = _SESSIONS.get(pool_key)
    if sess is not None:
        return sess
    with _SESSION_LOCK:
        sess = _SESSIONS.get(pool_key)
        if sess is None:
            sess = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=pool_maxsize,
                pool_maxsize=pool_maxsize,
                # 内置重试交给上层，这里只给网络层连接复用
                max_retries=0,
            )
            sess.mount("http://", adapter)
            sess.mount("https://", adapter)
            _SESSIONS[pool_key] = sess
    return sess


def post_json(
    *,
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
) -> Any:
    """POST JSON 并解析响应。

    参数：
        session: ``get_session`` 返回的共享 session。
        url: 完整 URL。
        payload: 请求体，会被 ``json.dumps(ensure_ascii=False)`` 序列化。
        headers: 请求头（会自动补 ``Content-Type``）。
        timeout: 请求总超时秒数。
    返回：
        解析后的 JSON（dict / list / 原始字符串，视服务端响应而定）。
    异常：
        ``requests.HTTPError``——HTTP 状态码非 2xx 时抛出，附带响应文本。
    """
    merged_headers = dict(headers)
    merged_headers.setdefault("Content-Type", "application/json")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = session.post(url, data=body, headers=merged_headers, timeout=timeout)
    if resp.status_code >= 400:
        # 把响应内容带进异常，方便上层 debug
        raise requests.HTTPError(
            f"HTTP {resp.status_code} from {url}: {resp.text[:500]}",
            response=resp,
        )
    try:
        return resp.json()
    except ValueError:
        return resp.text


def reset_sessions() -> None:
    """关闭并清理全部缓存 session；主要供测试使用。"""
    with _SESSION_LOCK:
        for sess in _SESSIONS.values():
            try:
                sess.close()
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                pass
        _SESSIONS.clear()


__all__ = ["get_session", "post_json", "reset_sessions"]
