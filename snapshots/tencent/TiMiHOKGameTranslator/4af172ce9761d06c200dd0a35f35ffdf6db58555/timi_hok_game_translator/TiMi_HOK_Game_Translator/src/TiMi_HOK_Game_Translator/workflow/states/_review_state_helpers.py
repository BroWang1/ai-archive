""":mod:`light_review_state` 、 :mod:`first_review_state` 与
:mod:`second_review_state` 共享的辅助。

三个审校状态骨架一致：

1. 为对应 :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage` 解析出平台；
2. **以批次为单位**把当前条目写成 **xlsx**（审校平台通用，Crowdin / Phrase
   都能解析——相比直接上传 dtxml / xml 等源文件格式，xlsx 的字段级 UI
   质量显著更好）；
3. 上传并在平台上创建审校任务；
4. 将任务 id、批次目录、上传文件 id 写入
   :attr:`WorkflowContext.state_data`，方便重启续跑；
5. **轮询** :meth:`TranslationPlatform.get_task_status` 直到 Crowdin 侧审校任务
   完成（``TaskStatus.APPROVED``）或达到 :attr:`ReviewConfig.stop_time`
   截止时间；
6. 把平台导出的译文（xliff）解析回 :attr:`WorkflowContext.entries`，
   供后续 ``validate_data`` / ``dtxml_merge`` / ``push_vcs`` 消费。

轮询策略
--------
* 间隔：:attr:`ReviewConfig.poll_interval_seconds`，默认
  :const:`DEFAULT_REVIEW_POLL_INTERVAL_SECONDS` 秒；
* 截止：:attr:`ReviewConfig.stop_time`（``"HH:MM"``，本地时区；为空代表
  **不设截止、一直轮询**，适合夜间作业或长任务场景）；
* 未完成即到达截止 → 抛 :class:`PlatformError`，runner 把当前 state
  保留为"未完成"；下次 ``python main.py run --language vi``（**不要
  --fresh**）会继续轮询同一个 ``task_id``（state_data 中已持久化）。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ...commons import DEFAULT_REVIEW_POLL_INTERVAL_SECONDS, PlatformError
from ...platforms._batch import build_batch_name, stage_dir, stage_file_stem
from ...platforms.base import TaskStatus
from ...platforms.factory import build_review_tool
from ...sources import XliffSource, XlsxSource
from .._tail_tasks import TailTaskStore
from ..state import WorkflowContext

logger = logging.getLogger(__name__)

#: 上传到平台的中间文件格式。Crowdin / Phrase 等都原生识别 xlsx。
_UPLOAD_FORMAT = "xlsx"


def _build_platform_url(platform_name: str, project_id: str) -> str:
    """根据平台名 + project_id 拼出该项目在平台 Web UI 上的入口 URL。

    不同平台 URL 规则：
    * Phrase TMS：``https://cloud.memsource.com/web/project2/show/<projectUid>``
      （EU/US 账户 UI 共用 memsource 主域；``region`` 字段仅影响 IDM 鉴权）；
    * Crowdin：``https://crowdin.com/project/<projectId>/tasks``
      （数字 project_id 会被 302 到 identifier；直接跳到任务列表页更有用）；
    * 其他平台 / 未配置 ID：返回空串，调用方应回落到裸文本。

    通知消息里直接把该 URL 作为"项目入口"链接展示，审核人员一键跳转，
    无需在正文里罗列 ``project_id`` / ``task_id`` 这类对人阅读无直接价值的裸 ID。
    """
    if not project_id:
        return ""
    name = (platform_name or "").lower()
    if name == "phrase":
        return f"https://cloud.memsource.com/web/project2/show/{project_id}"
    if name == "crowdin":
        return f"https://crowdin.com/project/{project_id}/tasks"
    return ""

#: 平台导出译文的格式。Crowdin 默认导出 XLIFF 1.2。
_EXPORT_FORMAT = "xliff"


def _resolve_lang(ctx: WorkflowContext) -> str:
    """从 :class:`WorkflowContext` 解析语种标识，用于按语种分区的落盘路径。

    优先级与 :class:`WorkflowRunner` 的分区规则保持一致：

    * ``ctx.language_profile.id`` 非空 → 用 profile id（和
      ``conf/languages/<lang>.json`` 文件名一致，稳定）；
    * 否则 ``ctx.config.target_locale`` → 退回 config 顶层语种码；
    * 都为空 → 空串（``TailTaskStore`` 会向后兼容地落到 ``workspace`` 根）。

    保持为"**共享 helper**"而非 Runner 的方法，是因为 state 层拿不到 Runner
    实例；由 ctx 推导是最 cheap 的方式。
    """
    profile = getattr(ctx, "language_profile", None)
    if profile is not None:
        pid = (getattr(profile, "id", "") or "").strip()
        if pid:
            return pid
    cfg = getattr(ctx, "config", None)
    if cfg is not None:
        tl = (getattr(cfg, "target_locale", "") or "").strip()
        if tl:
            return tl
    return ""


def run_review_stage(
    ctx: WorkflowContext,
    *,
    review_stage: str,
    resume_key_prefix: str,
) -> Optional[str]:
    """执行一个审校阶段。

    成功时返回 ``None``（runner 会自然推进到下一个状态）。

    参数：
        ctx: 工作流上下文。
        review_stage: :class:`ReviewStage` 之一。
        resume_key_prefix: 写入 :attr:`WorkflowContext.state_data` 时的 key 前缀（
            一般为 ``"first_review"`` / ``"second_review"`` / ``"light_review"``）。
    """
    profile = ctx.language_profile
    review_cfg = profile.review(review_stage) if profile else None
    target_locale = (
        (profile.target_locale if profile else "")
        or ctx.config.target_locale
    )

    platform = build_review_tool(
        profile if profile is not None else _synthetic_profile(ctx),
        review_stage,
        global_platform=ctx.config.platform,
    )

    # ------------------------------------------------------------------
    # 2026-10-09 方案 ①-🅱 + 方案 ②：二审入口的"昨日跨阶段条目"注入。
    #
    # 当前阶段是 second_review 时，有**两类昨日遗留条目**要在打包前
    # prepend 到 ctx.entries ——它们都已经过了昨日的一审，不应该回头
    # 重走今日 first_review：
    #
    #   A) ``last_review.second_only_entries``（方案 ② 新增）
    #      ← 由 ``LastMergeDataState`` 从一审遗留 approved 路由过来；
    #        昨日一审通过、但二审尚未开始/完成。
    #
    #   B) ``last_second_review.pending_rollover_entries``（方案 ①-🅱）
    #      ← 由 ``LastSecondReviewState`` 从二审遗留 pending 直接填充；
    #        昨日一审通过、二审到 deadline 时仍未审完的那部分。
    #
    # 为什么注入点在"空 entries 检查"之前？
    #   如果今天 pull_vcs 没有新增条目、first_review 也没产出 approved，
    #   但有上述两类昨日遗留 → ctx.entries 为空、existing_task_id 为空
    #   → 原来会被"空 entries 优雅跳过"分支消化掉 → 条目丢失。
    #   注入在前，让 ctx.entries 先补齐，就能走正常流程。
    # ------------------------------------------------------------------
    if review_stage == "second":
        _SECOND_ONLY_ENTRIES_KEY = "last_review.second_only_entries"  # pylint: disable=invalid-name
        _SECOND_PENDING_ROLLOVER_KEY = "last_second_review.pending_rollover_entries"  # pylint: disable=invalid-name

        second_only_raw = ctx.state_payload.get(_SECOND_ONLY_ENTRIES_KEY) or []
        pending_rollover_raw = ctx.state_payload.get(_SECOND_PENDING_ROLLOVER_KEY) or []

        combined_raw = list(second_only_raw) + list(pending_rollover_raw)
        if combined_raw:
            from ...sources.base import Entry  # noqa: WPS433 — 局部导入避免循环

            # 反序列化为 Entry 列表。
            rolled: list = []
            for raw in combined_raw:
                if not isinstance(raw, dict):
                    continue
                try:
                    rolled.append(
                        Entry(
                            key=str(raw.get("key", "")),
                            source_text=str(raw.get("source_text", "") or ""),
                            target_text=str(raw.get("target_text", "") or ""),
                            context=str(raw.get("context", "") or ""),
                            comment=str(raw.get("comment", "") or ""),
                            metadata=dict(raw.get("metadata") or {}),
                        )
                    )
                except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                    logger.warning(
                        "review[second]: skip malformed yesterday rollover item: %s",
                        exc,
                    )

            if rolled:
                # 【Rule 2b 精确版】对每条昨日条目做 key 冲突判定：
                #   * key 不冲突 → prepend 到 ctx.entries 头部；
                #   * key 冲突 + source 相同 → **原地替换** ctx.entries
                #     里对应的今日版本（保留昨日 target_text 和审员进度）；
                #   * key 冲突 + source 不同 → WARN 并丢弃昨日版本；
                #   * 通道间同 key 冲突（second_only 和 pending_rollover 撞）
                #     → 丢弃（防御性，正常不发生）。
                today_by_key = {e.key: e for e in ctx.entries}
                today_entries_mutable: list = list(ctx.entries)
                today_index_by_key = {e.key: i for i, e in enumerate(today_entries_mutable)}
                seen_in_rolled: set = set()

                prepend_entries: list = []
                replaced_in_today = 0
                dropped_diff_source = 0
                dropped_cross_channel = 0

                for e in rolled:
                    if e.key in seen_in_rolled:
                        # 通道内两条相同 key —— 保守丢第二条。
                        dropped_cross_channel += 1
                        continue
                    seen_in_rolled.add(e.key)

                    if e.key not in today_by_key:
                        prepend_entries.append(e)
                        continue

                    today_version = today_by_key[e.key]
                    if today_version.source_text == e.source_text:
                        # 保留昨日版本——它承载审员进度。
                        idx = today_index_by_key[e.key]
                        today_entries_mutable[idx] = e
                        today_by_key[e.key] = e
                        replaced_in_today += 1
                    else:
                        logger.warning(
                            "review[second]: dropping yesterday entry key=%r "
                            "because today has the same key with a DIFFERENT "
                            "source (today's version wins).",
                            e.key,
                        )
                        dropped_diff_source += 1

                before = len(ctx.entries)
                ctx.entries = prepend_entries + today_entries_mutable
                logger.info(
                    "review[second]: injected yesterday-rollover: new=%d, "
                    "replaced_in_today=%d (same source), dropped_diff_source=%d, "
                    "dropped_cross_channel=%d. "
                    "ctx.entries: %d → %d. "
                    "(sources: second_only=%d, second_pending=%d) "
                    "— these skip first_review and go directly into today's "
                    "second review task.",
                    len(prepend_entries), replaced_in_today, dropped_diff_source,
                    dropped_cross_channel, before, len(ctx.entries),
                    len(second_only_raw), len(pending_rollover_raw),
                )

            # 清空通道，防止下次 run 重复注入。
            ctx.state_payload.pop(_SECOND_ONLY_ENTRIES_KEY, None)
            ctx.state_payload.pop(_SECOND_PENDING_ROLLOVER_KEY, None)

    # ------------------------------------------------------------------
    # 空 entries 的处理策略：
    #
    # 1) 没有续跑 task_id 且 entries 为 0 → 当天没有新增需要翻译的条目
    #    （pull_vcs 加载到 0 条，或 translate 全部失败被过滤）。此时**优雅跳过**
    #    本审校阶段：不建 Crowdin 任务、不写批次目录，直接返回 None 让 runner
    #    推进到下一个 state。后续 process_pending（若已启用）会继续处理昨日遗留。
    #
    # 2) 有续跑 task_id 但 entries 为 0 → 这是上一轮 run 已经把条目消费掉、
    #    现在只是来拉 xliff 回写的"续跑场景"，不是异常。继续原路径即可
    #    （下面 if not task_id 分支会被自动跳过，直接走轮询 + xliff 回写）。
    # ------------------------------------------------------------------
    existing_task_id = ctx.state_data.get(f"{resume_key_prefix}.task_id", "") or ""
    if not ctx.entries and not existing_task_id:
        logger.info(
            "review[%s]: ctx.entries is empty and no resumable task_id — "
            "nothing to review this round, skipping.",
            review_stage,
        )
        return None

    # 0. 解析/创建批次。整个 WorkflowContext 共享一个 batch_name，
    #    first/second review 两次会落到同一个批次目录的不同子目录下。
    batch_name = _resolve_batch_name(ctx, target_locale)
    stage_root = stage_dir(Path(ctx.workspace), batch_name, review_stage)
    stem = stage_file_stem(batch_name, review_stage)
    upload_path = stage_root / f"{stem}.{_UPLOAD_FORMAT}"
    export_path = stage_root / f"{stem}.{_EXPORT_FORMAT}"
    meta_path = stage_root / f"{review_stage}.meta.json"

    # resume key 预声明，供后续各步骤复用。
    file_id_key = f"{resume_key_prefix}.file_id"
    task_id_key = f"{resume_key_prefix}.task_id"
    batch_key = f"{resume_key_prefix}.batch_name"
    upload_key = f"{resume_key_prefix}.upload_path"
    export_key = f"{resume_key_prefix}.export_path"

    task_id: str = ctx.state_data.get(task_id_key, "") or ""
    is_resume = bool(task_id)

    if not task_id:
        # 1. 把当前 entries 写成 xlsx（审校平台通用）。
        XlsxSource(encoding=ctx.config.source.encoding or "utf-8").dump(
            ctx.entries, str(upload_path)
        )
        logger.info(
            "review[%s]: wrote xlsx %s (%d entries)",
            review_stage, upload_path, len(ctx.entries),
        )

        # 2. 上传 + 创建任务。
        upload = platform.upload_source(str(upload_path), remote_path=upload_path.name)
        ctx.state_data[file_id_key] = upload.file_id
        ctx.state_data[batch_key] = batch_name
        ctx.state_data[upload_key] = str(upload_path)

        # 2.1 把 Target 列的 LLM 预译作为"已有翻译"上传到 Crowdin。
        #     Crowdin ``/files`` 挂载只接受源串；要让 Crowdin 侧看到预译文，
        #     必须再调一次 ``/translations/{languageId}`` 接口。
        #     平台如果没实现该方法则跳过。
        _upload_translations_if_supported(
            platform=platform,
            file_id=upload.file_id,
            target_locale=target_locale,
            xlsx_path=upload_path,
            review_stage=review_stage,
        )

        task = platform.create_task(
            [upload.file_id],
            target_locale,
            review_stage=review_stage,
            title=(
                (review_cfg.project_name if review_cfg else "")
                or f"{ctx.config.project_code} — {review_stage} — {batch_name}"
            ),
        )
        task_id = task.task_id
        ctx.state_data[task_id_key] = task_id
        logger.info(
            "review[%s]: created task_id=%s on platform=%s (batch=%s)",
            review_stage, task_id, platform.platform_name, batch_name,
        )
        # 任务创建通知（中文、含关键信息）
        stage_cn = {
            "light": "轻量审校",
            "first": "一审",
            "second": "二审",
        }.get(review_stage, review_stage)
        upload_filename = upload_path.name
        platform_url = _build_platform_url(platform.platform_name, platform.project_id)
        entry_line = (
            f"平台入口：{platform_url}" if platform_url
            else f"平台：{platform.platform_name}（project_id={platform.project_id}）"
        )
        _notify(
            ctx,
            review_stage,
            f"📢 【{ctx.config.project_code}】{stage_cn}任务已创建\n"
            f"目标语种：{target_locale}\n"
            f"{entry_line}\n"
            f"批次名：{batch_name}\n"
            f"上传文件：{upload_filename}\n"
            f"条目数：{len(ctx.entries)}\n"
            f"请及时登录平台处理。",
        )
    else:
        logger.info(
            "review[%s]: resuming with existing task_id=%s (batch=%s)",
            review_stage, task_id, batch_name,
        )

    # 3. 写一份人类可读的批次元信息（便于后续排错 / 定位 Crowdin 任务）。
    _write_meta(
        meta_path,
        {
            "review_stage": review_stage,
            "batch_name": batch_name,
            "project_id": platform.project_id,
            "platform": platform.platform_name,
            "task_id": task_id,
            "file_id": ctx.state_data.get(file_id_key, ""),
            "upload_path": str(upload_path),
            "export_path": str(export_path),
            "target_locale": target_locale,
            "entry_count": len(ctx.entries),
            "resumed": is_resume,
        },
    )

    # 4. 轮询等待 Crowdin 侧审校完成。
    poll_interval = _resolve_poll_interval(review_cfg)
    # 【task 创建后立即计算 deadline】——相对格式（如 "+3m"）的起点就是
    # 这里的 ``datetime.now()``（即"task 刚建好的时刻"），符合"审员从
    # 接到任务起 N 分钟内审完"的现实语义。续跑场景（is_resume=True）
    # 已有 task_id 的时候 now 也是本轮进入 review state 的时刻——相对
    # deadline 本就是"从本次 run 开始算 N 分钟"的测试友好设定，续跑时也
    # 自然给审员新的 N 分钟窗口，不会立刻超时。
    deadline = _resolve_deadline(review_cfg, reference_time=datetime.now())
    logger.info(
        "review[%s]: polling task_id=%s every %ds until %s",
        review_stage,
        task_id,
        poll_interval,
        deadline.isoformat(timespec="seconds") if deadline else "<no deadline>",
    )
    final_info, hit_deadline = _poll_until_done_or_deadline(
        platform=platform,
        task_id=task_id,
        review_stage=review_stage,
        poll_interval_seconds=poll_interval,
        deadline=deadline,
        ctx=ctx,
    )

    # 5. 【条目级拆分】把本任务已 approved 的部分回写到 ctx.entries；
    #    未 approved 的部分**立即在同一天建新尾巴 task**（审校员次日继续审），
    #    并把新 task_id 持久化到跨批次的 ``workspace/last_tasks.json``。
    approved_xlsx = stage_root / f"{stem}_approved.xlsx"
    pending_xlsx = stage_root / f"{stem}_pending.xlsx"
    split = platform.split_approved_data(
        task_id,
        save_approved_path=str(approved_xlsx),
        save_pending_path=str(pending_xlsx),
        review_stage=review_stage,
    )
    logger.info(
        "review[%s]: split task_id=%s → approved=%d, pending=%d (is_complete=%s)",
        review_stage, task_id,
        len(split.extra.get("approved_keys", [])),
        len(split.extra.get("pending_keys", [])),
        split.is_complete,
    )

    # 5.1 approved 条目回写到 ctx.entries；pending 条目在当前 ctx.entries 中被
    #     清除，这样下游 validate_data / dtxml_merge / push_vcs 只处理已审部分。
    _apply_split_to_entries(ctx, approved_xlsx, split)

    # 5.2 pending 非空 → 建新尾巴 task，持久化到 last_tasks.json。
    tail_store = TailTaskStore(Path(ctx.workspace), lang=_resolve_lang(ctx))
    pending_keys = split.extra.get("pending_keys", []) or []
    if pending_keys:
        _create_tail_task(
            ctx=ctx,
            platform=platform,
            review_stage=review_stage,
            target_locale=target_locale,
            batch_name=batch_name,
            pending_xlsx_path=pending_xlsx,
            pending_count=len(pending_keys),
            tail_store=tail_store,
            review_cfg=review_cfg,
            hit_deadline=hit_deadline,
        )
    else:
        # 整单审完 → 清空该阶段的历史尾巴（如果上一天还留着就一起清掉，
        # 防止被 last_*_review state 误读为新尾巴）。
        tail_store.clear(review_stage)

    # 5.3 删除旧 task（Crowdin 侧已经把内容分到 approved_xlsx + 新尾巴 task，
    #     旧 task 保留会污染 Crowdin 项目列表）。
    try:
        platform.delete_task(task_id, review_stage=review_stage)
        logger.info(
            "review[%s]: deleted original task_id=%s on platform=%s "
            "(contents split into approved=%d + new tail task)",
            review_stage,
            task_id,
            platform.platform_name,
            len(split.extra.get("approved_keys", [])),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "review[%s]: delete_task(%s) failed (continuing): %s",
            review_stage, task_id, exc,
        )

    # 5.3.1 删除旧 task 关联的 file。task 已走到"条目拆分 + 建新尾巴"阶段，
    #       原始上传的 xlsx 对后续轮次没有价值；不清掉会在 Crowdin 项目
    #       侧堆积（2026-10-09 实测确认缺这一步会残留文件）。
    old_file_id = str(ctx.state_data.get(file_id_key, "") or "")
    if old_file_id:
        try:
            platform.delete_file(old_file_id, review_stage=review_stage)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "review[%s]: delete_file(%s) failed (continuing): %s",
                review_stage, old_file_id, exc,
            )

    # 5.4 保留 xliff 导出路径到 state_data，便于排错回溯。
    ctx.state_data[export_key] = str(export_path)

    # 6. 完成通知。
    stage_cn = {
        "light": "轻量审校",
        "first": "一审",
        "second": "二审",
    }.get(review_stage, review_stage)
    if split.is_complete:
        status_text = "✅ 全部通过"
    else:
        status_text = f"⚠️ 部分通过（{len(pending_keys)} 条未完成，已滚入次日续审任务）"
    platform_url = _build_platform_url(platform.platform_name, platform.project_id)
    entry_line = (
        f"平台入口：{platform_url}" if platform_url
        else f"平台：{platform.platform_name}（project_id={platform.project_id}）"
    )
    _notify(
        ctx,
        review_stage,
        f"🏁 【{ctx.config.project_code}】{stage_cn}已结束\n"
        f"目标语种：{target_locale}\n"
        f"{entry_line}\n"
        f"批次名：{batch_name}\n"
        f"完成进度：{final_info.percent_completed:.1f}%\n"
        f"结果：{status_text}",
    )

    return None


def _resolve_poll_interval(review_cfg: Any) -> int:
    """按优先级解析本阶段的轮询间隔秒数。"""
    if review_cfg is not None:
        configured = int(getattr(review_cfg, "poll_interval_seconds", 0) or 0)
        if configured > 0:
            return configured
    return DEFAULT_REVIEW_POLL_INTERVAL_SECONDS


def _resolve_deadline(
    review_cfg: Any,
    *,
    reference_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """把 ``stop_time`` 解析为**绝对**的截止时刻。

    支持两种格式：

    1. **绝对时刻** ``"HH:MM"`` —— 生产语义，"审员今日的审校截止时间"：
       * 空串或未配置 → 返回 ``None``（不设截止，一直轮询到任务完成）；
       * 解析成功 → 返回**今天**同时区下的绝对时刻；
       * 若该时刻**已经早于当前时间**（例如今天 15:15 启动 run，而
         ``stop_time=15:10``），**不**顺延到明天——原样返回"今天的
         HH:MM"。调用方 :func:`_poll_until_done_or_deadline` 第一次 poll
         就会发现 ``now >= deadline`` → 直接走 ``split_approved_data``
         分支，让明天的 ``last_*_review`` state 接手；
    2. **相对偏移** ``"+Nm"`` / ``"+Nh"`` / ``"+N"`` —— 测试语义，
       "距离本次计算的参考时刻（``reference_time``，默认 ``datetime.now()``）
       向后 N 分钟/小时/分钟"：
       * ``"+3m"`` → reference_time + 3 分钟；
       * ``"+2h"`` → reference_time + 2 小时；
       * ``"+5"``  → 等价于 ``"+5m"`` （默认分钟）；
       * 这个格式便于测试时不手动改时间戳；上线前记得改回绝对 ``HH:MM``。

    格式错误 → 记一次 warning 后退化为"不设截止"。

    参数：
        review_cfg: 当前阶段的 :class:`ReviewConfig`（可能为 ``None``）；
        reference_time: 解析相对格式时的"起点"。调用方应该在 **task 创建
            成功之后**立即传入 ``datetime.now()``，这样相对偏移反映
            "审员从接到任务起 N 分钟"的真实窗口。默认 ``None`` → 用
            ``datetime.now()`` 的即时值。
    """
    if review_cfg is None:
        return None
    stop_time = (getattr(review_cfg, "stop_time", "") or "").strip()
    if not stop_time:
        return None

    ref = reference_time or datetime.now()

    # 相对格式：+Nm / +Nh / +N
    if stop_time.startswith("+"):
        return _parse_relative_deadline(stop_time, ref)

    # 绝对格式：HH:MM
    try:
        hh, mm = stop_time.split(":", 1)
        hour = int(hh)
        minute = int(mm)
    except (ValueError, AttributeError):
        logger.warning(
            "review: invalid stop_time %r (expected 'HH:MM' or '+Nm'/'+Nh'); "
            "ignoring deadline.",
            stop_time,
        )
        return None
    now = datetime.now()
    deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if deadline <= now:
        # 今日 HH:MM 已过：**不**顺延到明天，让轮询循环第一次就触发 deadline 分支。
        logger.info(
            "review: stop_time %s is already in the past (now=%s) — "
            "deadline will fire on the first poll attempt.",
            stop_time, now.strftime("%H:%M:%S"),
        )
    return deadline


def _parse_relative_deadline(stop_time: str, reference_time: datetime) -> Optional[datetime]:
    """解析 ``"+Nm"`` / ``"+Nh"`` / ``"+N"`` 相对偏移。

    返回 ``reference_time + 偏移``；格式非法时记 warning 并返回 ``None``。

    支持单位：
        * ``m`` / ``min`` / ``mins`` —— 分钟
        * ``h`` / ``hr`` / ``hrs``  —— 小时
        * 省略单位 —— 默认分钟

    示例::

        _parse_relative_deadline("+3m", now)     → now + 3min
        _parse_relative_deadline("+2h", now)     → now + 2h
        _parse_relative_deadline("+5",  now)     → now + 5min
        _parse_relative_deadline("+abc", now)    → None (warning)
    """
    body = stop_time[1:].strip().lower()  # 去掉 '+'
    if not body:
        logger.warning(
            "review: empty relative stop_time %r; ignoring deadline.", stop_time,
        )
        return None

    # 拆数字部分和单位部分
    import re as _re
    m = _re.match(r"^(\d+)\s*([a-z]*)$", body)
    if not m:
        logger.warning(
            "review: invalid relative stop_time %r (expected '+Nm'/'+Nh'/'+N'); "
            "ignoring deadline.",
            stop_time,
        )
        return None

    try:
        n = int(m.group(1))
    except ValueError:
        logger.warning(
            "review: invalid number in relative stop_time %r; ignoring deadline.",
            stop_time,
        )
        return None

    unit = m.group(2) or "m"
    if unit in ("m", "min", "mins", "minute", "minutes"):
        delta_minutes = n
    elif unit in ("h", "hr", "hrs", "hour", "hours"):
        delta_minutes = n * 60
    else:
        logger.warning(
            "review: unknown unit %r in relative stop_time %r "
            "(expected m/min/h/hr); ignoring deadline.",
            unit, stop_time,
        )
        return None

    from datetime import timedelta as _td
    deadline = reference_time + _td(minutes=delta_minutes)
    logger.info(
        "review: relative stop_time %r → deadline=%s (reference=%s, +%dmin)",
        stop_time,
        deadline.isoformat(timespec="seconds"),
        reference_time.isoformat(timespec="seconds"),
        delta_minutes,
    )
    return deadline


def _poll_until_done_or_deadline(
    *,
    platform: Any,
    task_id: str,
    review_stage: str,
    poll_interval_seconds: int,
    deadline: Optional[datetime],
    ctx: WorkflowContext,
):
    """阻塞轮询 ``task_id`` 直到 ``TaskStatus.APPROVED`` **或** ``deadline`` 到达。

    返回 ``(info, hit_deadline)``：

    * ``info``——最后一次 :class:`TaskInfo`；
    * ``hit_deadline``——``True`` 表示到达 ``deadline`` 时仍未完成（下游会
      按"部分审完"流程走 split_approved_data + 建新尾巴 task，而不是抛错）。

    * ``REJECTED`` → 立即抛 :class:`PlatformError`（人工取消的任务，没必要再等）；
    * ``APPROVED`` → 返回 ``(info, False)``；
    * 到达 ``deadline`` 仍未 APPROVED → 返回 ``(info, True)``，由调用方
      继续走条目级拆分流程。
    """
    attempt = 0
    last_percent = -1.0
    while True:
        attempt += 1
        info = platform.get_task_status(task_id, review_stage=review_stage)
        percent = float(info.percent_completed or 0.0)
        all_confirmed = bool(info.extra.get("all_confirmed", False))
        # 日志策略：
        #  * 进度有变动 (>=0.1%) 时**必打** INFO（关键节点可见）；
        #  * 否则每 5 次轮询打一次心跳 INFO（让用户看到流水线仍在工作，
        #    而不是误以为"假死"——Phrase 的 progress 在审员没点 Complete
        #    之前即使 UI 显示 90% 也可能被 segmentsCount 读到真实比例，
        #    但如果审员一直不操作则 progress 不变，不打日志会让用户焦虑）；
        #  * 其余轮次走 DEBUG，不污染生产日志。
        progress_changed = abs(percent - last_percent) >= 0.1
        heartbeat_due = (attempt == 1) or (attempt % 5 == 0)
        if progress_changed or heartbeat_due:
            logger.info(
                "review[%s]: poll attempt=%d status=%s progress=%.1f%% "
                "all_confirmed=%s (raw=%s)",
                review_stage,
                attempt,
                info.status.value if hasattr(info.status, "value") else info.status,
                percent,
                all_confirmed,
                info.extra.get("raw_status", ""),
            )
            last_percent = percent
        else:
            logger.debug(
                "review[%s]: poll attempt=%d (silent, progress unchanged at %.1f%%)",
                review_stage, attempt, percent,
            )

        if info.status == TaskStatus.APPROVED:
            return info, False

        # Phrase 场景：审员在 UI 把全部段都 confirm 了，但没点
        # "Complete this job" 按钮——此时 ``job.status`` 还是 NEW/ACCEPTED，
        # 但 segmentsCount 返回 ``allConfirmed=true``。为了避免白白等到
        # deadline，提前进入 split 流程把全部 approved 条目带入下游。
        if all_confirmed:
            logger.info(
                "review[%s]: platform reports all segments confirmed "
                "(attempt=%d, progress=%.1f%%) — early-exit polling, "
                "treating as fully reviewed.",
                review_stage, attempt, percent,
            )
            return info, False

        if info.status == TaskStatus.REJECTED:
            raise PlatformError(
                f"review[{review_stage}]: task {task_id} was rejected / cancelled "
                f"on the platform (raw_status={info.extra.get('raw_status', '')}). "
                f"Fix the task on Crowdin or delete state_data['{review_stage}."
                f"task_id'] and re-run with --fresh."
            )

        # 未完成——判断是否已到截止。
        if deadline is not None and datetime.now() >= deadline:
            logger.info(
                "review[%s]: deadline %s reached with progress=%.1f%% — "
                "proceeding to split_approved_data (partial run).",
                review_stage,
                deadline.isoformat(timespec="minutes"),
                percent,
            )
            return info, True

        time.sleep(max(1, int(poll_interval_seconds)))


def _apply_split_to_entries(
    ctx: WorkflowContext,
    approved_xlsx: Path,
    split: Any,
) -> None:
    """把 split 结果回写到 ``ctx.entries``。

    具体做法：

    * 用 ``extra["approved_keys"]`` 的集合筛掉 ``ctx.entries`` 中未 approved 的条目；
    * 从 ``approved_xlsx`` 读回 approved 条目的最新 ``target_text`` 覆盖内存条目的译文。

    这样下游 ``validate_data`` / ``dtxml_merge`` / ``push_vcs`` 只会处理已审部分；
    pending 的条目被显式从 ctx.entries 移除，避免未审译文被当成合法结果写出去。

    **极简平台兜底**：若 ``extra`` 既没给 ``approved_keys`` 也没给
    ``pending_keys``（例如 :class:`NoopPlatform` 的空实现），说明该平台
    并不区分 approved/pending 条目——此时保留 ``ctx.entries`` 原状，
    由 ``is_complete`` 自身决定下游是否正常走通。
    """
    from ...sources import XlsxSource  # noqa: WPS433

    approved_keys_raw = split.extra.get("approved_keys")
    pending_keys_raw = split.extra.get("pending_keys")

    # 极简平台兜底——两组 keys 都没给 → 不动 ctx.entries。
    if approved_keys_raw is None and pending_keys_raw is None:
        logger.info(
            "review: platform did not provide approved_keys/pending_keys; "
            "keeping ctx.entries unchanged (%d entries).",
            len(ctx.entries),
        )
        return

    approved_keys = set(approved_keys_raw or [])
    if not approved_keys:
        logger.info("review: split produced 0 approved entries; clearing ctx.entries.")
        ctx.entries = []
        return

    # 1) 从 approved xlsx 读回最新译文（映射 key → target_text）。
    try:
        latest = XlsxSource(encoding="utf-8").load(str(approved_xlsx))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "review: failed to re-read approved xlsx %s (%s); "
            "falling back to current in-memory targets.",
            approved_xlsx, exc,
        )
        latest = []
    target_by_key = {e.key: e.target_text for e in latest if e.target_text}

    # 2) 保留 approved_keys 对应的条目，并刷新译文。
    kept: list = []
    for entry in ctx.entries:
        if entry.key not in approved_keys:
            continue
        new_target = target_by_key.get(entry.key)
        if new_target:
            entry.target_text = new_target
        kept.append(entry)
    before = len(ctx.entries)

    # 硬保护：approved_keys 非空（claim 有 N 条已审），但过滤后 kept 为空，
    # 意味着 approved_keys 和 ctx.entries 完全无交集——通常是 key 维度错配
    # （如把 xliff 里 Crowdin 的数字 ``id`` 当成业务 key 填进了
    # approved_keys，而内存里是 ``resname`` 业务 key，2026-10-09 实测
    # 事故现场）。此时**不能**让 ctx.entries 被擦空，必须显式报错让
    # runner 保留 state_data 等排查，杜绝 silent data loss。
    if not kept and ctx.entries and approved_keys:
        from ...commons.exceptions import PlatformError  # noqa: WPS433
        sample_approved = sorted(approved_keys)[:3]
        sample_entries = [e.key for e in ctx.entries[:3]]
        raise PlatformError(
            f"review: approved_keys has {len(approved_keys)} items but none "
            f"matched any of {len(ctx.entries)} ctx.entries — this is a "
            f"KEY MISMATCH between the platform-side approved keys and "
            f"in-memory entry keys. Did XliffSource read Crowdin's numeric "
            f"'id' instead of 'resname'?  "
            f"approved_keys sample={sample_approved!r}, "
            f"entries sample={sample_entries!r}."
        )

    ctx.entries = kept
    logger.info(
        "review: ctx.entries filtered to approved subset: %d → %d",
        before, len(ctx.entries),
    )

    # 5.1a 【兄弟行广播】translate 阶段把同 source 的多条压成了一条代表走审核；
    #       现在代表 approved，需要从 incr 快照回捞兄弟行并复用代表的 target。
    #       pending 的代表不扩散兄弟（它们随代表一起由 tail task 续审）。
    _broadcast_siblings_from_snapshot(ctx)


def _broadcast_siblings_from_snapshot(ctx: WorkflowContext) -> None:
    """如果 translate 阶段保存了 incr 快照，就从快照把 approved 代表的
    兄弟行回捞合入 ``ctx.entries``。

    具体规则见 :func:`TiMi_HOK_Game_Translator.utils.sibling_broadcast.broadcast_siblings_by_source`。
    """
    snapshot_raw = ctx.state_payload.get("translate.incr_snapshot_path") or ""
    if not snapshot_raw:
        # 没走过 translate 的 same-source 折叠（可能是空 entries 分支），
        # 不扩散。
        return
    snapshot_path = Path(snapshot_raw)
    from ...utils import broadcast_siblings_by_source  # noqa: WPS433 — 局部避免循环

    before = len(ctx.entries)
    expanded = broadcast_siblings_by_source(
        approved_entries=ctx.entries,
        snapshot_path=snapshot_path,
    )
    if len(expanded) != before:
        logger.info(
            "review: sibling broadcast expanded ctx.entries %d → %d.",
            before, len(expanded),
        )
    ctx.entries = expanded


def _create_tail_task(
    *,
    ctx: WorkflowContext,
    platform: Any,
    review_stage: str,
    target_locale: str,
    batch_name: str,
    pending_xlsx_path: Path,
    pending_count: int,
    tail_store: Any,
    review_cfg: Any,
    hit_deadline: bool,
) -> None:
    """把 ``pending_xlsx_path`` 上传到平台生成**新尾巴 task**，并把 task_id
    落到 ``workspace/last_tasks.json`` 的对应 slot。

    约定：
    * 文件名复用 ``pending_xlsx_path``（``..._pending.xlsx``）；
    * 任务标题带 ``[tail]`` 前缀，方便平台侧区分；
    * 产生的 task_id 存到 TailTaskStore（而不是 state_data），下一天 run
      时由 ``last_first_review`` / ``last_second_review`` 读走。
    """
    from datetime import datetime as _dt

    from ...commons.exceptions import PlatformError  # noqa: WPS433

    if not pending_xlsx_path.exists():
        logger.warning(
            "review[%s]: pending xlsx %s does not exist — skipping tail task creation.",
            review_stage, pending_xlsx_path,
        )
        return

    # 构造唯一的远端文件名——加时间戳后缀（单下划线）。
    # 若直接用 ``pending_xlsx_path.name`` 作 remote_path，连续多次 roll-over
    # 或同一批次 re-run 时会撞到 Crowdin 的 ``HTTP 400 Invalid name given.
    # Name must be unique``（Crowdin 项目文件名需唯一）。
    # 2026-10-09 分隔符从 "__" 改为 "_"，与 last_first/last_second 的命名
    # 风格统一（和同目录 approved.xlsx/pending.xlsx 一个下划线一致）。
    timestamp = _dt.now().strftime("%Y%m%d%H%M%S")
    remote_filename = f"{pending_xlsx_path.stem}_{timestamp}{pending_xlsx_path.suffix}"

    try:
        upload = platform.upload_source(
            str(pending_xlsx_path),
            remote_path=remote_filename,
        )
    except Exception as exc:  # noqa: BLE001
        # 必须抛错——否则下游会继续 delete_task 把本轮刚拆分出的原始 task
        # 一并清掉，导致 pending 条目在 Crowdin + last_tasks.json 两边都
        # 丢失（2026-10-09 last_first_review_state 实测事故现场复盘）。
        raise PlatformError(
            f"review[{review_stage}]: failed to upload tail xlsx "
            f"{pending_xlsx_path} as {remote_filename!r}: {exc}. "
            f"Aborting pipeline so the original review task is NOT deleted; "
            f"next run can retry split_approved_data cleanly."
        ) from exc

    # 把 pending xlsx 的 Target 列（上一轮 LLM 预译）作为"已有翻译"同步上传。
    _upload_translations_if_supported(
        platform=platform,
        file_id=upload.file_id,
        target_locale=target_locale,
        xlsx_path=pending_xlsx_path,
        review_stage=review_stage,
    )

    title_prefix = "[tail]"
    try:
        task = platform.create_task(
            [upload.file_id],
            target_locale,
            review_stage=review_stage,
            title=(
                f"{title_prefix} "
                f"{(review_cfg.project_name if review_cfg else '') or ctx.config.project_code} "
                f"— {review_stage} — {batch_name}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        # 建 tail task 失败——先 best-effort 清掉刚上传的 file，再抛错让
        # runner 保留 state_data（原始 task_id 仍在 state_data 里，下次
        # 重跑会从 split_approved_data 开始走）。
        try:  # noqa: SIM105 — intentional best-effort swallow for cleanup
            platform.delete_file(upload.file_id, review_stage=review_stage)
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001, S110
            pass
        raise PlatformError(
            f"review[{review_stage}]: failed to create tail task from "
            f"new file_id={upload.file_id}: {exc}. "
            f"Rolled back the new file upload; aborting pipeline so the "
            f"original review task is NOT deleted."
        ) from exc

    record = {
        "task_id": task.task_id,
        "file_id": upload.file_id,
        "batch_name": batch_name,
        "upload_path": str(pending_xlsx_path),
        "remote_filename": remote_filename,
        "target_locale": target_locale,
        "project_id": platform.project_id,
        "platform": platform.platform_name,
        "created_at": _dt.now().isoformat(timespec="seconds"),
        "pending_count": pending_count,
        "hit_deadline": hit_deadline,
    }
    tail_store.put(review_stage, record)
    logger.info(
        "review[%s]: created TAIL task_id=%s (pending=%d entries) → persisted to last_tasks.json",
        review_stage, task.task_id, pending_count,
    )
    stage_cn = {
        "light": "轻量审校",
        "first": "一审",
        "second": "二审",
    }.get(review_stage, review_stage)
    platform_url = _build_platform_url(platform.platform_name, platform.project_id)
    entry_line = (
        f"平台入口：{platform_url}" if platform_url
        else f"平台：{platform.platform_name}（project_id={platform.project_id}）"
    )
    _notify(
        ctx,
        review_stage,
        f"⏭️ 【{ctx.config.project_code}】{stage_cn}续审任务已创建\n"
        f"剩余待审条目：{pending_count} 条\n"
        f"{entry_line}\n"
        f"将在次日的 last_{review_stage}_review 阶段继续处理。",
    )


def _notify(ctx: WorkflowContext, review_stage: str, message: str) -> None:
    """安全地发送一条通知；通知失败不影响主流程。

    会自动从 ``ctx.config.notification.mentioned`` 取出需要 @ 的用户列表
    透传给 notifier（企业微信群机器人 ``mentioned_list`` 字段），避免在每个
    调用点重复书写。
    """
    if ctx.notifier is None:
        return
    try:
        mentioned = tuple(
            (ctx.config.notification.mentioned or [])
            if getattr(ctx.config, "notification", None)
            else ()
        )
        ctx.notifier.notify(message, mentioned=mentioned)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning("review[%s]: notifier failed: %s", review_stage, exc)


def _resolve_batch_name(ctx: WorkflowContext, target_locale: str) -> str:
    """从 state_data 复用、或新建一个本次运行的批次名。

    保证 first_review / second_review 两次使用同一个 batch_name，
    便于用户在 ``workspace/batches/`` 下一眼看到一次 run 的全部产物。
    """
    key = "review.batch_name"
    existing = ctx.state_data.get(key, "") or ""
    if existing:
        return str(existing)
    batch_name = build_batch_name(
        project_code=ctx.config.project_code or "project",
        target_locale=target_locale or ctx.config.target_locale or "target",
    )
    ctx.state_data[key] = batch_name
    return batch_name


def _write_meta(path: Path, data: Dict[str, Any]) -> None:
    """把审校元数据落到 ``*.meta.json``，忽略 I/O 错误。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:  # pragma: no cover — 调试辅助
        logger.warning("review: failed to write meta %s: %s", path, exc)


