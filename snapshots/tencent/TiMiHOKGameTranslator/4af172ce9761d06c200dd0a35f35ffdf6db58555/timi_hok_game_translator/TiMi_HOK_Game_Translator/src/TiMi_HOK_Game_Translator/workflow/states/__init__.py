"""内置工作流状态实现。

导入本子包会自动调用
:func:`~TiMi_HOK_Game_Translator.workflow.state_registry.register_state`
对每个内置状态进行注册；第三方插件可采同样方式新增自定义状态。

目录结构——一个状态一个模块，保持完全的产品无关性
（无 Excel 假设、无繁简预处理、无特定通知器）。
"""

from ...commons import WorkflowState as _S
from ..state_registry import register_state
from .finished_state import FinishedState
from .first_review_state import FirstReviewState
from .increment_match_state import IncrementMatchState
from .last_first_review_state import LastFirstReviewState
from .last_merge_data_state import LastMergeDataState
from .last_second_review_state import LastSecondReviewState
from .light_review_state import LightReviewState
from .merge_data_state import MergeDataState
from .pull_vcs_state import PullVcsState
from .push_multi_vcs_state import PushMultiVcsState
from .push_vcs_state import PushVcsState
from .second_review_state import SecondReviewState
from .translate_state import TranslateState
from .update_grn_tm_state import UpdateGrnTmState
from .update_tm_state import UpdateTmState
from .validate_data_state import ValidateDataState

# ---- 将内置状态以标准名称注册到注册表 -------------------------
register_state(_S.PULL_VCS.value, PullVcsState, replace=True)
register_state(_S.PUSH_VCS.value, PushVcsState, replace=True)
register_state(_S.PUSH_MULTI_VCS.value, PushMultiVcsState, replace=True)
register_state(_S.TRANSLATE.value, TranslateState, replace=True)
register_state(_S.LIGHT_REVIEW.value, LightReviewState, replace=True)
register_state(_S.FIRST_REVIEW.value, FirstReviewState, replace=True)
register_state(_S.SECOND_REVIEW.value, SecondReviewState, replace=True)
register_state(_S.LAST_FIRST_REVIEW.value, LastFirstReviewState, replace=True)
register_state(_S.LAST_SECOND_REVIEW.value, LastSecondReviewState, replace=True)
register_state(_S.LAST_MERGE_DATA.value, LastMergeDataState, replace=True)
register_state(_S.MERGE_DATA.value, MergeDataState, replace=True)
register_state(_S.VALIDATE_DATA.value, ValidateDataState, replace=True)
register_state(_S.UPDATE_TM.value, UpdateTmState, replace=True)
register_state(_S.UPDATE_GRN_TM.value, UpdateGrnTmState, replace=True)
register_state(_S.INCREMENT_MATCH.value, IncrementMatchState, replace=True)
register_state(_S.FINISHED.value, FinishedState, replace=True)

# ⚠️ 已移除：``dtxml_merge`` 的 workflow 别名注册
# ---------------------------------------------------------------
# 历史背景：旧版本把 ``dtxml_merge`` 作为 workflow 的一个可选状态注册；
# 自 2026-10-09 起 ``MergeDataState`` 已成为统一实现，``dtxml_merge``
# 别名无实际价值，并会污染前端"状态编排"面板。
# 相关的 ``state_payload["dtxml_merge.*"]`` 兼容 key 由 MergeDataState
# 继续双写（push_vcs 旧实现据此读取），不受本注册移除影响。
# 老的 ``conf/languages/*.yaml`` 若仍在 workflow 中写了 ``dtxml_merge``，
# 需迁移为 ``merge_data``（本次已随 YAML 批量更新同步修复）。

__all__ = [
    "FinishedState",
    "FirstReviewState",
    "IncrementMatchState",
    "LastFirstReviewState",
    "LastMergeDataState",
    "LastSecondReviewState",
    "LightReviewState",
    "MergeDataState",
    "PullVcsState",
    "PushMultiVcsState",
    "PushVcsState",
    "SecondReviewState",
    "TranslateState",
    "UpdateGrnTmState",
    "UpdateTmState",
    "ValidateDataState",
]
