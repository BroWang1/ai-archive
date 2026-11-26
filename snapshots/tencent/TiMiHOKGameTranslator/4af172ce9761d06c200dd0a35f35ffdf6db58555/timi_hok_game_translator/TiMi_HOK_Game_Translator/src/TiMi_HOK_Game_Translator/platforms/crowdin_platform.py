"""Crowdin（Crowdin API v2）翻译平台适配器。

基于 **Crowdin REST API v2** 实现
:class:`~TiMi_HOK_Game_Translator.platforms.TranslationPlatform` 契约。

参考文档：

* API 概览 — https://developer.crowdin.com/api/v2/
* 文件相关 — https://developer.crowdin.com/api/v2/#tag/Source-Files
* 任务相关 — https://developer.crowdin.com/api/v2/#tag/Tasks
* 译文相关 — https://developer.crowdin.com/api/v2/#tag/Translations
* 存储相关 — https://developer.crowdin.com/api/v2/#tag/Storage

鉴权方式
--------
Crowdin Cloud 使用**个人访问令牌**（Bearer）。企业版采用同一令牌模型但
 API base 不同：``https://<org>.api.crowdin.com/api/v2``。调整 ``api_base`` 即可兼容两者。

使用的接口
------------
====================================  ===============================================================
用途                                  接口（相对于 ``api_base``）
====================================  ===============================================================
添加 storage（上传文件体）                ``POST /storages``（原始文件体）
将源文件挂到项目                        ``POST /projects/{projectId}/files``
创建任务                                ``POST /projects/{projectId}/tasks``
获取任务                                ``GET  /projects/{projectId}/tasks/{taskId}``
删除任务                                ``DELETE /projects/{projectId}/tasks/{taskId}``
导出任务译文                            ``POST /projects/{projectId}/translations/exports``
下载导出后文件                          ``GET  <exports 接口返回的 URL>``
获取项目                                ``GET  /projects/{projectId}`
====================================  ===============================================================

本适配器故意保持**短小**，只覆盖框架实际需要的接口。如需术语、机器翻译、
截图等能力，可继承本类自行扩展。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence

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

_DEFAULT_API_BASE = "https://api.crowdin.com/api/v2"


# Crowdin 任务状态 → 框架状态。
_STATUS_MAP: Dict[str, TaskStatus] = {
    "todo": TaskStatus.PENDING,
    "in_progress": TaskStatus.IN_PROGRESS,
    "done": TaskStatus.APPROVED,
    "closed": TaskStatus.APPROVED,
    "cancelled": TaskStatus.REJECTED,
    "canceled": TaskStatus.REJECTED,
}


def _map_status(remote: str) -> TaskStatus:
    if not remote:
        return TaskStatus.UNKNOWN
    return _STATUS_MAP.get(remote.lower(), TaskStatus.UNKNOWN)


# ---------------------------------------------------------------------------
# 适配器主体
# ---------------------------------------------------------------------------
class CrowdinPlatform(TranslationPlatform):
    """Crowdin API v2 适配器。

    支持的 ``extra`` key：

    * ``directory_id``——将上传文件挂在指定目录下；
    * ``workflow_step_id``——将任务固定到某个工作流步；
    * ``timeout_seconds`` / ``retries`` / ``retry_interval_seconds``——HTTP 可调参数；
    * ``session_factory``——高级选项，可传入自定义的 ``requests.Session`` 工厂。
    """

    platform_name = "crowdin"
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
        super().__init__(
            api_base=api_base or _DEFAULT_API_BASE,
            api_token=api_token,
            project_id=project_id,
            extra=extra,
        )
        self.api_base = self.api_base.rstrip("/")

        self._directory_id: str = str(self.extra.get("directory_id", "") or "")
        self._workflow_step_id: str = str(self.extra.get("workflow_step_id", "") or "")

        self._timeout: float = float(
            self.extra.get("timeout_seconds", DEFAULT_HTTP_TIMEOUT_SECONDS)
        )
        self._retries: int = int(self.extra.get("retries", DEFAULT_HTTP_RETRIES))
        self._retry_interval: float = float(
            self.extra.get("retry_interval_seconds", DEFAULT_HTTP_RETRY_INTERVAL_SECONDS)
        )

        session_factory: Optional[Callable[[], Any]] = self.extra.get("session_factory")
        self._session_factory: Optional[Callable[[], Any]] = (
            session_factory if callable(session_factory) else None
        )

        self._lock = threading.RLock()
        # file_id → { "file_id": str, "storage_id": str, "filename": str }
        self._files: Dict[str, Dict[str, Any]] = {}
        # task_id → 上次得到的 TaskInfo，供后续快速查找
        self._tasks: Dict[str, TaskInfo] = {}

    # ------------------------------------------------------------------
    # HTTP 工作基础
    # ------------------------------------------------------------------
    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        try:
            import requests  # noqa: WPS433 — 局部导入
        except ImportError as exc:  # pragma: no cover
            raise PlatformError(
                "CrowdinPlatform requires 'requests'. Install with "
                "`pip install requests`."
            ) from exc
        return requests.Session()

    def _headers(
        self,
        *,
        content_type: str = "application/json",
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        if not self.api_token:
            raise PlatformError(
                "CrowdinPlatform: api_token is empty. Set GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN "
                "or the ReviewConfig.api_token field."
            )
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        raw_body: Optional[bytes] = None,
        stream: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
        full_url: Optional[str] = None,
    ):
        """发送带鉴权的 HTTP 请求，按需重试。"""
        session = self._session()
        url = full_url or f"{self.api_base}{path}"
        content_type = (
            "application/octet-stream" if raw_body is not None else "application/json"
        )
        headers = self._headers(content_type=content_type, extra=extra_headers)

        last_exc: Optional[BaseException] = None
        for attempt in range(1, self._retries + 1):
            try:
                response = session.request(
                    method.upper(),
                    url,
                    params=params,
                    json=json_body if raw_body is None else None,
                    data=raw_body,
                    headers=headers,
                    timeout=self._timeout,
                    stream=stream,
                )
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 任何传输错误都需重试
                last_exc = exc
                logger.warning(
                    "CrowdinPlatform: %s %s failed on attempt %d/%d: %s",
                    method, path, attempt, self._retries, exc,
                )
                if attempt >= self._retries:
                    break
                _sleep(self._retry_interval)
                continue

            if response.status_code >= 500 or response.status_code == 429:
                logger.warning(
                    "CrowdinPlatform: %s %s got HTTP %d (attempt %d/%d)",
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
                f"CrowdinPlatform: exhausted {self._retries} retries for {method} {path}: {last_exc}"
            ) from last_exc
        raise PlatformError(
            f"CrowdinPlatform: exhausted {self._retries} retries for {method} {path}"
        )

    @staticmethod
    def _raise_for_status(response, path: str) -> None:
        if 200 <= response.status_code < 300:
            return
        body: Any = ""
        try:
            body = response.json()
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            body = getattr(response, "text", "")
        raise PlatformError(
            f"CrowdinPlatform: {path} → HTTP {response.status_code}: {body!r}"
        )

    def _project_id(self) -> str:
        if not self.project_id:
            raise PlatformError("CrowdinPlatform: project_id is empty.")
        return str(self.project_id)

    # ------------------------------------------------------------------
    # 适配器 API
    # ------------------------------------------------------------------
    def upload_source(self, file_path: str, *, remote_path: str = "") -> UploadResult:
        """两步上传：先写入 storage，再挂到项目文件。

        关键细节：
            * 对 ``.xlsx`` 文件，Crowdin 需要显式传 ``type: "xlsx"`` **和**
              ``importOptions.scheme`` 才能把表格解析成一组可翻译的 strings；
              否则 Crowdin 虽然会收下文件，但解析不出任何 string，后续
              :meth:`create_task` 会因 "fileIds not found" 返回 HTTP 400。
            * 本方法默认按仓库约定的 5 列表头（Key / Source / Target /
              Context / Comment）生成 scheme；若上传的是其它格式/其它列顺序，
              可通过构造器 ``extra['file_type']`` 与 ``extra['import_options']``
              整体覆盖。
        """
        filename = os.path.basename(remote_path) or os.path.basename(file_path)
        # requests 库对 HTTP header 默认用 latin-1 编码。Crowdin 的
        # ``Crowdin-API-FileName`` 不接受非 ASCII 字符（中文文件名会直接报
        # ``'latin-1' codec can't encode``），这里专门为 header 构造一个
        # ASCII-safe 版本；而 body 的 ``name`` 字段依然用原始中文名——
        # Crowdin 侧界面显示仍然是用户熟悉的中文。
        header_safe_filename = _to_ascii_filename(filename)

        with open(file_path, "rb") as handle:
            data = handle.read()

        storage_response = self._request(
            "POST",
            "/storages",
            raw_body=data,
            extra_headers={
                "Crowdin-API-FileName": header_safe_filename,
            },
        )
        storage_payload = storage_response.json().get("data", {})
        storage_id = str(storage_payload.get("id", ""))
        if not storage_id:
            raise PlatformError(
                "CrowdinPlatform: /storages response missing data.id"
            )

        body: Dict[str, Any] = {
            "storageId": int(storage_id),
            "name": filename,
        }
        if self._directory_id:
            body["directoryId"] = int(self._directory_id)

        # 根据扩展名（或 extra 覆盖）自动补上 type + importOptions。
        file_type, import_options = self._infer_file_type_and_options(filename)
        if file_type:
            body["type"] = file_type
        if import_options:
            body["importOptions"] = import_options

        file_response = self._request(
            "POST",
            f"/projects/{self._project_id()}/files",
            json_body=body,
        )
        file_payload = file_response.json().get("data", {})
        file_id = str(file_payload.get("id", ""))
        if not file_id:
            raise PlatformError(
                "CrowdinPlatform: files response missing data.id"
            )

        record = {
            "file_id": file_id,
            "storage_id": storage_id,
            "filename": filename,
        }
        with self._lock:
            self._files[file_id] = record

        logger.info(
            "CrowdinPlatform: uploaded %s (fileId=%s, storageId=%s)",
            filename, file_id, storage_id,
        )
        return UploadResult(
            file_id=file_id,
            revision=str(file_payload.get("revisionId", "")),
            extra=record,
        )

    def upload_translations(
        self,
        file_id: str,
        target_locale: str,
        local_xlsx_path: str,
        *,
        auto_approve: bool = False,
        import_eq_suggestions: bool = True,
    ) -> None:
        """把 ``local_xlsx_path`` 中 **Target 列** 的译文作为 "已有翻译" 上传到
        Crowdin，关联到 ``file_id`` 和 ``target_locale``。

        **为什么单独一个接口？**

        Crowdin 的 ``POST /projects/{id}/files``（挂文件）只识别**源串字段**
        （``identifier``/``sourcePhrase``/``context`` …），不会把 Target 列
        作为译文导入——哪怕 scheme 里写了 ``translation``。要让 Crowdin 侧
        同时看到 LLM 预译结果，必须额外调一次
        ``POST /projects/{id}/translations/{languageId}`` 接口，走的也是先
        ``/storages`` 上传文件体、再提交 ``storageId + fileId`` 的两步法。

        调用 Crowdin ``POST /projects/{id}/translations/{languageId}`` 接口
        上传已有译文。默认参数：

        * ``importEqSuggestions=True``——完全相同的源串若已有 TM 命中，
          依然把本次译文作为候选加入；
        * ``autoApproveImported=False``——导入的译文**不自动审核通过**，
          仍需审校员手动点 approve（符合"LLM 预译作为初稿"的工作流语义）；
        * ``translateHidden=False``：不翻译隐藏串；
        * ``addToTm=False``：不入 Crowdin 项目 TM（避免 LLM 结果污染术语库）。

        参数：
            file_id: Crowdin 侧已挂载的源文件 ID（即 :meth:`upload_source` 返回的 ``file_id``）；
            target_locale: Crowdin 语种代码（如 ``"vi"`` / ``"zh-CN"``）；
            local_xlsx_path: 本地 xlsx 路径，必须和挂文件时同一份 xlsx
                （Crowdin 侧按 Key 列对齐，Target 列作为译文）；
            auto_approve: 覆盖默认的 ``autoApproveImported=False``；
            import_eq_suggestions: 覆盖默认的 ``importEqSuggestions=True``。
        """
        filename = os.path.basename(local_xlsx_path)
        header_safe_filename = _to_ascii_filename(filename)

        with open(local_xlsx_path, "rb") as handle:
            data = handle.read()

        storage_response = self._request(
            "POST",
            "/storages",
            raw_body=data,
            extra_headers={"Crowdin-API-FileName": header_safe_filename},
        )
        storage_id = str(storage_response.json().get("data", {}).get("id", ""))
        if not storage_id:
            raise PlatformError(
                "CrowdinPlatform.upload_translations: /storages response missing data.id"
            )

        body: Dict[str, Any] = {
            "storageId": int(storage_id),
            "fileId": int(file_id) if str(file_id).isdigit() else file_id,
            "importEqSuggestions": bool(import_eq_suggestions),
            "autoApproveImported": bool(auto_approve),
            "translateHidden": False,
            "addToTm": False,
        }

        self._request(
            "POST",
            f"/projects/{self._project_id()}/translations/{target_locale}",
            json_body=body,
        )
        logger.info(
            "CrowdinPlatform: uploaded translations for fileId=%s locale=%s "
            "(storageId=%s, auto_approve=%s)",
            file_id, target_locale, storage_id, auto_approve,
        )

    def create_task(
        self,
        file_ids: Sequence[str],
        target_locale: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
        title: str = "",
        description: str = "",
    ) -> TaskInfo:
        if not file_ids:
            raise PlatformError("CrowdinPlatform.create_task: file_ids is empty.")

        body: Dict[str, Any] = {
            "title": title or f"Review {target_locale}",
            "languageId": target_locale,
            # type=0 → 翻译任务（要求至少 1 条 untranslated 字串）；
            # type=1 → 校对任务（要求目标语言已有译文）。
            #
            # 本项目的审校流程为"LLM 已预译 → 人工校对"：先用
            # upload_translations 把 Target 列全量导入 Crowdin，所以目标
            # 语言下 untranslated=0，若用 type=0 会被 Crowdin 以
            # HTTP 409 "Language has no untranslated words" 拒绝。
            # 因此默认选 1（校对）；若调用方确有必要可通过 extra["task_type"]
            # 覆盖。
            "type": 1,
            "fileIds": [int(f) for f in file_ids],
        }
        if description:
            body["description"] = description
        if self._workflow_step_id:
            body["workflowStepId"] = int(self._workflow_step_id)
        # 允许调用方以 extra 中的 ``task_*`` 字段覆盖任务字段。
        for key, value in self.extra.items():
            if key.startswith("task_"):
                body[key[len("task_"):]] = value

        response = self._request(
            "POST",
            f"/projects/{self._project_id()}/tasks",
            json_body=body,
        )
        data = response.json().get("data", {})
        task_id = str(data.get("id", ""))
        remote_status = str(data.get("status", ""))
        info = TaskInfo(
            task_id=task_id,
            status=_map_status(remote_status),
            target_locale=target_locale,
            project_id=self._project_id(),
            review_stage=review_stage,
            percent_completed=float(data.get("progress", {}).get("percent", 0.0)),
            extra={
                "raw_status": remote_status,
                "title": title,
                "description": description,
                "type": data.get("type"),
            },
        )
        with self._lock:
            self._tasks[task_id] = info
        return info

    def get_task_status(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> TaskInfo:
        response = self._request(
            "GET",
            f"/projects/{self._project_id()}/tasks/{task_id}",
        )
        data = response.json().get("data", {})
        remote_status = str(data.get("status", ""))
        percent = float(data.get("progress", {}).get("percent", 0.0))
        # Crowdin GET /tasks/{id} 响应里**语言字段叫 ``targetLanguageId``**
        # （见老项目 crowdin_service.py 第 698/714 行与
        # docs/crowdin_dual_platform_sync.md 第 260 行）。为兼容未来可能
        # 的字段名变更或其它 Crowdin 兼容实现，这里按
        # ``targetLanguageId → languageId`` 的顺序兜底读取；若还为空，
        # 回退到内存里**上次创建**该 task 时持有的 target_locale——而不是
        # 直接设成空串污染后续 translations/exports 调用。
        resolved_locale = (
            str(data.get("targetLanguageId", "") or "")
            or str(data.get("languageId", "") or "")
        )
        if not resolved_locale:
            with self._lock:
                cached = self._tasks.get(task_id)
            if cached is not None and cached.target_locale:
                resolved_locale = cached.target_locale
        info = TaskInfo(
            task_id=task_id,
            status=_map_status(remote_status),
            target_locale=resolved_locale,
            project_id=self._project_id(),
            review_stage=review_stage,
            percent_completed=percent,
            extra={
                "raw_status": remote_status,
                "title": data.get("title", ""),
                # 保留 fileIds，避免 import_approved() 重复拉取。
                "fileIds": list(data.get("fileIds") or []),
            },
        )
        with self._lock:
            self._tasks[task_id] = info
        return info

    def download_translations(
        self,
        file_id: str,
        target_locale: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        # Crowdin：先创建 exports 、再从返回的预签名 URL 下载。
        # 本处采用一步 exports 并直接下载。
        if not target_locale:
            raise PlatformError(
                "CrowdinPlatform.download_translations: target_locale is empty. "
                "This usually means get_task_status() returned a TaskInfo with "
                "empty target_locale (Crowdin task detail missing both "
                "'targetLanguageId' and 'languageId' fields). "
                f"review_stage={review_stage}, file_id={file_id}."
            )
        if not file_id:
            raise PlatformError(
                "CrowdinPlatform.download_translations: file_id is empty."
            )
        # 关键：显式传 ``format="xliff"``。
        # 若不传 format，Crowdin 会按源文件扩展名返回；源文件若为 xlsx，
        # 下游会收到一个 xlsx 包（内含 theme1.xml 等组件），错误挑成员
        # 后被 XliffSource 解析为 0 条 entries，导致 ``split_approved_data``
        # 返回 approved=0/pending=0，内存里的 ``ctx.entries`` 被错误清空。
        #
        # ``skipUntranslatedStrings=False``：pending 条目也要出现在导出
        # 里，不然 ``split_approved_data`` 无法分组。
        response = self._request(
            "POST",
            f"/projects/{self._project_id()}/translations/exports",
            json_body={
                "targetLanguageId": target_locale,
                "fileIds": [int(file_id)] if file_id.isdigit() else [file_id],
                "format": "xliff",
                "skipUntranslatedStrings": False,
            },
        )
        data = response.json().get("data", {})
        url = data.get("url") or ""
        if not url:
            raise PlatformError(
                "CrowdinPlatform: translations/exports response missing data.url"
            )

        # 返回的 URL 为 S3 预签名链接，下载时**不能**带 Authorization 头。
        payload = self._download_binary(url)

        # Crowdin 的 translations/exports 即使只导出一个文件也会把它包进
        # zip 返回（魔数 ``PK\x03\x04``）。此处识别并解压出真实的翻译文件，
        # 否则调用方按 UTF-8 解析 zip 字节流会立刻挂在 ``codec can't decode``。
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        if payload[:4] == b"PK\x03\x04":
            extracted = _unzip_single_translation(payload)
            if extracted is None:
                raise PlatformError(
                    "CrowdinPlatform: downloaded zip contains no translation file"
                )
            with open(dest_path, "wb") as fh:
                fh.write(extracted)
        else:
            with open(dest_path, "wb") as fh:
                fh.write(payload)
        return dest_path

    def _download_binary(self, url: str) -> bytes:
        session = self._session()
        try:
            response = session.request(
                "GET", url, timeout=self._timeout, stream=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise PlatformError(f"CrowdinPlatform: download failed: {exc}") from exc
        if response.status_code >= 400:
            raise PlatformError(
                f"CrowdinPlatform: download HTTP {response.status_code}"
            )
        if hasattr(response, "iter_content"):
            chunks: List[bytes] = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
            return b"".join(chunks)
        return getattr(response, "content", b"")

    def import_approved(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        # 先拿任务元信息拿到 fileIds 与 languageId，再复用 download_translations。
        info = self.get_task_status(task_id, review_stage=review_stage)
        file_ids = info.extra.get("fileIds") or info.extra.get("file_ids") or []
        target_locale = info.target_locale
        # 当汇总信息不足时回退重新拉取原始作为兵。
        if not file_ids:
            response = self._request(
                "GET",
                f"/projects/{self._project_id()}/tasks/{task_id}",
            )
            data = response.json().get("data", {})
            file_ids = data.get("fileIds") or []
            # Crowdin 响应用 targetLanguageId（见 crowdin_dual_platform_sync.md
            # 第 260 行）；languageId 作为降级兼容。
            target_locale = (
                target_locale
                or str(data.get("targetLanguageId", "") or "")
                or str(data.get("languageId", "") or "")
            )
        if not file_ids:
            raise PlatformError(
                f"CrowdinPlatform: cannot resolve fileIds for task {task_id}"
            )
        if not target_locale:
            raise PlatformError(
                f"CrowdinPlatform: cannot resolve target_locale for task {task_id} "
                f"(response missing both 'targetLanguageId' and 'languageId')"
            )
        return self.download_translations(
            str(file_ids[0]), target_locale, dest_path, review_stage=review_stage,
        )

    def export_review_report(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        info = self.get_task_status(task_id, review_stage=review_stage)
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Crowdin review report — taskId={task_id}\n")
            fh.write(f"stage={review_stage}\n")
            fh.write(f"status={info.extra.get('raw_status', '')}\n")
            fh.write(f"percent_completed={info.percent_completed}\n")
            fh.write(f"target_locale={info.target_locale}\n")
            fh.write(f"title={info.extra.get('title', '')}\n")
        return dest_path

    def split_approved_data(
        self,
        task_id: str,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        review_stage: str = ReviewStage.FIRST.value,
    ) -> SplitResult:
        """按条目维度把 ``task_id`` 的译文拆成 **approved** 与 **pending** 两份本地文件。

        按条目维度把 ``task_id`` 的译文拆分成两份本地文件：

        1. 调 :meth:`download_translations` 拿到 Crowdin 导出的 **xliff**；
        2. 解析每个 ``<trans-unit>`` 的 ``approved`` 属性——有值表示已审通过；
        3. 把 approved 对应 key 的条目物化成 ``save_approved_path`` 下的 xlsx；
        4. 其余 key 的条目物化成 ``save_pending_path`` 下的 xlsx（当该参数为空时跳过）。

        返回的 :class:`SplitResult`：

        * ``approved_path`` / ``pending_path``——两份 xlsx 的本地绝对路径（无内容时也会落空表）；
        * ``is_complete``——pending 为 0 时为 ``True``（整单审完）；
        * ``should_continue``——approved 有内容时为 ``True``（下游 merge 有数据可做）；
        * ``extra['approved_keys'] / extra['pending_keys']``——两组 key 列表，
          供工作流 state 直接按 key 拆分 ``ctx.entries``，免二次 I/O。
        """
        # 延迟导入避免 platforms 子包反向依赖 sources/workflow。
        from ..sources import XliffSource, XlsxSource  # noqa: WPS433

        # 1) 下载 xliff（import_approved 已经把 task → fileIds → export URL
        #    这条链封装好；它写入的就是 xliff 二进制）。
        xliff_path = save_approved_path.rsplit(".", 1)[0] + ".source.xliff"
        self.import_approved(task_id, xliff_path, review_stage=review_stage)

        # 2) 解析 xliff → entries（XliffSource 会把 trans-unit 上的
        #    ``approved`` 属性填入 entry.metadata["approved"]）。
        xliff_entries = XliffSource(encoding="utf-8").load(xliff_path)

        # 2.1 空数据保护：如果 xliff 解析出 0 条，一定是下载/格式出了问题
        #     （正常情况下任务里有多少条字串、xliff 里就应有多少 trans-unit）。
        #     此时**不能**悄悄返回 approved=0/pending=0 让上游走"整单审完"
        #     分支——那会把内存里的 ``ctx.entries`` 全部清空，造成"审核结果
        #     凭空消失"。显式抛错，runner 会保留 state_data（含 task_id），
        #     下次运行时（不加 ``--fresh``）会复用同一个 task_id 续跑。
        if not xliff_entries:
            raise PlatformError(
                f"CrowdinPlatform.split_approved_data: parsed 0 entries from "
                f"xliff {xliff_path!r} — the file is probably not a valid "
                f"XLIFF (e.g. Crowdin returned the source xlsx package "
                f"instead). Check the request body to /translations/exports "
                f"includes format='xliff'. task_id={task_id}, "
                f"xliff_size={os.path.getsize(xliff_path) if os.path.exists(xliff_path) else 'missing'}."
            )

        approved_entries = []
        pending_entries = []
        for entry in xliff_entries:
            if entry.metadata.get("approved"):
                approved_entries.append(entry)
            else:
                pending_entries.append(entry)

        is_complete = len(pending_entries) == 0

        # 3) 落两份 xlsx（即使 pending 为 0 或 approved 为 0 也落空表，
        #    保证下游"文件存在"的前置假设稳定）。
        os.makedirs(os.path.dirname(save_approved_path) or ".", exist_ok=True)
        XlsxSource(encoding="utf-8").dump(approved_entries, save_approved_path)

        pending_path_out = ""
        if save_pending_path:
            os.makedirs(os.path.dirname(save_pending_path) or ".", exist_ok=True)
            XlsxSource(encoding="utf-8").dump(pending_entries, save_pending_path)
            pending_path_out = save_pending_path

        info = self.get_task_status(task_id, review_stage=review_stage)
        logger.info(
            "CrowdinPlatform: split task=%s approved=%d pending=%d "
            "(is_complete=%s, raw_status=%s)",
            task_id, len(approved_entries), len(pending_entries),
            is_complete, info.extra.get("raw_status", ""),
        )
        return SplitResult(
            approved_path=save_approved_path,
            pending_path=pending_path_out,
            should_continue=len(approved_entries) > 0,
            is_complete=is_complete,
            extra={
                "raw_status": info.extra.get("raw_status", ""),
                "approved_keys": [e.key for e in approved_entries],
                "pending_keys": [e.key for e in pending_entries],
            },
        )

    def delete_task(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        self._request(
            "DELETE",
            f"/projects/{self._project_id()}/tasks/{task_id}",
        )
        with self._lock:
            self._tasks.pop(task_id, None)

    def delete_file(
        self,
        file_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        """``DELETE /projects/{pid}/files/{file_id}``。

        Crowdin 返回 204 表示删除成功，404 代表远端文件已不存在（上一轮
        已清理 / 用户手工删过），这两种情况都视为幂等成功。其他错误原样
        往上抛，让调用方决定重试策略。
        """
        if not file_id:
            return
        try:
            self._request(
                "DELETE",
                f"/projects/{self._project_id()}/files/{file_id}",
            )
        except PlatformError as exc:
            # 404 直接当作 "已删除"——保证流程幂等（例如上一轮已清、或
            # 测试环境下用户手工在 Crowdin UI 删过）。
            if "HTTP 404" in str(exc):
                logger.info(
                    "CrowdinPlatform: file %s already absent on remote "
                    "(treating 404 as success).",
                    file_id,
                )
            else:
                raise
        with self._lock:
            self._files.pop(file_id, None)
        logger.info("CrowdinPlatform: deleted file %s", file_id)

    def get_project_name(self, project_id: str = "") -> str:
        pid = project_id or self.project_id
        if not pid:
            return ""
        response = self._request("GET", f"/projects/{pid}")
        data = response.json().get("data", {})
        return data.get("name") or str(pid)

    # ------------------------------------------------------------------
    # 文件类型推断
    # ------------------------------------------------------------------
    def _infer_file_type_and_options(
        self, filename: str,
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """按扩展名推断 Crowdin ``file.type`` 和 ``importOptions``。

        xlsx 场景下必须显式告诉 Crowdin 哪一列是 identifier / source /
        translation / context，否则 Crowdin 收下文件但不解析出任何
        string，后续 create_task 会 400。

        用户可通过构造器 ``extra`` 覆盖本方法推断值：

        * ``extra['file_type']``——完全覆盖 ``file.type``；
        * ``extra['import_options']``——完全覆盖 ``importOptions``；
        * ``extra['xlsx_scheme']``——仅在 xlsx 场景下覆盖默认 scheme；
          常用场景：如果你的 xlsx 列顺序和框架不同，可传入
          ``{"identifier": 0, "sourcePhrase": 1, "translation": 2}`` 之类。
        """
        # 用户覆盖具有最高优先级。
        overridden_type = str(self.extra.get("file_type", "") or "")
        overridden_opts = self.extra.get("import_options")

        ext = os.path.splitext(filename)[1].lower()
        if ext == ".xlsx":
            file_type = overridden_type or "xlsx"
            if isinstance(overridden_opts, dict):
                return file_type, dict(overridden_opts)
            # 与 XlsxSource 的 5 列表头一一对应：
            #   列 0 Key | 列 1 Source | 列 2 Target | 列 3 Context | 列 4 Comment
            #
            # Crowdin ``/projects/{id}/files`` 接口要求
            # ``importOptions.scheme`` **同时**声明 ``sourcePhrase`` 和
            # ``translation`` 两列——缺任何一个都会返回：
            #     HTTP 400 schemeInvalid: The file schema must include the
            #     "Source String" and "Translation" elements
            # scheme 里声明 ``translation`` 并**不会**自动把该列作为"已有译文"
            # 导入（那是 ``/projects/{id}/translations/{languageId}`` 接口的
            # 职责——见 :meth:`upload_translations`），scheme 只是 Crowdin
            # 用来识别 xlsx 列结构的元信息。
            default_scheme = {
                "identifier": 0,
                "sourcePhrase": 1,
                "translation": 2,
                "context": 3,
            }
            scheme = self.extra.get("xlsx_scheme")
            if not isinstance(scheme, dict):
                scheme = default_scheme
            import_options: Dict[str, Any] = {
                "firstLineContainsHeader": True,
                "scheme": dict(scheme),
            }
            return file_type, import_options

        if ext == ".csv":
            file_type = overridden_type or "csv"
            if isinstance(overridden_opts, dict):
                return file_type, dict(overridden_opts)
            return file_type, None

        # 对 json / xml / xliff 等，由 Crowdin 自动按扩展名识别。
        return overridden_type, (dict(overridden_opts) if isinstance(overridden_opts, dict) else None)

    # ------------------------------------------------------------------
    # 翻译记忆（TM）回灌
    # ------------------------------------------------------------------
    # 以下 4 个方法为**可选扩展**，不属于 :class:`TranslationPlatform` 基类的
    # 抽象 API——不同平台的 TM 支持能力不一致，state 代码通过
    # ``hasattr(platform, "upload_tm")`` 探测，有则走 TM 回灌，无则告警跳过。
    # 相关端点：
    #   * 拿项目默认 TM：GET  /projects/{id}  → data.defaultTmId
    #   * 清空 TM 片段 ：DELETE /tms/{tm_id}/segments
    #   * 添加 storage ：POST /storages          （与 upload_source 共用）
    #   * 导入 TM 文件 ：POST /tms/{tm_id}/imports
    def get_project_default_tm_id(self) -> str:
        """返回当前项目的默认 TM 库 ID。查不到返回空串，不抛异常。"""
        try:
            res = self._request(
                "GET", f"/projects/{self._project_id()}",
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — TM 操作失败不致命
            logger.warning(
                "CrowdinPlatform.get_project_default_tm_id: GET /projects/%s "
                "failed: %s", self._project_id(), exc,
            )
            return ""
        data = res.json().get("data", {}) if res is not None else {}
        tm_id = data.get("defaultTmId") or data.get("tmId") or ""
        if not tm_id:
            logger.warning(
                "CrowdinPlatform.get_project_default_tm_id: project %s has no "
                "defaultTmId configured", self._project_id(),
            )
        return str(tm_id)

    def clear_tm_segments(self, tm_id: str) -> bool:
        """清空指定 TM 库下的所有片段。成功返回 True，失败返回 False（不抛）。

        调 ``DELETE /tms/{tm_id}/segments``；预期 204。
        """
        if not tm_id:
            return False
        try:
            self._request("DELETE", f"/tms/{tm_id}/segments")
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "CrowdinPlatform.clear_tm_segments: DELETE /tms/%s/segments "
                "failed: %s", tm_id, exc,
            )
            return False
        logger.info("CrowdinPlatform: cleared TM segments for tm_id=%s", tm_id)
        return True

    def _resolve_tm_source_locale(self, tm_id: str) -> str:
        """从 TM 库本身的配置里拿**源语 locale**。

        **为何不从项目取**：Crowdin TM 库和项目是**独立实体**，TM 库自己有
        ``languageId`` + ``languageIds`` 字段登记"这个库里存了哪些语种的
        翻译"，TM import 的 ``scheme`` 字段必须用 **TM 库登记的 locale 码**
        （见 ``GET /tms/{id}`` 返回的 ``languageIds``），而不是项目的
        ``targetLanguages[].locale``——两者可能不一致（例如项目配置的
        ``vi-VN``，TM 库里登记的是 ``vi``）。

        实现方式：

        1. ``GET /tms/{tm_id}`` 返回 ``data.languageId``（主源语）；
        2. 取不到就回退到 ``"zh-CN"``（当前新项目的默认源语）。

        参数：
            tm_id: TM 库 ID。

        返回：
            源语 locale 字符串（如 ``"zh-CN"``）。
        """
        default_source = "zh-CN"
        if not tm_id:
            return default_source
        try:
            res = self._request("GET", f"/tms/{tm_id}")
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "CrowdinPlatform._resolve_tm_source_locale: GET /tms/%s "
                "failed: %s — fallback to %r", tm_id, exc, default_source,
            )
            return default_source
        data = res.json().get("data", {}) if res is not None else {}
        src = str(data.get("languageId") or "").strip()
        if not src:
            logger.warning(
                "CrowdinPlatform._resolve_tm_source_locale: TM %s has no "
                "languageId — fallback to %r", tm_id, default_source,
            )
            return default_source
        logger.info(
            "CrowdinPlatform._resolve_tm_source_locale: tm_id=%s source=%r",
            tm_id, src,
        )
        return src

    def upload_tm(self, tm_file_path: str, *, target_locale: str, tm_id: str = "") -> bool:
        """把本地 TM xlsx 上传到 Crowdin 项目默认 TM 库（**先传后清**）。

        流程：
          1. 若 ``tm_id`` 为空，自动调用 :meth:`get_project_default_tm_id` 获取；
          2. 调用 :meth:`_resolve_tm_source_locale` 从 TM 库的 ``languageId``
             字段取源语 locale（如 ``"zh-CN"``）；
          3. ``POST /storages`` 上传 xlsx 文件体；
          4. ``POST /tms/{tm_id}/imports`` 触发 TM 导入；
          5. **import 成功**后再调 :meth:`clear_tm_segments` 清空旧片段。

        **"先传后清"的意义**：
            若 import 失败（例如 scheme 校验失败），TM 会保持原样，而不是
            留下清空后的空壳。Crowdin TM import 对同源同译对会 upsert，
            不会无限膨胀。

        **scheme 字段约定**：
            scheme 的 **key 必须严格使用 TM 库 ``languageIds`` 里登记的
            locale 码**（例如 ``{"zh-CN": 0, "vi": 1}``），不能用：

            - 字面占位符（``"sourcePhrase"``）→ 400 scheme not valid
            - 项目的 ``targetLanguages[].locale``（``"vi-VN"``）→ 400 scheme not valid
            - 任何 TM 库 ``languageIds`` 之外的 locale 码 → 400

            value 是文件里的列号，列顺序对齐 :mod:`utils.tm_file_builder`
            实际写入格式：列 0 = 源语文本、列 1 = 目标语文本。

        参数：
            tm_file_path: 由 :mod:`utils.tm_file_builder` 产出的两列 xlsx
                （列 0 = 源语文本，列 1 = 目标语文本）。
            target_locale: Crowdin TM 库 ``languageIds`` 里登记的目标语 locale
                码（如 ``"vi"``）。调用方传入的就是项目 ``targetLanguageId``，
                和 TM 库登记码天然一致，这里**不做任何转换**。
            tm_id: 可选，直接指定 TM 库 ID；为空则取项目默认 TM。

        返回：
            全链路成功返回 True；任一步失败均返回 False 并记日志，不抛异常。
        """
        import os as _os

        if not _os.path.exists(tm_file_path):
            logger.warning(
                "CrowdinPlatform.upload_tm: file not found: %s", tm_file_path,
            )
            return False

        tm_id = tm_id or self.get_project_default_tm_id()
        if not tm_id:
            return False

        # 从 TM 库自己的 languageId 取源语 locale（如 "zh-CN"）
        source_locale = self._resolve_tm_source_locale(tm_id)

        filename = _os.path.basename(tm_file_path)
        header_safe_filename = _to_ascii_filename(filename)

        try:
            with open(tm_file_path, "rb") as fh:
                data = fh.read()
            storage_response = self._request(
                "POST",
                "/storages",
                raw_body=data,
                extra_headers={"Crowdin-API-FileName": header_safe_filename},
            )
            storage_id = str(storage_response.json().get("data", {}).get("id", ""))
            if not storage_id:
                logger.warning(
                    "CrowdinPlatform.upload_tm: /storages response missing data.id",
                )
                return False

            # scheme 字段：key 必须是 TM 库 languageIds 里登记的 locale 码。
            # - 源语 key = TM 库的 data.languageId（已由 _resolve_tm_source_locale 取好）
            # - 目标语 key = 调用方传入的 target_locale（天然对齐 TM 库）
            # 列号对齐 tm_file_builder 实际写入：列 0 = 源语、列 1 = 目标语。
            body: Dict[str, Any] = {
                "storageId": int(storage_id),
                "firstLineContainsHeader": True,
                "scheme": {
                    source_locale: 0,
                    target_locale: 1,
                },
            }
            self._request(
                "POST",
                f"/tms/{tm_id}/imports",
                json_body=body,
            )
            # import 成功后才清空旧 segments（先传后清）：
            # 若 import 失败走到下面 except，这里不会执行——TM 保持原样。
            self.clear_tm_segments(tm_id)
            logger.info(
                "CrowdinPlatform.upload_tm: imported TM into tm_id=%s "
                "(file=%s, scheme=%s→%s)",
                tm_id, filename, source_locale, target_locale,
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — TM 回灌失败不阻塞主流程
            logger.warning(
                "CrowdinPlatform.upload_tm: failed to import TM to tm_id=%s "
                "(file=%s): %s", tm_id, filename, exc,
            )
            return False


def _sleep(seconds: float) -> None:
    import time as _time
    _time.sleep(max(0.0, seconds))


def _unzip_single_translation(payload: bytes) -> Optional[bytes]:
    """从 Crowdin 导出的 zip payload 里抽出真实的翻译文件内容。

    Crowdin 的 ``/translations/exports`` 下载是一个 zip 包；即使只有一个
    文件也会被 zip 封装。本函数：

    * 只取 ``.xliff`` / ``.xlf`` 结尾的成员（我们在
      :meth:`CrowdinPlatform.download_translations` 显式传了
      ``format="xliff"``，所以 zip 里必然有且仅有 xliff 成员）；
    * 若 zip 里**没有**任何 ``.xliff`` 成员——通常意味着 Crowdin 把源文件
      格式（xlsx 等）直接整包返回了（xlsx 本身就是 zip，内含
      ``theme1.xml`` / ``sharedStrings.xml`` 等组件）——**不要**回退到
      "挑第一个成员"，那样会把 xlsx 的 Office Theme XML 当成 xliff，
      导致 :class:`XliffSource` 解析 0 条、下游 ``split_approved_data``
      误判为"空审核"从而擦掉内存里的 ``ctx.entries``。直接返回 ``None``
      让上游显式报错；
    * 空压缩包同样返回 ``None``。
    """
    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        return None

    try:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            return None
        xliff = next(
            (m for m in members if m.lower().endswith((".xliff", ".xlf"))),
            None,
        )
        if xliff is None:
            # 关键兜底：zip 里没有 xliff 成员——不再 fallback 到 members[0]，
            # 避免把 xlsx 内部组件（theme1.xml 等）错当翻译结果。
            logger.warning(
                "CrowdinPlatform: downloaded zip contains no .xliff/.xlf "
                "member (found %d members: %s). This usually means "
                "/translations/exports did not include format='xliff' in the "
                "request body — refusing to pick a random member.",
                len(members),
                members[:5],
            )
            return None
        return zf.read(xliff)
    finally:
        zf.close()


def _to_ascii_filename(filename: str) -> str:
    """把一个可能含中文的文件名转为 ASCII-only 版本，保留扩展名。

    用途：Crowdin 的 ``Crowdin-API-FileName`` HTTP header 不接受非 ASCII
    字符（``requests`` 库默认用 latin-1 编码 header）。本函数策略：

    * 完整文件名已是 ASCII → 原样返回；
    * 否则 stem/扩展名分别做 URL 百分号编码（``%E7%AC%AC...``）；
      Crowdin 服务器端会按百分号解码得到原始中文。
    """
    try:
        filename.encode("latin-1")
        return filename
    except UnicodeEncodeError:
        pass

    from urllib.parse import quote

    stem, dot, ext = filename.rpartition(".")
    if not dot:
        return quote(filename, safe="")
    return f"{quote(stem, safe='')}.{quote(ext, safe='')}"


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
register_platform("crowdin", CrowdinPlatform)


__all__ = ["CrowdinPlatform"]
