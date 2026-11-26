"""工作流上下文与状态基类。

工作流建模为线性状态机，由 :class:`~.runner.WorkflowRunner` 驱动。
每个状态收到一份 :class:`WorkflowContext` 快照，执行副作用后返回下一个状态名
或 ``None``（流水线结束）。持久化与并发由
:class:`~.states_manager.StatesManager` 与上下文中自动落盘的
:class:`~.auto_save_dict.AutoSaveDict` 处理。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..commons import WorkflowState as StateEnum
from ..config.schema import Config, LanguageProfile
from ..llm.base import LLMClient
from ..platforms.base import TranslationPlatform
from ..sources.base import Entry, LocalizationSource
from ..vcs.base import VcsClient
from .auto_save_dict import AutoSaveDict


@dataclass
class WorkflowContext:
    """供状态使用的共享上下文。

    上下文在状态之间**共享**，前一状态的修改对后续状态可见。提供两类持久化面：

    * :attr:`state_payload`——普通 dict，驱动器（:class:`~.runner.WorkflowRunner`）
      在每次状态切换时会将它写入状态文件。适合少量、JSON 安全的转移标记。
    * :attr:`state_data`——:class:`AutoSaveDict`，每次变更均即时落盘；适合存放
      必须存活进程重启的业务数据（任务 id、DataFrame、中间输出）。
      使用 :meth:`AutoSaveDict.add_non_serialisable_key` 注册的 key
      保留在内存但不写入磁盘。

    字段：
        config: 完整合并后的 :class:`Config`。
        language_profile: 当前生效的 :class:`LanguageProfile`；当用户未提供 profile 时，
            它是由 :meth:`Config.language_profile` 合成的一份。
        vcs / source / llm / platform / notifier: 本次选择的同名后端。
        entries: 流经流水线的内存条目列表。
        state_payload: 少量、JSON 安全的转移标记。
        state_data: :class:`AutoSaveDict`，存放业务关键数据。
        workspace: workspace 绝对路径（启动时等于 ``config.workspace_path()``）。
        states_manager: 可选，指向驱动的
            :class:`~.states_manager.StatesManager`，方便状态调用
            :meth:`~.states_manager.StatesManager.is_completed` 实现幂等重启。
    """

    config: Config
    vcs: VcsClient
    source: LocalizationSource
    llm: LLMClient
    platform: TranslationPlatform
    notifier: Optional[Any] = None  # 来自 ``notify`` 子包的 ``Notifier``。

    language_profile: Optional[LanguageProfile] = None

    #: 流经流水线的内存条目列表。
    entries: List[Entry] = field(default_factory=list)

    #: 与当前状态名一同持久化的自由 payload。
    #: 保持为普通 dict，方便 :meth:`~.runner.WorkflowRunner.save` 一次性原子写入。
    state_payload: Dict[str, Any] = field(default_factory=dict)

    #: 自动持久化的业务数据表（参见类 docstring）。
    state_data: AutoSaveDict = field(default_factory=AutoSaveDict)

    #: workspace 绝对路径（启动时等于 ``config.workspace_path()``）。
    workspace: Path = field(default_factory=Path.cwd)

    #: 由 :class:`~.runner.WorkflowRunner` 回塑，供子状态查看其他状态的完成标志。
    states_manager: Optional[Any] = None


class WorkflowStateBase(abc.ABC):
    """所有工作流状态的基类。

    子类需设置类属性 :attr:`name` 为
    :class:`~TiMi_HOK_Game_Translator.commons.WorkflowState` 中的某个值（或通过
    :func:`TiMi_HOK_Game_Translator.workflow.state_registry.register_state` 注册的自定义名），
    并实现 :meth:`execute` 执行副作用。
    """

    #: 状态唯一名（参见 :class:`~TiMi_HOK_Game_Translator.commons.WorkflowState`）。
    name: str = ""

    # ------------------------------------------------------------------
    # 具体状态常用的辅助方法
    # ------------------------------------------------------------------
    def _already_completed(self, ctx: WorkflowContext) -> bool:
        """当本状态已被标为完成时返回 True。

        子类一般在 :meth:`execute` 开头调用，实现“断点重跑时跳过已完成状态”。
        """
        mgr = ctx.states_manager
        return bool(mgr and mgr.is_completed(self.name))

    def _mark_completed(self, ctx: WorkflowContext) -> None:
        """将本状态的完成位在 states_manager 上置位。"""
        mgr = ctx.states_manager
        if mgr is not None:
            mgr.mark_completed(self.name)

    @abc.abstractmethod
    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        """执行本状态的副作用，并返回下一个状态名。

        返回值：

        * ``None``——按驱动器的序列推进到下一个状态（无下一状态时结束）；
        * 字符串名称——直接跳到目标状态（用于遗留处理/快进逻辑）。
        """

    # ------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} name={self.name!r}>"


__all__ = ["WorkflowContext", "WorkflowStateBase", "StateEnum"]
