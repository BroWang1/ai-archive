"""``/api/meta`` —— 把枚举（VCS 类型、LLM provider、workflow 状态等）
全部暴露给前端做下拉选项，避免魔法字符串硬编码。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


# -----------------------------------------------------------------------------
# Workflow 状态的中文描述与推荐分组。前端用它渲染"状态编排"面板。
# key 必须与 :class:`WorkflowState` 的 value 完全一致。
#
# ⚠️ 顺序即推荐执行顺序：pull_vcs → ... → push_vcs。
# ⚠️ 以下状态**不在此列表中**，因为它们**不参与用户编排**：
#   - pending / finished / failed —— 运行时生命周期状态，由 StatesManager 自动流转
#   - increment_match / dtxml_merge —— 翻译器内部状态，无独立 state 类定义
# -----------------------------------------------------------------------------
_WORKFLOW_STATE_META = [
    # (key, 中文名, 简短说明, 分组, 是否推荐默认启用)
    ("pull_vcs",           "拉取源文件",       "从 VCS/本地读取最新源文件",             "版本控制",   True),
    ("last_first_review",  "上轮一审遗留处理", "拉取上一批次仍挂在平台的一审任务结果", "上一轮遗留", True),
    ("last_second_review", "上轮二审遗留处理", "拉取上一批次仍挂在平台的二审任务结果", "上一轮遗留", True),
    ("last_merge_data",    "上轮数据合并",     "把上一批次的译文合并回主表",             "上一轮遗留", True),
    ("translate",          "LLM 机器翻译",     "调用大模型批量翻译增量条目",             "翻译",       True),
    ("update_tm",          "一审 TM 回灌",     "历史已审译文灌回一审平台 TM",            "翻译记忆",   True),
    ("update_grn_tm",      "二审 TM 回灌",     "历史已审译文灌回二审平台 TM",            "翻译记忆",   True),
    ("light_review",       "轻校对",           "快速人工 QA（可选，无需平台）",          "审校",       False),
    ("first_review",       "一审",             "推送到一审平台，等待语言质检",           "审校",       True),
    ("second_review",      "二审",             "推送到二审平台，等待终审出稿",           "审校",       True),
    ("validate_data",      "数据校验",         "对最终译文做占位符/长度等结构性校验",     "数据装配",   True),
    ("merge_data",         "数据合并",         "把译文合并回最终导出表",                "数据装配",   True),
    ("push_vcs",           "推送到 VCS",       "把结果提交到仓库 / 落回本地目录",         "版本控制",   True),
    ("push_multi_vcs",     "多仓库推送",       "一次性把结果推送到多个 VCS 后端",         "版本控制",   False),
]

# 不该暴露给"状态编排"面板的内部 / 生命周期状态
_WORKFLOW_STATE_HIDDEN = {
    "pending", "finished", "failed",
    "increment_match", "dtxml_merge",
}


@router.get("")
async def meta():
    from ....commons.enums import (
        LLMProvider,
        LogLevel,
        NotifierType,
        PlatformType,
        ReviewStage,
        SourceFormat,
        Stage,
        VcsType,
        WorkflowState,
    )
    from ....workflow.state_registry import registered_state_names

    registered = set(registered_state_names())
    # 按预设顺序输出带中文标签的清单；只保留实际注册的状态
    workflow_states_meta = []
    seen = set()
    for key, label, desc, group, recommended in _WORKFLOW_STATE_META:
        if key in registered:
            workflow_states_meta.append({
                "key": key,
                "label": label,
                "desc": desc,
                "group": group,
                "recommended": recommended,
            })
            seen.add(key)
    # 兜底：第三方 register_state 注册的额外状态也追加到末尾
    # —— 但排除生命周期状态（pending/finished/failed）和内部状态
    #    （increment_match/dtxml_merge），它们不应出现在用户的"状态编排"面板。
    for key in sorted(registered - seen - _WORKFLOW_STATE_HIDDEN):
        workflow_states_meta.append({
            "key": key,
            "label": key,
            "desc": "（第三方注册状态）",
            "group": "其他",
            "recommended": False,
        })

    return {
        "vcs_types": VcsType.values(),
        "source_formats": SourceFormat.values(),
        "llm_providers": LLMProvider.values(),
        "platform_types": PlatformType.values(),
        "review_stages": ReviewStage.values(),
        "notifier_types": NotifierType.values(),
        "stages": Stage.values(),
        "log_levels": LogLevel.values(),
        "workflow_states": sorted(registered_state_names()),
        "workflow_states_canonical": WorkflowState.values(),
        "workflow_states_meta": workflow_states_meta,
    }