def _apply_xliff_to_entries(ctx: WorkflowContext, xliff_path: Path) -> None:
    """把 Crowdin 导出的 xliff 中非空 target 字段按 Key 回写到 ctx.entries。

    参数：
        ctx: 工作流上下文；修改其 ``entries`` 列表的 ``target_text``。
        xliff_path: 刚下载的 xliff 文件绝对路径。

    注意：
        若文件不是合法 xliff（例如 ``NoopPlatform`` 回传的原始 xlsx 二进制、
        或审校员人工干预导致的格式异常），此处记一次 warning 后**保留
        现有 target_text 原状**——不会让主流程因此崩溃。真实 Crowdin
        场景会正常走通，不会命中该分支。
    """
    if not xliff_path.exists():
        return
    try:
        translated = XliffSource(encoding="utf-8").load(str(xliff_path))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "review: failed to parse xliff %s (%s); keeping existing targets unchanged.",
            xliff_path, exc,
        )
        return
    by_key = {e.key: e for e in translated}
    hits = 0
    for entry in ctx.entries:
        remote = by_key.get(entry.key)
        if remote is not None and remote.target_text:
            entry.target_text = remote.target_text
            hits += 1
    logger.info(
        "review: xliff -> entries: %d of %d updated", hits, len(ctx.entries),
    )


