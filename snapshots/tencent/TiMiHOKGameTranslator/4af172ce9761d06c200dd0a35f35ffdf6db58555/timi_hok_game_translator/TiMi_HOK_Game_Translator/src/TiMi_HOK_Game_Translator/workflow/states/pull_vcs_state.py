"""``pull_vcs`` 状态——从 VCS 拉取源文件工作副本。

实际拉取动作交给 :class:`~TiMi_HOK_Game_Translator.vcs.VcsClient`——默认 mock
后端不做任何事，真实后端（svn / git / perforce）由
:attr:`Config.vcs.type` 选择。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)


class PullVcsState(WorkflowStateBase):
    """将本地工作副本同步到配置的版本。"""

    name = StateEnum.PULL_VCS.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        already_done = self._already_completed(ctx)

        target_revision = ctx.config.vcs.revision or "HEAD"
        # local_path 以 ctx.vcs（由 factory 展开后的绝对路径）为准，
        # 避免同时存在"全局 config.vcs vs profile.vcs vs {workspace} 占位符"
        # 时三方不一致。
        local_path = getattr(ctx.vcs, "local_path", "") or ctx.config.vcs.local_path

        if already_done:
            # 断点续跑：跳过真正的 svn update/checkout，但**仍然要重新
            # load entries**，否则下游 state（translate / review）会拿到
            # 空列表（``ctx.entries`` 不持久化）。``source.load()`` 是纯
            # 读操作，重复调用没有副作用也无需网络。
            logger.info("PullVcsState: already completed — reloading entries only.")
        else:
            logger.info(
                "PullVcsState: syncing %s@%s → %s",
                ctx.config.vcs.type,
                target_revision,
                local_path or "<default>",
            )
            try:
                if local_path and not Path(local_path).exists():
                    ctx.vcs.checkout()
                else:
                    ctx.vcs.update(revision=target_revision)
            except Exception as exc:  # noqa: BLE001
                ctx.state_payload["pull_vcs.error"] = repr(exc)
                raise

        source_cfg = _resolve_source_config(ctx)
        source_path = resolve_source_path(ctx, source_cfg.path)
        if not source_path:
            logger.warning(
                "PullVcsState: source.path is empty — no entries loaded.",
            )
            ctx.entries = []
        else:
            try:
                ctx.entries = list(ctx.source.load(source_path))
            except Exception as exc:  # noqa: BLE001
                # source 文件不存在 / 解析失败：**不能软吞**。下游 translate
                # 会拿到 0 entries，审校阶段再被 Crowdin 拒单（HTTP 409
                # "no untranslated words"），导致误导性的报错链路。此处
                # 直接 raise，让 runner 把状态标为失败并把异常原样抛给用户。
                ctx.state_payload["pull_vcs.source_load_error"] = repr(exc)
                ctx.state_payload["pull_vcs.source_path"] = source_path
                raise

        ctx.state_payload["pull_vcs.entry_count"] = len(ctx.entries)
        ctx.state_payload["pull_vcs.source_path"] = source_path
        logger.info("PullVcsState: loaded %d entries.", len(ctx.entries))

        # 【run 开始时的文件 hash 快照】——push_vcs 用来判断"相较于本 run 起
        # 点是否发生过变更"（而不是只看 dtxml_merge dump 前后，否则会把
        # last_merge_data 带入的昨日 approved 条目的 upsert 判成 no-op）。
        _record_pre_run_hashes(ctx, source_path)

        if not already_done:
            self._mark_completed(ctx)
        return None

def _record_pre_run_hashes(ctx: WorkflowContext, incremental_path: str) -> None:  # noqa: E302
    """把 ``incr`` + ``full`` 文件的 SHA-1 存到 ``ctx.state_payload``。

    * ``incr`` 路径就是 ``pull_vcs.source_path``；
    * ``full`` 路径优先取 profile 的 ``extra.full_table_path`` /
      ``strategy_config.full_table_path``，否则从 incr 用
      :func:`infer_full_table_path` 推断。

    任何一个文件不存在就记 ``""``（空 hash）——push_vcs 侧会把空 hash
    等价于"本 run 之前这个文件不存在，任何新写入都算变更"。
    """
    import hashlib

    from ...utils.table_merger import infer_full_table_path  # noqa: WPS433

    def _sha1(p: str) -> str:
        if not p:
            return ""
        try:
            if not Path(p).exists():
                return ""
            h = hashlib.sha1()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError as exc:
            logger.warning("PullVcsState: hash %s failed: %s", p, exc)
            return ""

    # incr hash
    incr_hash = _sha1(incremental_path)
    ctx.state_payload["push_vcs.pre_hash.incr"] = incr_hash

    # full 路径解析
    profile = ctx.language_profile
    full_path = ""
    if profile is not None:
        for key in ("full_table_path",):
            candidate = (
                profile.extra.get(key)
                or profile.strategy_config.get(key)
            )
            if candidate:
                full_path = str(candidate)
                break
    if not full_path and incremental_path:
        full_path = infer_full_table_path(incremental_path)

    ctx.state_payload["push_vcs.pre_hash.full_path"] = full_path
    ctx.state_payload["push_vcs.pre_hash.full"] = _sha1(full_path)

    logger.info(
        "PullVcsState: pre-run hashes recorded (incr=%s..., full=%s...; full_path=%s)",
        (incr_hash or "<none>")[:8],
        (ctx.state_payload["push_vcs.pre_hash.full"] or "<none>")[:8],
        full_path or "<unknown>",
    )


def _resolve_source_config(ctx: WorkflowContext):
    """优先使用 profile 上的 source 配置，回退到全局 source。"""
    profile = ctx.language_profile
    if profile is not None and profile.source and profile.source.path:
        return profile.source
    return ctx.config.source


def resolve_source_path(ctx: WorkflowContext, path: str) -> str:
    """将 ``path`` 解析为绝对文件路径。

    解析顺序（优先选用已经由 ``create_vcs_client`` 展开好的
    ``ctx.vcs.local_path`` 作为基准——它已经处理过 ``{workspace}`` 占位符
    与绝对/相对路径逻辑，是最权威的 SVN 工作副本根路径）：

    * ``path`` 本身为绝对路径时直接返回；
    * 否则以 ``ctx.vcs.local_path`` 为基准拼接；
    * 若 vcs client 没有 local_path（如 mock 后端），回退到 workspace 目录。
    """
    if not path:
        return ""
    p = Path(path)
    if p.is_absolute():
        return str(p)

    # 首选：从已初始化的 VcsClient 读 local_path（factory 已展开占位符）。
    vcs_local = getattr(ctx.vcs, "local_path", "") or ""
    if vcs_local:
        return str((Path(vcs_local) / p).resolve())

    # 回退 1：profile.vcs.local_path（相对路径按 workspace 展开）。
    profile = ctx.language_profile
    profile_local = (
        profile.vcs.local_path if profile is not None and profile.vcs else ""
    ) or ""
    if profile_local:
        profile_local = profile_local.replace("{workspace}", str(ctx.workspace))
        base = Path(profile_local)
        if not base.is_absolute():
            base = ctx.workspace / base
        return str((base / p).resolve())

    # 回退 2：全局 config.vcs.local_path。
    global_local = ctx.config.vcs.local_path or ""
    if global_local:
        global_local = global_local.replace("{workspace}", str(ctx.workspace))
        base = Path(global_local)
        if not base.is_absolute():
            base = Path.cwd() / base
        return str((base / p).resolve())

    # 回退 3：workspace。
    return str((ctx.workspace / p).resolve())


__all__ = ["PullVcsState", "resolve_source_path"]
