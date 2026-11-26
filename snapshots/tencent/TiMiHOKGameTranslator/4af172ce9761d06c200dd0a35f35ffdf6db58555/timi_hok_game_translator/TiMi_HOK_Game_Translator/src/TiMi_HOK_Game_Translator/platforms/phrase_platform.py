"""Phrase TMS（旧名 Memsource）翻译平台适配器。

基于 **Phrase TMS REST API**（旧称 "Memsource API v1/v2"）实现
:class:`~TiMi_HOK_Game_Translator.platforms.TranslationPlatform` 契约。

参考文档：

* Overview — https://developers.phrase.com/en/api/overview
* TMS 参考 — https://developers.phrase.com/en/api/tms/latest/introduction
* Platform IDM 令牌交换 —
  https://developers.phrase.com/en/api/platform/authentication

鉴权方式
--------
支持三种方式，优先级从高到低：

1. **Subject Token Exchange**（⭐ 推荐，官方 2024+ 新流程）——
   在 ``extra["subject_token"]`` 传入从 Phrase UI *Settings → API tokens → Generate token*
   屏复制的 token。适配器会通过
   ``POST https://<region>.phrase.com/idm/oauth/token``（grant type
   ``urn:ietf:params:oauth:grant-type:token-exchange``）将它交换为短时 Bearer，
   缓存在内存中，并在过期前约 60 秒自动刷新。后续请求会携带
   ``Authorization: Bearer <access_token>``。
2. **旧式 ApiToken**——直接传入 ``api_token``。适配器发送
   ``Authorization: ApiToken <token>``，用于兼容早期 Phrase / Memsource 部署。
3. **用户名 + 密码**——在 ``extra["username"]`` / ``extra["password"]`` 传入，
   首次需鉴权时适配器自动调用
   ``POST /web/api2/v3/auth/login``（旧租户回退 ``/v1/auth/login``）获取
   24 小时 ApiToken。适用于禁用 SSO / 不能新建 API token 的情景。

使用的接口
------------
==============================================  ==================================================================
用途                                            接口（相对于 ``api_base``）
==============================================  ==================================================================
IDM 令牌交换（方式 1）                            ``POST <idm_base>/idm/oauth/token``
登录（方式 3，首选）                             ``POST /web/api2/v3/auth/login``
登录（方式 3，回退）                             ``POST /web/api2/v1/auth/login``
当前身份                                            ``GET  /web/api2/v1/auth/whoAmI``
获取项目                                            ``GET  /web/api2/v1/projects/{projectUid}``
上传 Job（源文件）                                ``POST /web/api2/v1/projects/{projectUid}/jobs``
获取 Job                                        ``GET  /web/api2/v1/projects/{projectUid}/jobs/{jobUid}``
下载双语/目标文件                                 ``GET  /web/api2/v1/projects/{projectUid}/jobs/{jobUid}/targetFile``
修改 Job 状态                                    ``POST /web/api2/v1/projects/{projectUid}/jobs/setStatus``
==============================================  ==================================================================

敏感字段
--------
适配器不会将 ``api_token`` / ``password`` 写入日志。当外层
:class:`~TiMi_HOK_Game_Translator.config.Config` 通过
:meth:`~TiMi_HOK_Game_Translator.config.Config.to_dict` 导出时，这些字段会被
通用敏感字段逻辑脱敏（参见
:data:`TiMi_HOK_Game_Translator.commons.SENSITIVE_FIELD_MARKERS`）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any, Callable, Dict, Optional, Sequence

from ..commons import (
    DEFAULT_HTTP_RETRIES,
    DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    PlatformError,
    ReviewStage,
)
from .base import (
    SplitResult,
    TaskInfo,
    TaskStatus,
    TranslationPlatform,
    UploadResult,
)
from .factory import register_platform

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://cloud.memsource.com/web/api2"

# --- Phrase Platform IDM（Token Exchange） -------------------------------------
# 参考：https://developers.phrase.com/en/api/platform/authentication
_TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
# 在 ``exp`` 前提前多少秒刷新——小预量，避免请求到达服务器时令牌刚好过期。
_TOKEN_EXPIRY_SKEW_SECONDS = 60.0

# Region → (IDM base, TMS API base)：IDM 位于 ``<region>.phrase.com``，而 TMS REST API
# 仍使用 ``cloud.memsource.com``（EU/US 共用，区域由 Bearer 的 ``aud`` / tenant claim 控制）。
_REGION_BASES: Dict[str, Dict[str, str]] = {
    "eu": {
        "idm": "https://eu.phrase.com",
        "api": "https://cloud.memsource.com/web/api2",
    },
    "us": {
        "idm": "https://us.phrase.com",
        "api": "https://cloud.memsource.com/web/api2",
    },
}

# ---------------------------------------------------------------------------
# Phrase ↔ 框架的映射辅助
# ---------------------------------------------------------------------------
# Phrase Job 工作流级别状态（参考 TMS OpenAPI 中的 JobPartStatusDto）。
_STATUS_MAP: Dict[str, TaskStatus] = {
    "NEW": TaskStatus.PENDING,
    "EMAILED": TaskStatus.PENDING,
    "ASSIGNED": TaskStatus.IN_PROGRESS,
    "DECLINED_BY_LINGUIST": TaskStatus.REJECTED,
    "COMPLETED_BY_LINGUIST": TaskStatus.IN_PROGRESS,
    "COMPLETED": TaskStatus.APPROVED,
    "ACCEPTED_BY_LINGUIST": TaskStatus.IN_PROGRESS,
    "CANCELLED": TaskStatus.REJECTED,
    "REJECTED": TaskStatus.REJECTED,
    "DELIVERED": TaskStatus.APPROVED,
}


def _map_status(remote: str) -> TaskStatus:
    """将 Phrase 状态字符串映射为 :class:`TaskStatus`。"""
    if not remote:
        return TaskStatus.UNKNOWN
    return _STATUS_MAP.get(remote.upper(), TaskStatus.UNKNOWN)

def _extract_percent(data: Dict[str, Any]) -> float:  # noqa: E302
    """从 Phrase job 响应里提取"完成百分比"，兼容多种响应形态。

    已知形态：
    * **新版 TMS**：顶层 ``workflowLevel`` 直接是 int（如 ``1``），
      ``providers`` / ``status`` 另行表达进度；百分比字段不存在。
    * **旧版 TMS / 某些 workflow 项目**：``workflowLevel`` 为 dict，
      内含 ``percentageCompleted`` 浮点字段。
    * **若干 fallback 顶层字段**：``percentageCompleted`` /
      ``progressPercentage``——存在时直接读。

    任何解析失败都返回 ``0.0``，让轮询器据此继续等。
    """
    # 顶层直接给百分比的 fallback
    for key in ("percentageCompleted", "progressPercentage"):
        val = data.get(key)
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    # workflowLevel 旧结构 { "percentageCompleted": X }
    workflow_level = data.get("workflowLevel")
    if isinstance(workflow_level, dict):
        val = workflow_level.get("percentageCompleted")
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# 适配器主体
# ---------------------------------------------------------------------------
class PhrasePlatform(TranslationPlatform):
    """Phrase TMS 适配器——支持 一审/二审/轻度审校 三个阶段。

    构造参数（均为关键字参数）：

    * ``api_base``——Phrase TMS API 基地址。默认为
      ``https://cloud.memsource.com/web/api2``（EU / US 两个租户共用，
      区域由令牌本身控制，而非 DNS）；区域化/私部部署需改写。
    * ``api_token``——旧式长效 API token，提供时直接发送
      ``Authorization: ApiToken <token>``。
    * ``project_id``——Phrase 项目 UID。
    * ``extra``——自由字段，已识别的 key：

      * ``subject_token``——从 Phrase UI 复制的 API token（*Settings →
        API tokens → Generate token*）。提供后适配器会自动向
        ``<idm_base>/idm/oauth/token`` 交换为短时 Bearer，并在
        过期前自动刷新。
      * ``region``——``"eu"``（默认）或 ``"us"``；当仅提供
        ``subject_token`` 时，用于选择 IDM 主机。显式传入 ``idm_base`` 时忽略。
      * ``idm_base``——覆盖 IDM 主机（如 ``"https://eu.phrase.com"``），
        仅令牌交换时需要。
      * ``username`` / ``password``——旧式流程回退凭据；上述两者均未提供时，
        将通过 ``/auth/login`` 获取 24 小时 ApiToken。
      * ``user_uid``——同一用户名属于多个 TMS company 时必填，
        它会作为 ``userUid`` 发到登录接口。
      * ``workflow_step_uid``——将新建 Job 固定到某个工作流步。
      * ``timeout_seconds`` / ``retries`` / ``retry_interval_seconds``——
        HTTP 可调参数（默认值见 :mod:`TiMi_HOK_Game_Translator.commons.constants`）。
      * ``session_factory``——高级选项，可传入一个返回预配好的
        ``requests.Session`` 的工厂，供测试避免全局 patch ``requests``。
      * ``clock``——高级选项，可传入无参返回 UNIX 时间戳的可调用对象，
        供测试确定性地推进时间。

    本适配器线程安全：:attr:`_token_lock` 将令牌刷新串行化，但在令牌已缓存后
    允许并发发起 HTTP 请求。
    """

    platform_name = "phrase"
    supports_stages = (
        ReviewStage.FIRST.value,
        ReviewStage.SECOND.value,
        ReviewStage.LIGHT.value,
    )

    def __init__(
        self,
        *,
        api_base: str = "",
        api_token: str = "",
        project_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_extra = dict(extra or {})

        # --- 区域与基地址选择 -------------------------------------
        # 区域默认 ``eu``（Phrase 官方入口现在默认新建于 EU）；US 租户需显式传入
        # ``extra["region"] = "us"``。
        region = str(merged_extra.get("region", "eu") or "eu").lower()
        if region not in _REGION_BASES:
            raise PlatformError(
                f"PhrasePlatform: unknown region {region!r} — expected 'eu' or 'us'."
            )
        region_bases = _REGION_BASES[region]

        super().__init__(
            api_base=api_base or region_bases["api"],
            api_token=api_token,
            project_id=project_id,
            extra=merged_extra,
        )
        self.api_base = self.api_base.rstrip("/")

        self._region: str = region
        self._idm_base: str = str(
            merged_extra.get("idm_base") or region_bases["idm"]
        ).rstrip("/")

        # 令牌交换模式（模块 docstring 中的方式 1）。
        self._subject_token: str = str(merged_extra.get("subject_token", "") or "")
        # 当前 Bearer 失效的 UNIX 时间戳；0.0 代表“尚未缓存”。
        self._bearer_expires_at: float = 0.0

        # 旧式用户名密码模式（模式 3）。
        self._username: str = str(merged_extra.get("username", ""))
        self._password: str = str(merged_extra.get("password", ""))
        self._workflow_step_uid: str = str(merged_extra.get("workflow_step_uid", ""))

        # 目标语种 locale——Phrase 上传 job 时 Memsource 头的 ``targetLangs``
        # 必须非空，否则服务器直接 404（Spring 兜底，连 Phrase 应用层都进不去）。
        # 工厂 ``build_review_tool`` 当前未把 ``ReviewConfig.target_language_id``
        # 透传成实例属性，因此在构造时从 extra 兜底读取，优先级：
        #   1. extra["target_language_id"]（ReviewConfig 的字段名；见 schema.py）
        #   2. extra["target_locale"]（通用别名）
        #   3. 空串——留给调用方后续通过 ``instance.target_locale = ...`` 覆盖
        self._target_locale: str = str(
            merged_extra.get("target_language_id")
            or merged_extra.get("target_locale")
            or ""
        )

        # 【方案 🅒】Phrase 的默认 XLSX import 解析器不认识本项目固定的 5 列
        # 格式（Key/Source/Target/Context/Comment），导致 wordsCount=0, segments=[]，UI 显示
        # “The job has no segments”。解决方案：**首次 upload 前延迟创建**一个
        # multilingual_xls 类型的 ImportSettings，并在 upload 的 Memsource 头里通过
        # ``importSettings.uid`` 引用它。
        # * 缓存到实例字段 → 单次 PhrasePlatform 实例生命周期内只建一次，后续
        #   upload 按 uid 复用；不做跨 run 持久化（ImportSettings 对象在 Phrase 侧
        #   是全组织级别的，没理由污染它，每次 run 重建最干净）。
        # * 设为 ``None`` 表示未尝试创建；设为空串 ``""`` 表示尝试过但失败
        #   （此时 upload 降级为不带 importSettings，走 Phrase 默认解析——虽然解析不
        #   出 segments，但至少不让整个流水线崩）。
        self._import_settings_uid: Optional[str] = None

        # —— 诊断日志（排障用，默认 DEBUG 级别；流水线稳定后仅在 ``logging.level=DEBUG``
        # 时打印）：构造时拿到的凭据/配置状态。
        logger.debug(
            "[PhraseDBG-INIT] project_id=%r api_base=%r api_token_len=%d "
            "subject_token_len=%d region=%r target_locale=%r "
            "extra_keys=%s",
            project_id, self.api_base, len(self.api_token or ""),
            len(self._subject_token or ""), self._region,
            self._target_locale, sorted(list(merged_extra.keys())),
        )

        self._timeout: float = float(
            merged_extra.get("timeout_seconds", DEFAULT_HTTP_TIMEOUT_SECONDS)
        )
        self._retries: int = int(merged_extra.get("retries", DEFAULT_HTTP_RETRIES))
        self._retry_interval: float = float(
            merged_extra.get(
                "retry_interval_seconds", DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
            )
        )

        session_factory: Optional[Callable[[], Any]] = merged_extra.get(
            "session_factory"
        )
        self._session_factory: Optional[Callable[[], Any]] = (
            session_factory if callable(session_factory) else None
        )
        clock: Optional[Callable[[], float]] = merged_extra.get("clock")
        self._clock: Callable[[], float] = clock if callable(clock) else _now

        self._token_lock = threading.RLock()
        # 本地缓存：创建过的 job 信息，供 :meth:`download_translations` 直接
        # 从 file_id 将 jobUid 解出来，无需额外请求。
        self._jobs: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # HTTP 工作基础
    # ------------------------------------------------------------------
    def _session(self):
        """返回一个全新或用户自定义的 ``requests.Session``。

        避免全局导入 ``requests``，保证在无 HTTP 库环境下也能引用本模块。
        """
        if self._session_factory is not None:
            return self._session_factory()
        try:
            import requests  # noqa: WPS433 — 故意局部导入
        except ImportError as exc:  # pragma: no cover — 安装时已硬依赖
            raise PlatformError(
                "PhrasePlatform requires 'requests'. Install with "
                "`pip install requests`."
            ) from exc
        return requests.Session()

    def _authenticate(self, session) -> None:
        """保证 :attr:`api_token` 已填充且未过期。

        根据提供的凭据选择不同模式：

        1. **Subject Token Exchange**——存在 ``extra["subject_token"]`` 时，
           通过 ``<idm_base>/idm/oauth/token`` 交换为 Bearer，
           缓存至过期前约 60 秒。
        2. **静态 ApiToken**——已提供 ``api_token`` 且无子 token 时直接使用。
        3. **用户名 + 密码**——均未提供时回退到 ``/auth/login`` 拿 24 小时 ApiToken。
        """
        with self._token_lock:
            # 模式 1：使用 subject_token 交换令牌，并在过期前自动刷新。
            if self._subject_token:
                now = self._clock()
                if (
                    self.api_token
                    and self._bearer_expires_at
                    and now < self._bearer_expires_at - _TOKEN_EXPIRY_SKEW_SECONDS
                ):
                    return
                self._exchange_subject_token(session)
                return

            # 模式 2：调用方预先提供了静态 ApiToken。
            if self.api_token:
                return

            # 模式 3：用户名 + 密码 → 24 小时 ApiToken。
            if not (self._username and self._password):
                raise PlatformError(
                    "PhrasePlatform: no credentials configured. Set one of "
                    "extra.subject_token / api_token / (extra.username + "
                    "extra.password)."
                )
            self._login_with_password(session)

    def _exchange_subject_token(self, session) -> None:
        """将 ``subject_token`` 交换为 Bearer access token。

        采用 RFC 8693 OAuth 2.0 Token Exchange，请求 Phrase Platform IDM。
        必须在 :attr:`_token_lock` 保护下调用。
        """
        url = f"{self._idm_base}/idm/oauth/token"
        try:
            response = session.post(
                url,
                data={
                    "grant_type": _TOKEN_EXCHANGE_GRANT_TYPE,
                    "subject_token": self._subject_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001 — 传输层失败
            raise PlatformError(
                f"PhrasePlatform: IDM token exchange transport error: {exc}"
            ) from exc
        self._raise_for_status(response, "idm/oauth/token")

        data = response.json()
        access_token = data.get("access_token") or ""
        if not access_token:
            raise PlatformError(
                "PhrasePlatform: IDM response missing 'access_token'."
            )
        expires_in = float(data.get("expires_in", 0.0) or 0.0)
        # ``expires_in`` 一般总存在，但若服务器未返回则回退 3600，以保证仍会刷新。
        if expires_in <= 0.0:
            expires_in = 3600.0
        self.api_token = access_token
        self._bearer_expires_at = self._clock() + expires_in
        logger.info(
            "PhrasePlatform: exchanged subject token for Bearer via %s "
            "(expires in %.0fs)",
            url, expires_in,
        )

    def _login_with_password(self, session) -> None:
        """将用户名 + 密码换取 24 小时 ApiToken。

        遵循官方推荐的新接口 ``POST /web/api2/v3/auth/login``，
        未迁移的旧租户回退到 ``/v1/auth/login``。必须在 :attr:`_token_lock` 下调用。

        当同一用户名属于多个 TMS company 时需传 ``extra["user_uid"]``，
        它会作为 ``userUid`` 提交。
        """
        payload: Dict[str, Any] = {
            "userName": self._username,
            "password": self._password,
        }
        user_uid = str(self.extra.get("user_uid", "") or "")
        if user_uid:
            payload["userUid"] = user_uid

        last_error: Optional[Exception] = None
        for path in ("/v3/auth/login", "/v1/auth/login"):
            try:
                response = session.post(
                    f"{self.api_base}{path}",
                    json=payload,
                    timeout=self._timeout,
                )
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 传输层失败
                last_error = exc
                continue
            if response.status_code == 404:
                # 当前租户未提供该接口，尝试下一个。
                last_error = PlatformError(
                    f"PhrasePlatform: {path} returned 404 "
                    "(tenant does not expose it)."
                )
                continue
            self._raise_for_status(response, path)
            data = response.json()
            token = data.get("token") or ""
            if not token:
                raise PlatformError(
                    f"PhrasePlatform: {path} response missing 'token'."
                )
            self.api_token = token
            # Phrase 保证本模式下令牌有15天/24小时有效期。
            self._bearer_expires_at = 0.0
            logger.info(
                "PhrasePlatform: acquired 24-hour ApiToken via %s", path,
            )
            return

        # 两个接口都失败。
        if last_error is not None:
            raise PlatformError(
                f"PhrasePlatform: auth/login failed on all endpoints: "
                f"{last_error}"
            ) from last_error
        raise PlatformError(
            "PhrasePlatform: auth/login failed on all endpoints."
        )

    def _headers(self) -> Dict[str, str]:
        """构造当前模式对应的 ``Authorization`` 头。

        * Subject-Token-Exchange 模式 → ``Bearer <access_token>``
        * ApiToken / 密码模式     → ``ApiToken <token>``
        """
        scheme = "Bearer" if self._subject_token else "ApiToken"
        return {
            "Authorization": f"{scheme} {self.api_token}",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        files: Optional[Any] = None,
        data: Optional[Any] = None,
        stream: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        """发送带鉴权的 HTTP 请求，按需重试。"""
        session = self._session()
        self._authenticate(session)

        url = f"{self.api_base}{path}"
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)

        # requests 会将超时/连接重置抛为异常；重试在本处包裹。
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self._retries + 1):
            try:
                # —— 诊断日志（排障用，默认 DEBUG）：请求全貌 ——
                _safe_headers = {
                    k: (v if k not in ("Authorization",) else f"<{v.split(' ', 1)[0]} ...masked>")
                    for k, v in headers.items()
                }
                _body_hint = (
                    f"data_bytes={len(data) if isinstance(data, (bytes, bytearray)) else type(data).__name__}"
                    if data is not None else
                    f"files={list(files.keys()) if isinstance(files, dict) else files}" if files is not None else
                    f"json_keys={list(json_body.keys()) if isinstance(json_body, dict) else json_body}"
                )
                logger.debug(
                    "[PhraseDBG] %s %s | headers=%s | %s | params=%s",
                    method.upper(), url, _safe_headers, _body_hint, params,
                )
                response = session.request(
                    method.upper(),
                    url,
                    params=params,
                    json=json_body,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=self._timeout,
                    stream=stream,
                )
                # —— 诊断日志（排障用，默认 DEBUG）：响应关键头 ——
                _rh = response.headers
                logger.debug(
                    "[PhraseDBG] <- HTTP %s | server=%r | content-type=%r | x-request-id=%r | body_preview=%r",
                    response.status_code,
                    _rh.get("Server") or _rh.get("server"),
                    _rh.get("Content-Type") or _rh.get("content-type"),
                    _rh.get("X-Request-Id") or _rh.get("x-request-id"),
                    (getattr(response, "text", "") or "")[:300],
                )
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 任何传输错误都需重试
                last_exc = exc
                logger.warning(
                    "PhrasePlatform: %s %s failed on attempt %d/%d: %s",
                    method, path, attempt, self._retries, exc,
                )
                if attempt >= self._retries:
                    break
                _sleep(self._retry_interval)
                continue

            # 已持有令牌但回 401——可能已过期。强制重新鉴权一次，但仅当已有
            # 可自动刷新的模式（subject_token 或密码）时才重试。
            can_refresh = bool(self._subject_token or (self._username and self._password))
            if response.status_code == 401 and can_refresh and attempt == 1:
                logger.info(
                    "PhrasePlatform: 401 on %s %s — re-authenticating", method, path,
                )
                with self._token_lock:
                    self.api_token = ""
                    self._bearer_expires_at = 0.0
                self._authenticate(session)
                headers = self._headers()
                if extra_headers:
                    headers.update(extra_headers)
                continue

            # 5xx / 429 重试，其他直接返回。
            if response.status_code >= 500 or response.status_code == 429:
                logger.warning(
                    "PhrasePlatform: %s %s got HTTP %d (attempt %d/%d)",
                    method, path, response.status_code, attempt, self._retries,
                )
                if attempt >= self._retries:
                    self._raise_for_status(response, path)
                _sleep(self._retry_interval)
                continue

            self._raise_for_status(response, path)
            return response

        if last_exc is not None:
            raise PlatformError(
                f"PhrasePlatform: exhausted {self._retries} retries for {method} {path}: {last_exc}"
            ) from last_exc
        raise PlatformError(
            f"PhrasePlatform: exhausted {self._retries} retries for {method} {path}"
        )

    @staticmethod
    def _raise_for_status(response, path: str) -> None:
        """当 ``response`` 报错时抛出 :class:`PlatformError`。"""
        if 200 <= response.status_code < 300:
            return
        # 保留错误主体以便排查，但不写入任何令牌。
        body: Any = ""
        try:
            body = response.json()
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001 — 主体未必是 JSON
            body = getattr(response, "text", "")
        raise PlatformError(
            f"PhrasePlatform: {path} → HTTP {response.status_code}: {body!r}"
        )

    # ------------------------------------------------------------------
    # 适配器 API
    # ------------------------------------------------------------------
    def _project_uid(self) -> str:
        if not self.project_id:
            raise PlatformError(
                "PhrasePlatform: project_id is empty; set it on the ReviewConfig "
                "or global platform config."
            )
        return self.project_id

    def _ensure_import_settings(self, target_locale: str) -> str:
        """按需创建一个 multilingual-XLSX 的 ImportSettings 对象，返回 uid。

        **为什么需要**：Phrase 的默认 XLSX import 解析器不识别本项目固定的
        5 列格式（``Key | Source | Target | Context | Comment``），直接 upload
        会导致 ``wordsCount=0, segments=[]``，UI 显示 "The job has no segments
        and cannot be accessed. Job is empty"。按 Phrase 官方
        ``POST /api2/v1/importSettings`` 的 ``MultilingualXlsSettingsDtoV1``
        schema 构造 ImportSettings，让 Phrase 按本框架 XLSX 的列映射把它正确
        解析成 segments。

        **列映射**（和 :class:`XlsxSource` 的 ``_HEADERS`` 对齐）::

            A = Key     → contextKeyColumn（上下文 key）
            B = Source  → sourceColumn
            C = Target  → targetColumns[target_locale]
            D = Context → contextNoteColumn（上下文备注）
            E = Comment → 本次不传给 Phrase（Phrase 没对应字段）

        **复用策略**（2025+ 优化）：ImportSettings 在 Phrase 侧是**账号级**
        对象（不是项目级），重复 POST 会**无限累积**同名垃圾。本方法改为：
          1. 先 ``GET /v1/importSettings`` 列表按 ``name == settings_name``
             查找已存在的，有则直接复用其 ``uid``；
          2. 没有再 POST 新建。
        这样一个账号 × 一个 target_locale 对应至多一个 ImportSettings，流水线
        重跑不会污染账号。

        **缓存策略**：PhrasePlatform 实例生命周期内只查/建一次（``self.
        _import_settings_uid`` 缓存）。

        **降级**：若查询/创建失败（权限、网络等），记空串，upload 退回不带
        ``importSettings`` 的模式。
        """
        if self._import_settings_uid is not None:
            # 已尝试过（成功 → 非空字符串；失败 → 空串）；都不再重试。
            return self._import_settings_uid

        settings_name = f"TiMi_HOK_Game_Translator_xlsx_{target_locale}"

        # Step 1: 先尝试复用现有同名 ImportSettings
        try:
            resp = self._request(
                "GET",
                "/v1/importSettings",
                params={"pageSize": 50},
            )
            existing = resp.json().get("content", []) if callable(getattr(resp, "json", None)) else []
            for item in existing:
                if item.get("name") == settings_name and item.get("uid"):
                    uid = str(item["uid"])
                    self._import_settings_uid = uid
                    logger.info(
                        "PhrasePlatform: reused existing ImportSettings uid=%s "
                        "name=%r (avoid account-level duplication)",
                        uid, settings_name,
                    )
                    return uid
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 查询失败则走创建分支
            logger.debug(
                "PhrasePlatform: list ImportSettings failed (%s); will try to create.",
                exc,
            )

        # Step 2: 没有同名 → 创建新的
        body = {
            "name": settings_name,
            "fileImportSettings": {
                "fileFormat": "multiling_xls",
                "autodetectMultilingualFiles": True,
                "multilingualXls": {
                    "sourceColumn": "B",
                    "targetColumns": {target_locale: "C"},
                    "contextKeyColumn": "A",
                    "contextNoteColumn": "D",
                    "importRows": "2-",       # 跳过首行表头
                    "segmentation": True,
                },
            },
        }
        try:
            response = self._request(
                "POST",
                "/v1/importSettings",
                json_body=body,
                extra_headers={"Content-Type": "application/json"},
            )
            uid = str(response.json().get("uid") or "")
            self._import_settings_uid = uid
            if uid:
                logger.info(
                    "PhrasePlatform: created ImportSettings uid=%s name=%r "
                    "(multilingualXls: A=key, B=source, C=target[%s], D=contextNote)",
                    uid, settings_name, target_locale,
                )
            else:
                logger.warning(
                    "PhrasePlatform: ImportSettings creation returned no uid; "
                    "upload will fall back to default (segments may be empty).",
                )
            return uid
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 创建失败不致命，走降级分支
            logger.warning(
                "PhrasePlatform: ImportSettings creation failed (%s); upload "
                "will fall back to default (segments may be empty). This is "
                "non-fatal but reviewers won't see translatable segments in UI.",
                exc,
            )
            self._import_settings_uid = ""  # 标记尝试过且失败，避免反复 POST
            return ""

    def upload_source(self, file_path: str, *, remote_path: str = "") -> UploadResult:
        """将 ``file_path`` 以新 Phrase Job 的形式上传到项目。

        Phrase 中 Job 的源语言固定为项目源语言，目标语言则归一个 Job；
        因此调用方通常通过 :meth:`create_task` 为每个目标语种创建一个 Job。

        **Phrase 契约要点**（2024+）：
          * 请求体必须是**纯文件二进制**（``application/octet-stream``），
            **不能**用 ``multipart/form-data``——后者会被 API 网关识别不出而
            返回 ``404 Not Found``；
          * ``Content-Disposition`` 必须**严格匹配**服务器正则：
            ``((inline|attachment); )?(filename\\*=UTF-8''(.+)|filename="?(.+)"?)`` —
            即 ``filename=`` 和 ``filename*=`` **二选一不可同时存在**。
            含中文时统一用 ``filename*=UTF-8''<pct-encoded>``；
          * ``Memsource`` 头承载 JSON 元信息（``targetLangs``、
            ``importSettings`` 等），必须是 ASCII（``ensure_ascii=True``）。
        """
        from urllib.parse import quote as _url_quote

        project_uid = self._project_uid()
        filename = os.path.basename(remote_path) or os.path.basename(file_path)
        # Phrase 服务器只允许单一 filename 字段。有非 ASCII 字符时用
        # RFC 5987 的 ``filename*=UTF-8''<pct-encoded>``；全 ASCII 则直接
        # 用 ``filename="..."``——避免同时提供两者触发 400 Bad Request。
        is_ascii = all(ord(ch) < 128 for ch in filename)
        if is_ascii:
            content_disposition = f'attachment; filename="{filename}"'
        else:
            encoded_filename = _url_quote(filename, safe="")
            content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

        # Memsource 元信息：
        #   * ``targetLangs``：Phrase 支持一个 upload 产出多个 target-locale Job；
        #     本框架每个语种独立上传，所以这里直接把 target_locale 塞进去。
        #     读取优先级：构造时从 ``extra["target_language_id"]`` 兜底的
        #     ``self._target_locale`` > 外部动态赋值的 ``self.target_locale``
        #     属性 > 空串。
        #     **⚠️ 实测**：此字段**必须非空**，否则 Phrase API 网关会在应用层
        #     之前直接返回 ``404 Not Found``（Spring 兜底 ``{"error":{"message":
        #     "Not Found","code":404}}`` 格式），和路径找不到完全无法区分。
        #   * **不要**传 ``importSettings: {}``：Phrase 会把它解释为"引用一个
        #     uid=null 的 Import Settings 对象"而报 ``ResourceNotFound``；
        #     省略此字段即走项目模板的默认 import 行为（含 pre-translate 等）。
        target_locale = (
            self._target_locale
            or str(getattr(self, "target_locale", "") or "")
        )
        metadata: Dict[str, Any] = {}
        if target_locale:
            metadata["targetLangs"] = [target_locale]
        if self._workflow_step_uid:
            metadata["workflowSteps"] = [{"uid": self._workflow_step_uid}]

        # 【方案 🅒】引用按需创建的 ImportSettings——让 Phrase 按 ``Key|Source|Target|
        # Context|Comment`` 5 列模板解析 XLSX，使 segments > 0。若创建失败则降级
        # 为不带 ``importSettings``（入 Phrase 默认 import，解析出来是 0 条 segment 但
        # job 条目本身能被创建）。
        if target_locale:
            settings_uid = self._ensure_import_settings(target_locale)
            if settings_uid:
                metadata["importSettings"] = {"uid": settings_uid}

        with open(file_path, "rb") as handle:
            file_bytes = handle.read()
        response = self._request(
            "POST",
            f"/v1/projects/{project_uid}/jobs",
            data=file_bytes,
            extra_headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": content_disposition,
                "Memsource": json.dumps(metadata, ensure_ascii=True),
            },
        )

        data = response.json()
        # Phrase 返回体形如 { "jobs": [{ "uid": "...", ... }, ...] }
        jobs = data.get("jobs") or []
        if not jobs:
            raise PlatformError(
                "PhrasePlatform: upload response missing 'jobs' payload."
            )
        job_uid = jobs[0].get("uid", "")
        internal_id = data.get("asyncRequest", {}).get("id") or job_uid or filename
        file_id = f"phrase::{project_uid}::{job_uid}"
        self._jobs[file_id] = {
            "project_uid": project_uid,
            "job_uid": job_uid,
            # 【fallback 方案 A 用】记原始上传文件绝对路径——当 MXLF 段级拆分
            # （方案 C）失败降级时，直接把原上传 xlsx 复制为 pending.xlsx 让
            # 下游 ``XlsxSource.load`` 能拿到完整 Entry 列表（含 LLM 译文）。
            "source_file_path": os.path.abspath(file_path),
        }
        logger.info(
            "PhrasePlatform: uploaded %s (jobUid=%s, projectUid=%s)",
            filename, job_uid, project_uid,
        )

        # ⚠️ import gate：Phrase 的 ``POST /jobs`` 只是 "上传完成 + 创建占位
        # Job"，真实的 segment 解析是**异步**跑的（``asyncRequest.action =
        # IMPORT_JOB``）。实测 ~5 秒。如果不等 import 完成就返回：
        #   * 下游调 ``get_task_status``/轮询，看到的始终是 ``status=NEW,
        #     wordsCount=-1``，根本没进入"审员可操作"状态；
        #   * 用户 UI 打开 job 看到 "The job has no segments, Job is empty"；
        #   * ``bilingualFile`` 导出 404 ``ResourceNotFound: 工作未正确导入``。
        # 所以必须阻塞到 ``importStatus.status == OK``；若 ERROR 立刻抛错，
        # 让流水线上层通过 ``PlatformError`` 感知；超时也抛错避免悬挂。
        try:
            self._wait_for_import(project_uid, job_uid)
        except PlatformError:
            # 清理失败的本地缓存（Phrase 侧也应清理，但 Phrase 对 import ERROR
            # 的 job 已经视为垃圾，调用方可以择机 delete_task）
            self._jobs.pop(file_id, None)
            raise

        return UploadResult(
            file_id=file_id,
            revision=str(internal_id),
            extra={"job_uid": job_uid, "project_uid": project_uid, "filename": filename},
        )

    def _wait_for_import(
        self,
        project_uid: str,
        job_uid: str,
        *,
        timeout_seconds: float = 180.0,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        """阻塞轮询直到 Phrase job 的异步 import 完成。

        Phrase 对 ``POST /jobs`` 的处理是"同步建占位 Job + 异步真正解析"。
        ``GET /jobs/{jobUid}`` 返回体里的 ``importStatus.status`` 字段才是
        真正的 import 进度，取值：

          * ``"RUNNING"``：异步 import 还在进行，继续等；
          * ``"OK"``：import 完成，``wordsCount`` 变为实际词数，``imported``
            变 ``true``，``segments`` 可访问；
          * ``"ERROR"``：import 失败，``errorMessage`` 字段带错误原因（如列
            映射错、文件被识别为不支持的格式等）。

        **超时策略**：默认 180s（30 轮 × 2s）。本框架的典型文件尺寸（<1MB、
        <1000 条段落）实测 2-5s 完成，180s 保守但足够兜底 Phrase 偶发延迟。
        超时抛 :class:`PlatformError`，上层清理本地缓存。

        **兼容性兜底**：某些旧版 Phrase 响应里 ``importStatus`` 字段可能为
        ``null``；本方法额外用 ``imported == true`` 或 ``wordsCount > 0`` 作
        次级判定。
        """
        deadline = _now() + timeout_seconds
        attempt = 0
        while True:
            attempt += 1
            response = self._request(
                "GET",
                f"/v1/projects/{project_uid}/jobs/{job_uid}",
            )
            data = response.json() if callable(getattr(response, "json", None)) else {}
            status_info = data.get("importStatus") or {}
            import_status = (status_info or {}).get("status") if isinstance(status_info, dict) else ""
            imported = bool(data.get("imported"))
            words_count = data.get("wordsCount")
            try:
                words_count_int = int(words_count) if words_count is not None else -1
            except (TypeError, ValueError):
                words_count_int = -1

            # 终态：OK
            if import_status == "OK":
                logger.info(
                    "PhrasePlatform: job %s import OK (attempt=%d, wordsCount=%d)",
                    job_uid, attempt, words_count_int,
                )
                return

            # 终态：ERROR
            if import_status == "ERROR":
                err_msg = ""
                if isinstance(status_info, dict):
                    err_msg = str(status_info.get("errorMessage") or "")
                raise PlatformError(
                    f"PhrasePlatform: job {job_uid} import ERROR"
                    + (f": {err_msg}" if err_msg else "")
                )

            # 兜底判定：旧版 Phrase 可能不返回 importStatus；靠 imported 和
            # wordsCount 推断
            if (import_status in ("", None)) and imported and words_count_int > 0:
                logger.info(
                    "PhrasePlatform: job %s import inferred-done (no importStatus "
                    "field but imported=true, wordsCount=%d)",
                    job_uid, words_count_int,
                )
                return

            logger.debug(
                "[PhraseDBG] waiting for import: job=%s attempt=%d importStatus=%r "
                "imported=%s wordsCount=%s",
                job_uid, attempt, import_status, imported, words_count,
            )

            if _now() >= deadline:
                raise PlatformError(
                    f"PhrasePlatform: job {job_uid} import timed out after "
                    f"{timeout_seconds:.0f}s (last importStatus={import_status!r}, "
                    f"imported={imported}, wordsCount={words_count})"
                )
            _sleep(poll_interval_seconds)

    def create_task(
        self,
        file_ids: Sequence[str],
        target_locale: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
        title: str = "",
        description: str = "",
    ) -> TaskInfo:
        """返回描述审校 Job 的 :class:`TaskInfo`。

        Phrase 在上传时即完成 Job 创建（每份上传文件产生一或多个 Job）；
        因此本方法仅拉取 ``file_ids[0]`` 的最新状态，并补充框架需要的本地化元信息。
        """
        if not file_ids:
            raise PlatformError("PhrasePlatform.create_task: file_ids is empty.")
        file_id = file_ids[0]
        record = self._jobs.get(file_id) or _parse_file_id(file_id)
        project_uid = record["project_uid"]
        job_uid = record["job_uid"]

        response = self._request(
            "GET",
            f"/v1/projects/{project_uid}/jobs/{job_uid}",
        )
        data = response.json()
        remote_status = (data.get("status") or "").upper()
        info = TaskInfo(
            task_id=job_uid,
            status=_map_status(remote_status),
            target_locale=target_locale or data.get("targetLang", ""),
            project_id=project_uid,
            review_stage=review_stage,
            percent_completed=_extract_percent(data),
            extra={
                "raw_status": remote_status,
                "filename": data.get("filename", ""),
                "title": title,
                "description": description,
            },
        )
        return info

    def get_task_status(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> TaskInfo:
        project_uid = self._project_uid()
        response = self._request(
            "GET",
            f"/v1/projects/{project_uid}/jobs/{task_id}",
        )
        data = response.json()
        remote_status = (data.get("status") or "").upper()

        # —— 真·段级进度：调 segmentsCount 接口 ——
        # Phrase 的 ``job.status`` 轴（NEW/ACCEPTED/COMPLETED）**和已 confirmed
        # 段落数完全解耦**——只有审员**手动点 "Complete this job"**，status
        # 才会变 COMPLETED。而 ``POST /jobs/segmentsCount`` 给出的
        # ``completedSegmentsCount / segmentsCount`` 才是真实的审员工作量进度。
        # 另外 ``counts.allConfirmed`` 字段用于识别"审员已 confirm 所有段但
        # 未点 Complete this job" 的场景，供上层轮询器提前终止。
        #
        # 失败降级：segmentsCount 404/5xx 时沿用老的 ``_extract_percent``
        # （返回 0），不影响流水线继续推进。
        percent, all_confirmed, counts = self._fetch_segments_count(
            project_uid, task_id,
        )
        if counts is None:
            # 退回老的字段解析（workflowLevel.percentageCompleted 等）
            percent = _extract_percent(data)
        return TaskInfo(
            task_id=task_id,
            status=_map_status(remote_status),
            target_locale=data.get("targetLang", ""),
            project_id=project_uid,
            review_stage=review_stage,
            percent_completed=percent,
            extra={
                "raw_status": remote_status,
                "filename": data.get("filename", ""),
                "all_confirmed": all_confirmed,
                "segments_counts": counts or {},
            },
        )

    def _fetch_segments_count(
        self,
        project_uid: str,
        job_uid: str,
    ) -> "tuple[float, bool, Optional[Dict[str, Any]]]":
        """调 ``POST /v1/projects/{projectUid}/jobs/segmentsCount`` 获取段级进度。

        Phrase 2024+ 推荐这个接口替代旧的 ``workflowLevel.percentageCompleted``
        字段。返回体示例::

            {
              "segmentsCountsResults": [
                {"jobPartUid": "...",
                 "counts": {
                   "allConfirmed": false,
                   "segmentsCount": 20,
                   "completedSegmentsCount": 11,
                   "confirmedWordsCount": 180,
                   "wordsCount": 318,
                   ...
                 }}
              ]
            }

        **进度口径**：``completedSegmentsCount / segmentsCount * 100``。
        文档明确说明 ``completedSegmentsCount = confirmed + locked -
        (confirmed and locked)``——即审员真正"做完的"段落数。

        **allConfirmed**：当审员**在 UI 把所有段都 confirm** 但没点
        "Complete this job"，该字段仍为 ``true``；上层轮询器可据此提前终止。

        返回 ``(percent, all_confirmed, counts_dict_or_None)``。失败时返回
        ``(0.0, False, None)``，让调用方自行退路。
        """
        try:
            response = self._request(
                "POST",
                f"/v1/projects/{project_uid}/jobs/segmentsCount",
                json_body={"jobs": [{"uid": job_uid}]},
                extra_headers={"Content-Type": "application/json"},
            )
            payload = response.json() if callable(getattr(response, "json", None)) else {}
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 失败降级
            logger.debug(
                "[PhraseDBG] segmentsCount fetch failed for job=%s: %s",
                job_uid, exc,
            )
            return (0.0, False, None)

        results = payload.get("segmentsCountsResults") or []
        if not results:
            return (0.0, False, None)
        counts = results[0].get("counts") or {}
        total = int(counts.get("segmentsCount") or 0)
        completed = int(counts.get("completedSegmentsCount") or 0)
        all_confirmed = bool(counts.get("allConfirmed") or False)
        percent = (completed / total * 100.0) if total > 0 else 0.0
        return (percent, all_confirmed, counts)

    def get_task_percent(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> float:
        return self.get_task_status(task_id, review_stage=review_stage).percent_completed

    def download_translations(
        self,
        file_id: str,
        target_locale: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        record = self._jobs.get(file_id) or _parse_file_id(file_id)
        project_uid = record["project_uid"]
        job_uid = record["job_uid"]
        response = self._request(
            "GET",
            f"/v1/projects/{project_uid}/jobs/{job_uid}/targetFile",
            stream=True,
        )
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as fh:
            for chunk in _iter_response_content(response):
                if chunk:
                    fh.write(chunk)
        logger.info(
            "PhrasePlatform: downloaded target file for jobUid=%s → %s",
            job_uid, dest_path,
        )
        return dest_path

    def import_approved(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        # Phrase 中“已批准的数据”即为完成后的 target file，直接复用下载接口。
        project_uid = self._project_uid()
        file_id = f"phrase::{project_uid}::{task_id}"
        self._jobs.setdefault(file_id, {"project_uid": project_uid, "job_uid": task_id})
        return self.download_translations(
            file_id, "", dest_path, review_stage=review_stage,
        )

    def export_review_report(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        # Phrase 对单 job 提供“analysis”接口；为避免依赖付费的分析模块，
        # 本处仅导出一份纯文本报告，够框架使用。
        project_uid = self._project_uid()
        response = self._request(
            "GET",
            f"/v1/projects/{project_uid}/jobs/{task_id}",
        )
        data = response.json()
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Phrase review report — jobUid={task_id}\n")
            fh.write(f"stage={review_stage}\n")
            for key in ("status", "workflowLevel", "filename", "targetLang"):
                fh.write(f"{key}: {data.get(key)}\n")
        return dest_path

    def split_approved_data(
        self,
        task_id: str,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        review_stage: str = ReviewStage.FIRST.value,
    ) -> SplitResult:
        """按**段级** approved/pending 拆分 Phrase job 的译文产物。

        **方案 C（真·段级拆分，2025+ 推荐）**：
          1. 调 ``POST /v1/projects/{projectUid}/jobs/bilingualFile?format=MXLF``
             拉取 Phrase 的 MXLF（XLIFF 1.2 + Phrase ``m:`` 命名空间）；
          2. 解析每个 ``<trans-unit>`` 节点的 ``m:confirmed`` 属性：
             - ``"1"`` → **approved**（审员已 confirm 的段落，``<target>`` 内是
               审员的真实译文）；
             - ``"0"`` → **pending**（未 confirm，``<target>`` 内是 LLM 原译文
               或空）；
          3. ``approved.xlsx`` 写含真实译文的 approved 段；``pending.xlsx`` 写
             pending 段（Target 列保留 LLM 原译文，供下轮回流）；
          4. ``is_complete`` 的判定变成 "是否全部段落 confirmed=1" 而不是 Job
             整体 ``status == COMPLETED``——因为用户可以 "全部 confirm 但未
             手动 Complete this job"，这种情况之前方案 A 会错判为 pending。

        **降级**：MXLF 下载失败 / 解析失败 → 自动退回方案 A（见
        :meth:`_split_fallback_whole_job`），按 Job 整体状态做 "全有或全无"。

        **key 回映射**：MXLF 的 ``<group>/<context-group>/<context
        context-type="x-key">`` 文本就是 upload 时 XLSX 第一列 ``Key`` 的值
        （由 :class:`XlsxSource` 固定列映射 + ImportSettings 的
        ``contextKeyColumn="A"`` 共同保证）。
        """
        from ..sources import XlsxSource, Entry  # 局部导入避免顶层循环依赖

        try:
            segs = self._parse_mxlf_segments(
                self._download_bilingual_mxlf(task_id, review_stage=review_stage),
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — MXLF 失败则降级
            # 优先识别 "job 已不存在" 这类**不可恢复**错误：Phrase 侧 404
            # ResourceNotFound 意味着这个 tail job 已被人工删除/被其他 run
            # 清理，再怎么降级也拿不到数据。直接返回空 SplitResult 让上层
            # ``LastFirstReviewState`` 把 slot 当"已完成"清掉，而不是在
            # ``_split_fallback_whole_job`` 里再 404 一次导致流水线崩溃。
            if _is_job_gone_error(exc):
                logger.warning(
                    "PhrasePlatform.split_approved_data: task=%s is GONE on "
                    "Phrase side (404 ResourceNotFound). Treating as "
                    "zero-content complete to let pipeline clear the slot.",
                    task_id,
                )
                return self._empty_split_result(
                    save_approved_path=save_approved_path,
                    save_pending_path=save_pending_path,
                    raw_status="job_gone",
                )
            logger.warning(
                "PhrasePlatform.split_approved_data: MXLF segment-level split "
                "failed (%s); falling back to whole-job split (approach A).",
                exc,
            )
            return self._split_fallback_whole_job(
                task_id,
                save_approved_path=save_approved_path,
                save_pending_path=save_pending_path,
                review_stage=review_stage,
            )

        info = self.get_task_status(task_id, review_stage=review_stage)
        raw_status = info.extra.get("raw_status", "")

        # 1) 段级分桶
        approved_entries: list = []
        pending_entries: list = []
        for seg in segs:
            key = seg.get("key") or ""
            if not key:
                continue  # 没 context x-key 的段无法回映射，跳过
            entry = Entry(
                key=key,
                source_text=seg.get("source") or "",
                target_text=seg.get("target") or "",
                context=seg.get("context_note") or "",
                comment="",  # MXLF 不携带原 Excel E 列 Comment
            )
            if seg.get("confirmed"):
                approved_entries.append(entry)
            else:
                pending_entries.append(entry)

        approved_keys = [e.key for e in approved_entries]
        pending_keys = [e.key for e in pending_entries]
        is_complete = (len(pending_entries) == 0 and len(approved_entries) > 0)

        logger.info(
            "PhrasePlatform.split_approved_data: MXLF segment-level split "
            "task=%s → approved=%d pending=%d is_complete=%s (raw_status=%s)",
            task_id, len(approved_keys), len(pending_keys), is_complete, raw_status,
        )

        # 2) 写 approved.xlsx（即使 0 条也写合法空 xlsx，便于下游幂等判存在）
        approved_path_out = save_approved_path
        try:
            os.makedirs(os.path.dirname(save_approved_path) or ".", exist_ok=True)
            XlsxSource(encoding="utf-8").dump(approved_entries, save_approved_path)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "PhrasePlatform.split_approved_data: cannot write approved xlsx "
                "at %s (%s); approved_path will be empty string.",
                save_approved_path, exc,
            )
            approved_path_out = ""

        # 3) 写 pending.xlsx（仅当 save_pending_path 非空）
        pending_path_out = ""
        if save_pending_path:
            try:
                os.makedirs(os.path.dirname(save_pending_path) or ".", exist_ok=True)
                XlsxSource(encoding="utf-8").dump(pending_entries, save_pending_path)
                pending_path_out = save_pending_path
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "PhrasePlatform.split_approved_data: cannot write pending "
                    "xlsx at %s (%s); pending_path will be empty.",
                    save_pending_path, exc,
                )

        return SplitResult(
            approved_path=approved_path_out,
            pending_path=pending_path_out,
            should_continue=True,
            is_complete=is_complete,
            extra={
                "raw_status": raw_status,
                "approved_keys": approved_keys,
                "pending_keys": pending_keys,
            },
        )

    def _split_fallback_whole_job(
        self,
        task_id: str,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        review_stage: str = ReviewStage.FIRST.value,
    ) -> SplitResult:
        """**方案 A（降级 fallback）**：按 Job 整体 status 做"全有或全无"拆分。

        仅在方案 C（MXLF 段级拆分）失败时触发（例如 Phrase 版本不支持
        ``bilingualFile`` 接口、网络抖动、MXLF 格式变更等）。保留此分支以保
        证流水线在平台异常时仍能完成一轮——即使拆分粒度退回到 job 级。

        **COMPLETED 分支**：
          * ``approved.xlsx`` ← :meth:`import_approved` 下载的双语文件；
          * ``pending.xlsx`` 为仅表头的占位；
          * ``extra = {approved_keys: [全部], pending_keys: []}``。

        **非 COMPLETED 分支**（stop_time 到期但 Phrase 尚未审完）：
          * ``approved.xlsx`` 为仅表头占位；
          * ``pending.xlsx`` ← 原始上传 xlsx 的完整副本；
          * ``extra = {approved_keys: [], pending_keys: [全部]}``。
        """
        import shutil
        from pathlib import Path as _Path
        from ..sources import XlsxSource  # 局部导入，避免顶层循环依赖

        try:
            info = self.get_task_status(task_id, review_stage=review_stage)
        except Exception as exc:  # noqa: BLE001 — 二级 404 保护
            if _is_job_gone_error(exc):
                logger.warning(
                    "PhrasePlatform._split_fallback_whole_job: task=%s is GONE "
                    "(get_task_status 404). Treating as zero-content complete.",
                    task_id,
                )
                return self._empty_split_result(
                    save_approved_path=save_approved_path,
                    save_pending_path=save_pending_path,
                    raw_status="job_gone",
                )
            raise
        is_approved = info.status == TaskStatus.APPROVED

        if is_approved:
            # —— 全部通过分支 ——
            approved = self.import_approved(
                task_id, save_approved_path, review_stage=review_stage,
            )
            approved_keys: list = []
            try:
                entries = XlsxSource(encoding="utf-8").load(approved)
                approved_keys = [e.key for e in entries if getattr(e, "key", "")]
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 读失败不致命，仅告警
                logger.warning(
                    "PhrasePlatform._split_fallback_whole_job: approved file %s "
                    "cannot be parsed as xlsx (%s); approved_keys will be empty.",
                    approved, exc,
                )
            pending = ""
            if save_pending_path:
                os.makedirs(os.path.dirname(save_pending_path) or ".", exist_ok=True)
                try:
                    XlsxSource(encoding="utf-8").dump([], save_pending_path)
                    pending = save_pending_path
                except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                    logger.warning(
                        "PhrasePlatform._split_fallback_whole_job: cannot write "
                        "empty pending xlsx at %s (%s); leaving pending_path empty.",
                        save_pending_path, exc,
                    )
            return SplitResult(
                approved_path=approved,
                pending_path=pending,
                should_continue=True,
                is_complete=True,
                extra={
                    "raw_status": info.extra.get("raw_status", ""),
                    "approved_keys": approved_keys,
                    "pending_keys": [],
                },
            )

        # —— 未完成分支：全部视为 pending ——
        pending_source_path = self._lookup_source_file_path(task_id)

        pending_path = ""
        pending_keys: list = []
        if save_pending_path:
            os.makedirs(os.path.dirname(save_pending_path) or ".", exist_ok=True)
            if pending_source_path and _Path(pending_source_path).exists():
                try:
                    shutil.copyfile(pending_source_path, save_pending_path)
                    pending_path = save_pending_path
                    logger.info(
                        "PhrasePlatform._split_fallback_whole_job: pending.xlsx ← "
                        "copied from upload source %s",
                        pending_source_path,
                    )
                except OSError as exc:
                    logger.warning(
                        "PhrasePlatform._split_fallback_whole_job: failed to copy "
                        "upload source %s → %s (%s); falling back to targetFile download.",
                        pending_source_path, save_pending_path, exc,
                    )
            if not pending_path:
                try:
                    pending_path = self.import_approved(
                        task_id, save_pending_path, review_stage=review_stage,
                    )
                    logger.info(
                        "PhrasePlatform._split_fallback_whole_job: pending.xlsx ← "
                        "fallback: downloaded targetFile for job=%s (upload source "
                        "not available).",
                        task_id,
                    )
                except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                    logger.warning(
                        "PhrasePlatform._split_fallback_whole_job: fallback targetFile "
                        "download also failed (%s); pending.xlsx will be empty.",
                        exc,
                    )
            if pending_path:
                try:
                    entries = XlsxSource(encoding="utf-8").load(pending_path)
                    pending_keys = [e.key for e in entries if getattr(e, "key", "")]
                except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                    logger.warning(
                        "PhrasePlatform._split_fallback_whole_job: cannot parse "
                        "pending xlsx %s (%s); pending_keys will be empty.",
                        pending_path, exc,
                    )

        approved_path_out = save_approved_path
        try:
            os.makedirs(os.path.dirname(save_approved_path) or ".", exist_ok=True)
            XlsxSource(encoding="utf-8").dump([], save_approved_path)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "PhrasePlatform._split_fallback_whole_job: cannot write empty "
                "approved xlsx at %s (%s); approved_path will be empty string.",
                save_approved_path, exc,
            )
            approved_path_out = ""

        return SplitResult(
            approved_path=approved_path_out,
            pending_path=pending_path,
            should_continue=False,
            is_complete=False,
            extra={
                "raw_status": info.extra.get("raw_status", ""),
                "approved_keys": [],
                "pending_keys": pending_keys,
            },
        )

    def _empty_split_result(
        self,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        raw_status: str = "",
    ) -> SplitResult:
        """构造一个"零内容"的 :class:`SplitResult`，用于 Phrase job 已消失等
        不可恢复场景。

        **使用场景**：
          * tail job 在 Phrase 侧被人工删除 / 已被另一次 run 清理 → 当前
            run 没数据可审，应放流水线继续推进（下一轮会从头建新 job）；
          * ``split_approved_data`` 的 MXLF 下载 404、``get_task_status``
            404 都走这里，避免 ``_split_fallback_whole_job`` 二级 404 把流
            水线崩掉。

        **产物契约**：
          * ``approved.xlsx`` 和 ``pending.xlsx`` 都写**仅表头**的合法空
            xlsx（下游 ``XlsxSource.load`` 能读到 ``entries == []``，
            ``_apply_split_to_entries`` 会把 ``ctx.entries`` 筛空）；
          * ``is_complete=False``：没有真正审完，上层 ``LastFirstReviewState``
            看到就清掉 ``last_tasks.json`` 的 slot；
          * ``should_continue=True``：允许流水线进入下游 state；
          * ``extra.raw_status`` 带入传参（典型 ``"job_gone"``）。
        """
        from ..sources import XlsxSource  # 局部导入避免顶层循环依赖

        approved_out = save_approved_path
        try:
            os.makedirs(os.path.dirname(save_approved_path) or ".", exist_ok=True)
            XlsxSource(encoding="utf-8").dump([], save_approved_path)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "PhrasePlatform._empty_split_result: cannot write empty "
                "approved xlsx at %s (%s); approved_path will be empty.",
                save_approved_path, exc,
            )
            approved_out = ""

        pending_out = ""
        if save_pending_path:
            try:
                os.makedirs(os.path.dirname(save_pending_path) or ".", exist_ok=True)
                XlsxSource(encoding="utf-8").dump([], save_pending_path)
                pending_out = save_pending_path
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "PhrasePlatform._empty_split_result: cannot write empty "
                    "pending xlsx at %s (%s); pending_path will be empty.",
                    save_pending_path, exc,
                )

        return SplitResult(
            approved_path=approved_out,
            pending_path=pending_out,
            should_continue=True,
            is_complete=False,
            extra={
                "raw_status": raw_status,
                "approved_keys": [],
                "pending_keys": [],
            },
        )

    # ------------------------------------------------------------------
    # MXLF（Phrase 双语 XLIFF）相关辅助——方案 C 的核心
    # ------------------------------------------------------------------
    def _download_bilingual_mxlf(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,  # noqa: ARG002 — 暂不区分 stage
    ) -> bytes:
        """调 ``POST /v1/projects/{projectUid}/jobs/bilingualFile?format=MXLF``
        下载指定 job 的 Phrase MXLF 双语文件（二进制）。

        **接口契约**（2025+ 实测）：
          * 必须用 ``POST``（不是 GET）；
          * 请求体 ``{"jobs":[{"uid":"<job_uid>"}]}``；
          * ``Accept`` 不能是 ``application/json`` —— MXLF 走
            ``application/mxliff;charset=utf-8``，这里设为 ``*/*``；
          * ``format=MXLF`` 作为 query param。
        """
        project_uid = self._project_uid()
        response = self._request(
            "POST",
            f"/v1/projects/{project_uid}/jobs/bilingualFile",
            json_body={"jobs": [{"uid": task_id}]},
            params={"format": "MXLF"},
            extra_headers={
                "Accept": "*/*",
                "Content-Type": "application/json",
            },
        )
        return response.content

    @staticmethod
    def _parse_mxlf_segments(mxlf_bytes: bytes) -> list:
        """解析 Phrase MXLF 字节流，返回每段的 ``dict`` 列表。

        返回元素字段::

            {
                "key":           str,  # <context context-type="x-key">...</context>
                "source":        str,  # <source> 文本
                "target":        str,  # <target> 文本
                "confirmed":     bool, # m:confirmed=="1"
                "context_note":  str,  # 其他 <context> 文本（如果有）
            }

        **XML 命名空间**：MXLF 混用 XLIFF 1.2 (``urn:oasis:names:tc:xliff:document:1.2``)
        和 Phrase (``http://www.memsource.com/mxlf/2.0``)。``<source>`` /
        ``<target>`` / ``<group>`` / ``<trans-unit>`` / ``<context-group>`` /
        ``<context>`` 都在 XLIFF 默认命名空间下；``m:confirmed`` 属性在 Phrase
        命名空间下。

        **容错**：解析失败（空字节、XML 格式错误等）抛 :class:`PlatformError`，
        由调用方降级到方案 A。
        """
        import xml.etree.ElementTree as ET

        if not mxlf_bytes:
            raise PlatformError("PhrasePlatform: empty MXLF payload")

        try:
            root = ET.fromstring(mxlf_bytes)
        except ET.ParseError as exc:
            raise PlatformError(
                f"PhrasePlatform: malformed MXLF ({exc})"
            ) from exc

        NS_XLIFF = "urn:oasis:names:tc:xliff:document:1.2"  # pylint: disable=invalid-name
        NS_PHRASE = "http://www.memsource.com/mxlf/2.0"  # pylint: disable=invalid-name
        CONFIRMED_ATTR = f"{{{NS_PHRASE}}}confirmed"  # pylint: disable=invalid-name

        segments: list = []
        # 遍历所有 <trans-unit>（在 group 下，也可能直接在 body 下）
        for tu in root.iter(f"{{{NS_XLIFF}}}trans-unit"):
            source_elem = tu.find(f"{{{NS_XLIFF}}}source")
            target_elem = tu.find(f"{{{NS_XLIFF}}}target")
            source_text = _xliff_elem_text(source_elem)
            target_text = _xliff_elem_text(target_elem)
            confirmed = (tu.get(CONFIRMED_ATTR, "0") == "1")

            # key 来自父 <group>/<context-group>/<context context-type="x-key">
            # XLIFF 没父指针，向上找需用 iter 的侧扫路线
            segments.append({
                "key": "",  # 稍后用 group 层扫描补齐
                "source": source_text,
                "target": target_text,
                "confirmed": confirmed,
                "context_note": "",
                "_tu_id": tu.get("id", ""),
            })

        # 再扫一遍 <group>，用它的 <context-group> 补齐 key / context_note
        # —— 一个 group 对应一个 trans-unit（Phrase MXLF 的约定）
        tu_id_to_meta: Dict[str, Dict[str, str]] = {}
        for group in root.iter(f"{{{NS_XLIFF}}}group"):
            key = ""
            context_note = ""
            for ctx in group.iter(f"{{{NS_XLIFF}}}context"):
                ctype = ctx.get("context-type", "")
                text = (ctx.text or "").strip()
                if ctype == "x-key":
                    key = text
                elif ctype in ("x-context", "x-note", "note"):
                    # 其他类型的 context 当作 context_note（罕见）
                    if text and not context_note:
                        context_note = text
            tu_in_group = group.find(f"{{{NS_XLIFF}}}trans-unit")
            if tu_in_group is not None:
                tu_id_to_meta[tu_in_group.get("id", "")] = {
                    "key": key,
                    "context_note": context_note,
                }

        for seg in segments:
            meta = tu_id_to_meta.get(seg["_tu_id"], {})
            seg["key"] = meta.get("key", "")
            seg["context_note"] = meta.get("context_note", "")
            seg.pop("_tu_id", None)

        return segments

    def _lookup_source_file_path(self, job_uid: str) -> str:
        """在 ``self._jobs`` 内存缓存里按 ``job_uid`` 反查原上传文件路径。

        * 若调用方传入的 ``task_id`` 就是 ``file_id``（``phrase::proj::job``），
          直接命中；
        * 否则遍历 values 匹配 ``job_uid`` 字段——这是本次 run 内刚上传过的
          job 走 split 分支时的典型场景；
        * 跨 run 续审（Day-N）时内存缓存是空，返回空串，由调用方处理退路。
        """
        record = self._jobs.get(job_uid) or self._jobs.get(f"phrase::{self._project_uid()}::{job_uid}")
        if isinstance(record, dict):
            path = str(record.get("source_file_path") or "")
            if path:
                return path
        for cached in self._jobs.values():
            if isinstance(cached, dict) and cached.get("job_uid") == job_uid:
                path = str(cached.get("source_file_path") or "")
                if path:
                    return path
        return ""

    def delete_task(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        """删除指定 Phrase job。

        **端点选择**：Phrase 新版 TMS 的删除走
        ``DELETE /v1/projects/{projectUid}/jobs/batch`` 而不是
        ``.../jobs``——后者 ``Allow`` 头只有 ``HEAD,POST,GET,OPTIONS``，
        调用会返回 ``405 Method Not Allowed``。通过手工 ``OPTIONS`` 探测
        得到 ``jobs/batch`` 的 ``Allow: DELETE,OPTIONS,PUT``，实际 DELETE
        返回 ``204 No Content`` 已验证。
        """
        project_uid = self._project_uid()
        self._request(
            "DELETE",
            f"/v1/projects/{project_uid}/jobs/batch",
            json_body={"jobs": [{"uid": task_id}]},
        )
        # 同时清理本地缓存。
        for cached_id, record in list(self._jobs.items()):
            if record.get("job_uid") == task_id:
                self._jobs.pop(cached_id, None)

    def get_project_name(self, project_id: str = "") -> str:
        uid = project_id or self.project_id
        if not uid:
            return ""
        response = self._request("GET", f"/v1/projects/{uid}")
        data = response.json()
        return data.get("name") or uid

    # ------------------------------------------------------------------
    # 翻译记忆（TM）回灌
    # ------------------------------------------------------------------
    # 以下 4 个方法为**可选扩展**，不属于 :class:`TranslationPlatform` 基类的
    # 抽象 API——由 ``update_tm_state`` 通过 ``hasattr`` 探测调用。
    # Phrase TM 相关端点（详见 docs/platforms/report_final.md）：
    #   * 项目 TM 列表：GET  /api2/v3/projects/{projectUid}/transMemories
    #     响应体 ``transMemories[*]`` 元素含 ``transMemory.uid`` 和
    #     ``writeMode``。回灌时取 ``writeMode=true`` 的那一条作为"默认 TM"；
    #     若全部 writeMode=false，则取第一条兜底。
    #   * 清空 TM 片段：DELETE /api2/v2/transMemories/{uid}/segments  → 202
    #   * 导入 TMX/xlsx：POST /api2/v2/transMemories/{uid}/import     → 202
    #     - 请求体直接传二进制文件
    #     - 必须带 Content-Disposition: ``attachment; filename*=UTF-8''<name>``
    def get_project_default_tm_id(self) -> str:
        """返回当前项目用于 writeMode 的 TM 库 UID；查不到返回空串。"""
        uid = self._project_uid()
        if not uid:
            return ""
        try:
            response = self._request(
                "GET", f"/v3/projects/{uid}/transMemories",
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "PhrasePlatform.get_project_default_tm_id: GET "
                "/v3/projects/%s/transMemories failed: %s", uid, exc,
            )
            return ""
        data = response.json() if response is not None else {}
        tm_list = data.get("transMemories") or []
        if not tm_list:
            logger.warning(
                "PhrasePlatform.get_project_default_tm_id: project %s has no "
                "transMemories assigned", uid,
            )
            return ""
        # 优先 writeMode=true 的 TM；否则取第一条兜底
        write_tm = next(
            (item for item in tm_list if item.get("writeMode")), tm_list[0],
        )
        tm_entry = write_tm.get("transMemory") or {}
        tm_uid = str(tm_entry.get("uid") or "")
        if not tm_uid:
            logger.warning(
                "PhrasePlatform.get_project_default_tm_id: TM entry missing uid: %r",
                write_tm,
            )
        return tm_uid

    def clear_tm_segments(self, tm_id: str) -> bool:
        """清空指定 TM 库下的所有片段。成功返回 True，失败返回 False（不抛）。

        调 ``DELETE /api2/v2/transMemories/{tm_id}/segments``，异步 202。
        """
        if not tm_id:
            return False
        try:
            self._request("DELETE", f"/v2/transMemories/{tm_id}/segments")
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "PhrasePlatform.clear_tm_segments: DELETE "
                "/v2/transMemories/%s/segments failed: %s", tm_id, exc,
            )
            return False
        logger.info(
            "PhrasePlatform: cleared TM segments for tm_uid=%s (async request)",
            tm_id,
        )
        return True

    def upload_tm(self, tm_file_path: str, *, target_locale: str, tm_id: str = "") -> bool:
        """把本地 TM xlsx/TMX 文件上传到项目默认 TM 库（**先清后传**）。

        流程：
          1. 若 ``tm_id`` 为空，自动调用 :meth:`get_project_default_tm_id`；
          2. 调用 :meth:`clear_tm_segments` 清空旧 TM；
          3. ``POST /api2/v2/transMemories/{tm_id}/import`` 二进制上传。

        参数：
            tm_file_path: 由 :mod:`utils.tm_file_builder` 产出的 xlsx 文件
                （Phrase 自动按扩展名识别为 Excel 格式）。
            target_locale: 保留以保持与 Crowdin 版 ``upload_tm`` 签名一致；
                Phrase TMX import 不需要显式传 target_locale，列头已含语种。
            tm_id: 可选，直接指定 TM UID；为空则取项目默认 TM。

        返回：
            True 全链路成功；False 任一步失败。失败只记日志，不抛异常。
        """
        import os as _os

        _ = target_locale  # 保持签名一致；Phrase 不需要这个参数

        if not _os.path.exists(tm_file_path):
            logger.warning(
                "PhrasePlatform.upload_tm: file not found: %s", tm_file_path,
            )
            return False

        tm_id = tm_id or self.get_project_default_tm_id()
        if not tm_id:
            return False

        # 先清后传
        self.clear_tm_segments(tm_id)

        filename = _os.path.basename(tm_file_path)
        # RFC 5987 扩展：Phrase 要求 Content-Disposition 必须用 UTF-8 编码
        from urllib.parse import quote as _quote
        content_disposition = (
            f"attachment; filename*=UTF-8''{_quote(filename, safe='')}"
        )

        try:
            with open(tm_file_path, "rb") as fh:
                data = fh.read()
            self._request(
                "POST",
                f"/v2/transMemories/{tm_id}/import",
                data=data,
                extra_headers={
                    "Content-Disposition": content_disposition,
                    "Content-Type": "application/octet-stream",
                },
            )
            logger.info(
                "PhrasePlatform.upload_tm: imported TM into tm_uid=%s (file=%s)",
                tm_id, filename,
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — TM 回灌失败不阻塞主流程
            logger.warning(
                "PhrasePlatform.upload_tm: failed to import TM to tm_uid=%s "
                "(file=%s): %s", tm_id, filename, exc,
            )
            return False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
_FILE_ID_RE = re.compile(r"^phrase::(?P<project>[^:]+)::(?P<job>[^:]+)$")


def _parse_file_id(file_id: str) -> Dict[str, str]:
    """尽力从不透明的 ``file_id`` 中写回 ``(project_uid, job_uid)``。"""
    match = _FILE_ID_RE.match(file_id or "")
    if not match:
        raise PlatformError(
            f"PhrasePlatform: unknown file_id {file_id!r} — expected "
            "'phrase::<projectUid>::<jobUid>'."
        )
    return {"project_uid": match.group("project"), "job_uid": match.group("job")}


def _iter_response_content(response, chunk_size: int = 8192):
    """递增迭代 ``response`` 主体，兼容未提供流式接口的 mock 对象。"""
    if hasattr(response, "iter_content"):
        yield from response.iter_content(chunk_size=chunk_size)
        return
    payload = getattr(response, "content", b"") or b""
    yield payload


def _sleep(seconds: float) -> None:
    """封装 ``time.sleep``，便于测试 patch。"""
    import time as _time
    _time.sleep(max(0.0, seconds))


def _now() -> float:
    """返回当前 UNIX 时间戳；单独抽出便于测试 patch。"""
    import time as _time
    return _time.time()


def _is_job_gone_error(exc: BaseException) -> bool:
    """判定一个异常是否属于"Phrase job 已不存在"类错误。

    Phrase TMS 对已删除/未成功导入的 job 返回 HTTP 404，错误体通常是以下
    两种模式之一（EU 中文返回；英文服务器可能是 ``Not Found``）::

        {"errorCode":"ResourceNotFound",
         "errorDescription":"[UidReference(uid:xxx)]工作未正确导入或导入正在进行 ..."}

        {"errorCode":"无效的参数",
         "errorDescription":"被"jobUid"字段和"xxx"值所引用的对象找不到。"}

    由于 :class:`PlatformError` 的 message 里会包含 ``HTTP 404`` 和原始错
    误 body（见 :meth:`PhrasePlatform._raise_for_status`），本函数通过字
    符串匹配识别。保守起见只匹配 **404 + 下列任一关键词**：

      * ``ResourceNotFound`` — 删除/没导入成功的通用错误码
      * ``找不到`` / ``已删除`` — 中文返回的两种描述
      * ``Not Found`` — 英文返回

    **只应用于识别"不可恢复、应优雅跳过"的场景**（如 split 时 tail job
    已被人工删除）。网络超时、鉴权失败、重试类错误**不**走这里。
    """
    msg = str(exc) if exc is not None else ""
    if "404" not in msg:
        return False
    for keyword in ("ResourceNotFound", "找不到", "已删除", "Not Found"):
        if keyword in msg:
            return True
    return False


def _xliff_elem_text(elem) -> str:
    """提取 XLIFF ``<source>`` / ``<target>`` 的纯文本内容。

    XLIFF 允许 inline tag（``<g>``、``<ph>`` 等）嵌入到 ``<source>`` /
    ``<target>`` 中：::

        <target>Hello <g id="1">World</g>!</target>

    对于 Phrase MXLF 的双语文件，我们只关心最终呈现给审员的**可读文本**，
    inline tag 本身是 XLIFF 的格式元信息，不应保留。本函数做深度文本遍历，
    把 ``elem.text`` + 每个子节点的 ``.text`` + ``tail`` 按顺序拼起来。

    若 ``elem`` 为 ``None`` 则返回空串。
    """
    if elem is None:
        return ""
    parts: list = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_xliff_elem_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
register_platform("phrase", PhrasePlatform)


__all__ = ["PhrasePlatform"]