def _upload_translations_if_supported(
    *,
    platform: Any,
    file_id: str,
    target_locale: str,
    xlsx_path: Path,
    review_stage: str,
) -> None:
    """若平台实现了 ``upload_translations``，就把 ``xlsx_path`` 的 Target 列
    作为"已有翻译"上传。

    * 用于把 LLM 预译结果（本地 Target 列）同步到 Crowdin，这样审校员在
      Crowdin 页面能看到预译文而不是只有源串；
    * 失败不致命——继续后续 ``create_task``，审校员仍能从源串开始审（只是
      没有 LLM 预译参考）；
    * 对 PhrasePlatform / NoopPlatform 等不实现该方法的平台，自动跳过。
    """
    if not hasattr(platform, "upload_translations"):
        logger.debug(
            "review[%s]: platform=%s does not implement upload_translations — skip.",
            review_stage, getattr(platform, "platform_name", type(platform).__name__),
        )
        return
    if not file_id or not target_locale:
        logger.warning(
            "review[%s]: upload_translations missing file_id=%r or target_locale=%r — skip.",
            review_stage, file_id, target_locale,
        )
        return
    try:
        platform.upload_translations(
            file_id=file_id,
            target_locale=target_locale,
            local_xlsx_path=str(xlsx_path),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "review[%s]: upload_translations failed (continuing without pre-translations): %s",
            review_stage, exc,
        )


def _synthetic_profile(ctx: WorkflowContext):
    """当 runner 未提供 profile 时合成一份。"""
    from ...config.schema import LanguageProfile
    return LanguageProfile(id=ctx.config.target_locale or "target")


__all__ = ["run_review_stage"]
