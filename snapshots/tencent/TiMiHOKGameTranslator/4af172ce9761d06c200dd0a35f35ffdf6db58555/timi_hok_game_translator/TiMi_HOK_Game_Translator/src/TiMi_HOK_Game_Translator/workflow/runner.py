"""工作流驱动器。

给定一份 :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile`（或一组显式状态名），
驱动器依次：

1. 通过 :func:`TiMi_HOK_Game_Translator.workflow.state_registry.build_workflow` 实例化工作流；
2. 初始化 :class:`~.states_manager.StatesManager`（全部为“未完成”）；
3. 组装 :class:`WorkflowContext`（含 :class:`AutoSaveDict` 写入 ``project_run_data.json``，
   :class:`StatesManager` 写入 ``project_status.json``）；
4. 逐个执行状态 :meth:`execute`，支持 ``skip_after_current`` / ``finish`` 等提示；
5. 最后进入终态 :class:`FinishedState`。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from ..commons import DEFAULT_STATE_FILENAME
from ..commons import WorkflowState as StateEnum
from ..config.schema import Config, LanguageProfile
from .auto_save_dict import AutoSaveDict
from .state import WorkflowContext, WorkflowStateBase
from .state_registry import build_state, build_workflow
from .states_manager import StatesManager

logger = logging.getLogger(__name__)

_RUN_DATA_FILENAME = "project_run_data.json"


class WorkflowRunner:
    """驱动一种语种的工作流至完成。

    典型用法::

        runner = WorkflowRunner(
            config=config,
            profile=config.language_profile("vi"),
            vcs=vcs, source=source, llm=llm, platform=platform,
            notifier=notifier,
        )
        runner.run()

    本类故意保持短小；可重用的拼装逻辑（后端创建、通知接线）均在 CLI。
    """

    def __init__(
        self,
        *,
        config: Config,
        profile: Optional[LanguageProfile] = None,
        vcs: Any,
        source: Any,
        llm: Any,
        platform: Any,
        notifier: Optional[Any] = None,
        workflow_names: Optional[Iterable[str]] = None,
        workspace: Optional[Path] = None,
        state_filename: Optional[str] = None,
    ) -> None:
        self.config = config
        self.profile = profile
        self.vcs = vcs
        self.source = source
        self.llm = llm
        self.platform = platform
        self.notifier = notifier

        self.workspace = workspace or config.workspace_path()
        self.workspace.mkdir(parents=True, exist_ok=True)

        # 【按语种分区】每条语种 profile 占用一个子目录，存放 state 文件和
        # last_tasks.json。多语种并发时各走各的子目录，互不覆盖。
        # - profile.id 非空（conf/languages/<lang>.json 的 "id" 字段，和文件名一致）→ 用 profile.id
        # - 否则回退 config.target_locale（命令行传入或 config.yaml 顶层）
        # - 都没有 → 空串（等同旧行为，state 直接落 workspace 根）
        lang_dir_name = ""
        if profile is not None and (profile.id or "").strip():
            lang_dir_name = profile.id.strip()
        elif (config.target_locale or "").strip():
            lang_dir_name = config.target_locale.strip()
        self._lang_dir_name: str = lang_dir_name
        self._lang_scoped_workspace: Path = (
            self.workspace / lang_dir_name if lang_dir_name else self.workspace
        )
        if lang_dir_name:
            # 预创建语种子目录，避免首次写 state 时 parent 不存在。
            self._lang_scoped_workspace.mkdir(parents=True, exist_ok=True)

        # 确定本次执行的状态名列表。
        if workflow_names is not None:
            self._state_names: List[str] = list(workflow_names)
        elif profile is not None and profile.workflow:
            self._state_names = list(profile.workflow)
        else:
            self._state_names = _default_workflow()

        # 状态文件（完成位记录）与业务数据文件——落到按语种分区的子目录。
        self._state_file_path = self._lang_scoped_workspace / (
            state_filename or DEFAULT_STATE_FILENAME
        )
        self._run_data_path = self._lang_scoped_workspace / _RUN_DATA_FILENAME

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------
    def run(self, *, fresh: bool = False, batch: str | None = None) -> str:
        """执行工作流并返回最终状态名。

        参数：
            fresh: ``True`` 时先删除上次持久化的 state 与 run_data，强制从头跑。
                与 ``batch`` 互斥。
            batch: 指定一个历史批次名（如 ``"vi_20261008204338"``），从该批次
                的 ``_archive/`` 目录把 state 与 run_data 还原回 workspace 根，
                然后 Runner 的 "skip already completed" 逻辑会自动跳过已完成的
                state，从第一个未完成的 state 继续。与 ``fresh`` 互斥。
            （两者都为默认值时）**M 语义**：等同于"新开批次 + 软清理"——
                删除 workspace 根下残留的 state 文件，但**保留** ``last_tasks.json``
                等跨批次持久化状态。
        """
        if fresh and batch:
            # 调用方传入的互斥由 CLI 层拦截；这里再兜底一次。
            raise ValueError("Runner.run: fresh=True and batch is set — mutually exclusive.")

        if batch:
            # --batch：从归档恢复 state；若恢复不到，日志告警后按新批次处理。
            restored = self._restore_from_archive(batch)
            if restored:
                logger.info(
                    "WorkflowRunner: resuming batch %s from %s",
                    batch, restored,
                )
            else:
                logger.warning(
                    "WorkflowRunner: --batch %s given but no archive found; "
                    "starting a fresh batch instead.",
                    batch,
                )
                self._delete_persistent_files()
        else:
            # 无 --batch：删 workspace 根的 state 残留。
            # last_tasks.json 由 _delete_persistent_files 本就不碰，等同 M 语义。
            # 【方案 2 友好提示】若发现现场有未完成的 state，提示用户可以
            # 用 --batch <name> 续跑；但为了不破坏 Day-N 日常"自动开新批次"
            # 的习惯，这里**不阻塞**，只告警。
            if not fresh:
                existing_batch = self._read_batch_name_from_workspace()
                if existing_batch:
                    logger.warning(
                        "WorkflowRunner: detected incomplete state in %s "
                        "belonging to batch %r. Starting a NEW batch and "
                        "DISCARDING this progress. "
                        "If you intended to resume, Ctrl+C now and re-run with "
                        "'--batch %s'; if you really want a fresh batch, "
                        "re-run with '--fresh' to silence this warning.",
                        self._state_file_path, existing_batch, existing_batch,
                    )
            self._delete_persistent_files()

        # 实例化具体状态。
        states = build_workflow(self._state_names)

        manager = StatesManager(self._state_file_path)
        manager.initialize({name: False for name in self._state_names})

        # 加载已持久化的业务数据。
        run_data = self._load_run_data()

        ctx = self._build_context(run_data, manager)

        # -- 驱动状态机。
        try:
            for idx, state in enumerate(states):
                state_name = state.name
                if manager.is_completed(state_name):
                    logger.info(
                        "WorkflowRunner: %s already completed — skipping.",
                        state_name,
                    )
                    continue

                logger.info(
                    "WorkflowRunner: entering %s (%d/%d)",
                    state_name, idx + 1, len(states),
                )
                next_hint = state.execute(ctx)

                # 每个状态执行后都将业务数据写盘，避免中途崩溃丢失进度。
                self._save_run_data(run_data)

                if isinstance(next_hint, str) and next_hint:
                    # 显式跳转——前推指针。
                    target_idx = _index_of(states, next_hint)
                    if target_idx is not None:
                        # ``for`` 循环会自然推进 idx；此处将当前+1 至
                        # target 之间的状态标为“已完成”，完成快进。
                        for skipped_state in states[idx + 1: target_idx]:
                            manager.mark_completed(skipped_state.name)
                        continue
                    else:
                        logger.warning(
                            "WorkflowRunner: %s requested jump to unknown state %r",
                            state_name, next_hint,
                        )

            # 终态。
            finished = build_state(StateEnum.FINISHED.value)
            logger.info("WorkflowRunner: entering %s (terminal)", finished.name)
            finished.execute(ctx)

            # 【批次归档】仅在正常完成时触发：把当前批次的 state 文件移到
            # ``workspace/batches/<batch>/_archive/``，为下一天的 run 清出 workspace。
            # 异常/中断路径不归档，让续跑能看到残留 state 继续。
            self._archive_batch_state(ctx)

            return finished.name

        except Exception:
            logger.exception("WorkflowRunner: pipeline failed")
            # 失败时仍尽量写盘当前进度后重新抛出，方便事后排查。
            try:
                self._save_run_data(run_data)
                manager.save()
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                pass
            raise

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _build_context(
        self,
        run_data: AutoSaveDict,
        manager: StatesManager,
    ) -> WorkflowContext:
        profile = self.profile
        if profile is None:
            profile = self.config.language_profile(
                self.config.target_locale or "target",
            )
        return WorkflowContext(
            config=self.config,
            vcs=self.vcs,
            source=self.source,
            llm=self.llm,
            platform=self.platform,
            notifier=self.notifier,
            language_profile=profile,
            entries=[],
            state_payload={},
            state_data=run_data,
            workspace=self.workspace,
            states_manager=manager,
        )

    def _load_run_data(self) -> AutoSaveDict:
        """从磁盘初始化并返回一份新的 :class:`AutoSaveDict`。"""
        callback = self._save_run_data_callback()
        data = AutoSaveDict(save_callback=None)  # 加载时暂不写盘
        if self._run_data_path.exists():
            try:
                raw = json.loads(self._run_data_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data.update(raw)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "WorkflowRunner: failed to load run data %s: %s",
                    self._run_data_path, exc,
                )
        data.set_save_callback(callback)
        # 将 dict 本身绑定到回调闭包上，以便内部序列化。
        self._run_data_ref = data
        return data

    def _save_run_data_callback(self) -> Callable[[], None]:
        def _cb() -> None:
            data = getattr(self, "_run_data_ref", None)
            if data is None:
                return
            self._save_run_data(data)
        return _cb

    def _save_run_data(self, data: AutoSaveDict) -> None:
        try:
            self._run_data_path.parent.mkdir(parents=True, exist_ok=True)
            payload = data.serialisable_items()
            tmp = self._run_data_path.with_suffix(self._run_data_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            import os as _os
            _os.replace(tmp, self._run_data_path)
        except OSError as exc:
            logger.warning(
                "WorkflowRunner: failed to write %s: %s",
                self._run_data_path, exc,
            )

    def _delete_persistent_files(self) -> None:
        for path in (self._state_file_path, self._run_data_path):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("WorkflowRunner: could not delete %s: %s", path, exc)

    # ------------------------------------------------------------------
    def _restore_from_archive(self, batch_name: str) -> Path | None:
        """为续跑 ``--batch <batch_name>`` 恢复 state 文件。

        恢复优先级（2026-10-09 方案 2 增强）：

        1. **优先：workspace 现场**。若按语种分区的 state 文件（本次 Runner
           预先指向 ``workspace/<lang>/workflow_state.json``）**已经存在**
           且其对应的 ``project_run_data.json`` 里 ``review.batch_name``
           恰好等于传入的 ``batch_name``——说明这就是上次崩溃/中断留下
           的现场，**原地续跑**（不动文件）。这解决了"归档只在
           FinishedState 跑完才做、崩溃时 _archive/ 不存在"的缺陷。
        2. **其次：归档目录**。从 ``batches/<batch>/_archive/`` 复制归档
           的 state 文件到 workspace 的语种子目录。
        3. 以上都失败 → 返回 ``None``，调用方会走"启新批次"路径。

        流程：
        * 情况 1 命中：返回 workspace 的语种子目录路径（用于日志）；
          **不**清理、**不**复制，让 Runner 的 "skip is_completed" 跳转
          到第一个未完成的 state。
        * 情况 2 命中：
            a) 定位 ``_archive`` 目录；不存在则跳到 3；
            b) 先清掉现场的 state / run_data（避免和归档内容混杂）；
            c) 分别把 ``workflow_state.json`` 和 ``project_run_data.json``
               从归档**复制**（不是移动）回现场——保留归档完整，便于反
               复续跑；
            d) 返回归档目录绝对路径。

        若归档存在但两份 state 都读不到（空归档），仍返回 ``None`` 使调用方
        回落到"新开批次"路径，这是比"静默跑一个空工作流"更安全的行为。
        """
        # ------- Case 1: 优先用 workspace 现场 -------
        workspace_batch = self._read_batch_name_from_workspace()
        if workspace_batch and workspace_batch == batch_name:
            logger.info(
                "WorkflowRunner: found live workspace state for batch %s "
                "(workflow_state.json=%s). Resuming in place without archive restore.",
                batch_name, self._state_file_path,
            )
            return self._lang_scoped_workspace

        # ------- Case 2: 从 _archive/ 归档恢复 -------
        archive_dir = self.workspace / "batches" / batch_name / "_archive"
        if not archive_dir.exists() or not archive_dir.is_dir():
            return None

        src_state = archive_dir / self._state_file_path.name
        src_run_data = archive_dir / self._run_data_path.name
        if not src_state.exists() and not src_run_data.exists():
            return None

        # 清掉 workspace 现场残留的 state 文件，避免和归档内容混杂。
        self._delete_persistent_files()

        import shutil
        copied = 0
        for src, dst in (
            (src_state, self._state_file_path),
            (src_run_data, self._run_data_path),
        ):
            if not src.exists():
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(src), str(dst))
                copied += 1
                logger.debug(
                    "WorkflowRunner: restored %s ← %s", dst.name, src,
                )
            except OSError as exc:
                logger.warning(
                    "WorkflowRunner: failed to restore %s ← %s: %s",
                    dst, src, exc,
                )

        return archive_dir if copied > 0 else None

    def _read_batch_name_from_workspace(self) -> str:
        """读 workspace 现场 ``project_run_data.json`` 里的 ``review.batch_name``。

        用于判断 workspace 根（按语种分区后的子目录）里残留的 state 文件
        是否属于用户想续跑的那个 batch_name。读失败/字段缺失/文件不存在都
        返回空串——调用方会据此继续走归档恢复路径。
        """
        if not self._run_data_path.exists():
            return ""
        try:
            raw = json.loads(self._run_data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(
                "WorkflowRunner: _read_batch_name_from_workspace failed on %s: %s",
                self._run_data_path, exc,
            )
            return ""
        if not isinstance(raw, dict):
            return ""
        name = raw.get("review.batch_name") or raw.get("translate.batch_name") or ""
        return str(name or "").strip()

    # ------------------------------------------------------------------
    def _archive_batch_state(self, ctx: Any) -> None:
        """流水线正常完成后，把当前批次的 state 文件归档到批次目录。

        移动的文件（现均位于按语种分区的子目录 ``workspace/<lang>/``）：

        * ``workspace/<lang>/workflow_state.json``
        * ``workspace/<lang>/project_run_data.json``

        **不**移动的文件（跨批次保留）：

        * ``workspace/<lang>/last_tasks.json``——下一天 ``last_first_review`` /
          ``last_second_review`` state 要靠它接回昨日尾巴 task。
        * ``workspace/svn/``、``workspace/git/``、``workspace/p4/`` 等 VCS 工作副本。
        * ``workspace/batches/<batch>/`` 下的审校产物本身。

        归档位置：``workspace/batches/<batch_name>/_archive/``；若当前批次
        名不可解析（state_data 没写）则跳过归档——保守行为优先。
        """
        batch_name: str = ""
        try:
            # 以 review 流程写入的 batch_name 作为归档目录依据。
            batch_name = str(ctx.state_data.get("review.batch_name", "") or "")
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            batch_name = ""

        if not batch_name:
            logger.info(
                "WorkflowRunner: no batch_name in state_data; skipping archive. "
                "state files remain in workspace root."
            )
            return

        archive_dir = self.workspace / "batches" / batch_name / "_archive"
        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "WorkflowRunner: cannot create archive dir %s: %s", archive_dir, exc,
            )
            return

        import shutil
        for src in (self._state_file_path, self._run_data_path):
            if not src.exists():
                continue
            dst = archive_dir / src.name
            try:
                shutil.move(str(src), str(dst))
                logger.info("WorkflowRunner: archived %s → %s", src.name, dst)
            except OSError as exc:
                logger.warning(
                    "WorkflowRunner: failed to archive %s → %s: %s",
                    src, dst, exc,
                )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _default_workflow() -> List[str]:
    """未提供 profile 时的最小可行工作流。"""
    return [
        StateEnum.PULL_VCS.value,
        StateEnum.TRANSLATE.value,
        StateEnum.VALIDATE_DATA.value,
        StateEnum.PUSH_VCS.value,
    ]


def _index_of(states: List[WorkflowStateBase], name: str) -> Optional[int]:
    for i, s in enumerate(states):
        if s.name == name:
            return i
    return None


__all__ = ["WorkflowRunner"]
