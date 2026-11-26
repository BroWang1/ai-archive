"""项目级常量。

**判断准则**：如果一个字面量被多个模块引用，或者它代表一个"离开上下文
也能理解含义"的可调项，就应放在本文件（或 :mod:`TiMi_HOK_Game_Translator.commons.enums`）。

**不要**把面向用户的可配置项放在这里 —— 那些应写入 ``config.example.yaml``。
本模块只承载真正不变的常量（默认重试次数、约定 key 等）。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 包身份标识
# ---------------------------------------------------------------------------
APP_NAME: str = "TiMi_HOK_Game_Translator"
CLI_COMMAND: str = "TiMi_HOK_Game_Translator"

# 环境变量前缀，用于自动映射到 Config 对象。
# 例如 GAME_TRANS_TOOLCHAIN__VCS__TYPE 会覆盖 ``config.vcs.type``。
ENV_PREFIX: str = "GAME_TRANS_TOOLCHAIN"
ENV_NESTED_DELIMITER: str = "__"

# ---------------------------------------------------------------------------
# 文件系统默认值
# ---------------------------------------------------------------------------
DEFAULT_CONFIG_FILENAME: str = "config.yaml"
DEFAULT_ENV_FILENAME: str = ".env"
DEFAULT_WORKSPACE_DIRNAME: str = "workspace"
DEFAULT_STATE_FILENAME: str = "workflow_state.json"
DEFAULT_LOG_DIRNAME: str = "logs"

# ---------------------------------------------------------------------------
# 网络重试默认值（供基于 HTTP 的平台 / 通知客户端使用）
# ---------------------------------------------------------------------------
DEFAULT_HTTP_TIMEOUT_SECONDS: int = 30
DEFAULT_HTTP_RETRIES: int = 3
DEFAULT_HTTP_RETRY_INTERVAL_SECONDS: int = 30

# ---------------------------------------------------------------------------
# VCS 默认值
# ---------------------------------------------------------------------------
DEFAULT_VCS_COMMIT_MESSAGE: str = "[TiMi_HOK_Game_Translator] commit translation data"
DEFAULT_VCS_CLI_TIMEOUT_SECONDS: int = 600

# ---------------------------------------------------------------------------
# 密钥扫描 / 脱敏
# ---------------------------------------------------------------------------
# 需要在 ``dump`` / 日志中脱敏的字段名，每一项都是**完整**字段名（大小写不敏感）。
# 出现新的携带凭据的字段时，请追加到此列表。
SENSITIVE_FIELD_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "webhook",
    "api_token",
)
SENSITIVE_MASK: str = "***"

# ---------------------------------------------------------------------------
# LLM 默认值
# ---------------------------------------------------------------------------
DEFAULT_LLM_TEMPERATURE: float = 0.2
DEFAULT_LLM_MAX_TOKENS: int = 1024
DEFAULT_LLM_BATCH_SIZE: int = 32

# ---------------------------------------------------------------------------
# 工作流默认值
# ---------------------------------------------------------------------------
DEFAULT_STATE_POLL_INTERVAL_SECONDS: int = 5

# ---------------------------------------------------------------------------
# 审校轮询默认值
# ---------------------------------------------------------------------------
#: ``first_review`` / ``second_review`` 轮询 Crowdin 任务状态的默认间隔秒数。
#: 可通过 ``ReviewConfig.poll_interval_seconds`` 在 ``conf/languages/*.json`` 覆盖。
DEFAULT_REVIEW_POLL_INTERVAL_SECONDS: int = 1800
