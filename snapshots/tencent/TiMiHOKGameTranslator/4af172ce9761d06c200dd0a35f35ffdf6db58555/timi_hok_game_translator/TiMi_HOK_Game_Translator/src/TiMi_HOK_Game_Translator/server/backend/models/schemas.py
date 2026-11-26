"""Pydantic 模型。

为了对前端最大限度宽松（允许直接编辑原始 YAML 结构），
大部分配置块使用 ``Dict[str, Any]``，由后端服务层做最小的字段兜底。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "缺少 pydantic。请执行 pip install fastapi uvicorn[standard]"
    ) from exc


# =============================================================================
# Setup / 初始化
# =============================================================================
class SetupStatusModel(BaseModel):
    """初始化状态。"""

    initialized: bool = Field(..., description="是否已完成初始化")
    config_yaml_exists: bool = False
    llm_yaml_exists: bool = False
    languages_count: int = 0
    missing_fields: List[str] = Field(default_factory=list, description="全局配置中仍缺失的关键字段")


class InitSetupRequest(BaseModel):
    """首次初始化请求体。"""

    config: Dict[str, Any] = Field(..., description="conf/config.yaml 的完整内容")
    llm: Dict[str, Any] = Field(..., description="conf/llm.yaml 的完整内容")


# =============================================================================
# 全局配置 / LLM
# =============================================================================
class GlobalConfigModel(BaseModel):
    """conf/config.yaml 内容（宽松模型）。"""

    data: Dict[str, Any] = Field(default_factory=dict)


class LLMProfileModel(BaseModel):
    """单个 LLM profile。"""

    name: str
    provider: str
    model: str = ""
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 1024
    batch_size: int = 16
    timeout_seconds: int = 60
    retries: int = 3
    retry_interval_seconds: int = 10
    extra: Dict[str, Any] = Field(default_factory=dict)


class LLMRegistryModel(BaseModel):
    """conf/llm.yaml 内容。"""

    default: str = ""
    profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


# =============================================================================
# 语种 profile
# =============================================================================
class LanguageProfileModel(BaseModel):
    """conf/languages/<lang>.yaml 内容。"""

    id: str = Field(..., description="语种短 ID，与文件名一致（例如 vi、ja、ko）")
    data: Dict[str, Any] = Field(default_factory=dict, description="完整 YAML 内容")


# =============================================================================
# 运行 / 调度
# =============================================================================
class RunStartRequest(BaseModel):
    language: str = Field(..., description="要运行的语种 ID")
    fresh: bool = False
    batch: Optional[str] = None
    stage: Optional[str] = None


class RunInfoModel(BaseModel):
    run_id: str
    language: str
    status: str  # running | finished | failed | killed
    started_at: str
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    fresh: bool = False
    batch: Optional[str] = None
    log_file: Optional[str] = None


class ScheduleModel(BaseModel):
    """一个定时任务。"""

    id: str = Field(..., description="调度 ID，唯一")
    language: str
    cron: str = Field(..., description="标准 5 字段 cron 表达式：分 时 日 月 周")
    enabled: bool = True
    fresh: bool = False
    description: str = ""
