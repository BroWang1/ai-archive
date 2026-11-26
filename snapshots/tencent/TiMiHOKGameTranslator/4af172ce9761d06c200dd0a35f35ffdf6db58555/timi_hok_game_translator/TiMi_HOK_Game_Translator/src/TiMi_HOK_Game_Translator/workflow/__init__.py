"""TiMi_HOK_Game_Translator.workflow——基于状态机的流水线。

对外 API::

    from TiMi_HOK_Game_Translator.workflow import (
        WorkflowContext, WorkflowStateBase,
        StatesManager, AutoSaveDict,
        WorkflowRunner,
        register_state, build_state, build_workflow, registered_state_names,
    )

导入本包时会自动通过 :mod:`TiMi_HOK_Game_Translator.workflow.states` 注册内置 17 个状态。
"""

# 导入内置状态包，依靠其副作用完成自动注册。
from . import states as _bundled_states  # noqa: F401
from .auto_save_dict import AutoSaveDict
from .runner import WorkflowRunner
from .state import WorkflowContext, WorkflowStateBase
from .state_registry import (
    build_state,
    build_workflow,
    register_state,
    registered_state_names,
    unregister_state,
)
from .states_manager import StatesManager

__all__ = [
    "AutoSaveDict",
    "StatesManager",
    "WorkflowContext",
    "WorkflowRunner",
    "WorkflowStateBase",
    "build_state",
    "build_workflow",
    "register_state",
    "registered_state_names",
    "unregister_state",
]
