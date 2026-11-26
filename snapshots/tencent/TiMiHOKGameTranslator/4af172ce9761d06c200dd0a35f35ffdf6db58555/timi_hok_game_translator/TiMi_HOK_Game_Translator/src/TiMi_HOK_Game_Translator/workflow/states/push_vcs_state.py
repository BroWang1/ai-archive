"""``push_vcs`` 状态——将合并后的译文提交回 VCS。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ...commons import DEFAULT_VCS_COMMIT_MESSAGE
from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from .pull_vcs_state import resolve_source_path as _resolve

logger = logging.getLogger(__name__)


class PushVcsState(WorkflowStateBase):
    """将条目写回源文件并提交至 VCS。

    为保证无变更不报错，此状态行为宽容；上游如需短路经可设置
    ``ctx.state_payload["push_vcs.skipped"] = True``。
    """

    name = StateEnum.PUSH_VCS.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("PushVcsState: already completed — skipping.")
            return None
        if ctx.state_payload.get("push_vcs.skipped"):
            reason = ctx.state_payload.get("push_vcs.skip_reason") or "upstream requested skip"
            logger.info("PushVcsState: skipping — %s.", reason)
            self._mark_completed(ctx)
            return None

        source_cfg = _resolve_source_config(ctx)
        incremental_path = _resolve(ctx, source_cfg.path)
        if not incremental_path:
            logger.warning("PushVcsState: source.path is empty — nothing to dump.")
            self._mark_completed(ctx)
            return None

        # 全量表路径：由 dtxml_merge 把合入后的绝对路径写进 state_payload，
        # 本 state 要**和增量表一起**提交到 VCS——否则本轮合入全量表的译文
        # 只落在本地工作副本，SVN 侧永远拿不到（2026-10-09 实测事故现场）。
        # 若 dtxml_merge 本轮没跑（translated=0 → skip 分支），fallback 到
        # pull_vcs 落下来的 full_path（**绝不能**让 full_path 为空而漏判
        # last_merge_data 带入的昨日 approved 对 full 表的 upsert）。
        full_path = str(
            ctx.state_payload.get("dtxml_merge.full_path")
            or ctx.state_payload.get("push_vcs.pre_hash.full_path")
            or ""
        )

        # 【基准 hash 来源】优先用 pull_vcs 阶段落下来的 ``pre_hash``——这是
        # "本次 run 刚开始、还没动过任何文件"时的真实快照；而不是本 state
        # dump 前的瞬时值（否则会漏掉 dtxml_merge 对 full 表的 upsert，
        # 以及 last_merge_data 对 full 表的 upsert，让 push_vcs 误判
        # "nothing changed" → 跳过 commit，SVN 侧永远拿不到当天译文）。
        #
        # 若 state_payload 里取不到（兼容旧批次 / 不走 pull_vcs 的测试路径），
        # 回退到"本 state dump 前的瞬时 hash"做兜底。
        pre_hash_inc = ctx.state_payload.get("push_vcs.pre_hash.incr")
        if pre_hash_inc is None:
            pre_hash_inc = _file_hash(incremental_path)
        pre_hash_full = ctx.state_payload.get("push_vcs.pre_hash.full")
        if pre_hash_full is None:
            pre_hash_full = _file_hash(full_path) if full_path else None

        # 1) 写增量表（ctx.entries 已是"剔除 approved 之后的剩余条目"）。
        Path(incremental_path).parent.mkdir(parents=True, exist_ok=True)
        # 【P4 兼容钩子】写磁盘前通知 VCS 后端——svn/git/mock 为 no-op；
        # perforce 会跑 `p4 edit`，取消本地文件的只读属性，否则下面的
        # ctx.source.dump() 会抛 PermissionError。
        _paths_to_prepare: list = [incremental_path]
        if full_path:
            _paths_to_prepare.append(full_path)
        try:
            ctx.vcs.prepare_for_write(_paths_to_prepare)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 不致命，commit 阶段仍会兜底。
            logger.warning(
                "PushVcsState: vcs.prepare_for_write failed (continuing): %s",
                exc,
            )
        try:
            ctx.source.dump(ctx.entries, incremental_path)
        except Exception as exc:  # noqa: BLE001
            ctx.state_payload["push_vcs.dump_error"] = repr(exc)
            raise

        # 全量表的内容由 ``dtxml_merge`` 已经写入磁盘（它直接通过底层
        # ``merge_incremental_into_full`` 的 I/O 完成），本 state 无需再
        # dump；只需要对比哈希决定要不要加入 commit 列表。

        post_hash_inc = _file_hash(incremental_path)
        post_hash_full = _file_hash(full_path) if full_path else None

        changed_paths: list = []
        if pre_hash_inc != post_hash_inc:
            changed_paths.append(incremental_path)
        if full_path and pre_hash_full != post_hash_full:
            changed_paths.append(full_path)

        if not changed_paths:
            logger.info(
                "PushVcsState: nothing changed (incremental=%s, full=%s) — "
                "skipping commit to avoid empty/no-op push to VCS.",
                incremental_path, full_path or "<none>",
            )
            ctx.state_payload["push_vcs.path"] = incremental_path
            ctx.state_payload["push_vcs.unchanged"] = True
            self._mark_completed(ctx)
            return None

        commit_message = (
            ctx.state_payload.get("push_vcs.message")
            or ctx.config.vcs.default_commit_message
            or DEFAULT_VCS_COMMIT_MESSAGE
        )
        try:
            ctx.vcs.commit(changed_paths, message=str(commit_message))
        except Exception as exc:  # noqa: BLE001
            ctx.state_payload["push_vcs.commit_error"] = repr(exc)
            raise

        ctx.state_payload["push_vcs.path"] = incremental_path
        ctx.state_payload["push_vcs.committed_paths"] = list(changed_paths)
        logger.info(
            "PushVcsState: committed %d file(s): %s",
            len(changed_paths), changed_paths,
        )

        self._mark_completed(ctx)
        return None


def _file_hash(path: str) -> Optional[str]:
    """对 ``path`` 的内容计算 SHA-1；文件不存在/读失败/路径为空返回 ``None``。

    用途：:class:`PushVcsState` 在 dump 前后各算一次，相同 → 跳过 commit。
    """
    import hashlib

    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def _resolve_source_config(ctx: WorkflowContext):
    """优先使用 profile 上的 source 配置，回退到全局 source。"""
    profile = ctx.language_profile
    if profile is not None and profile.source and profile.source.path:
        return profile.source
    return ctx.config.source


__all__ = ["PushVcsState"]
