"""单语种配置文件加载器。

扫描一个目录下的配置文件（一个语种一份），将其实例化为
:class:`~TiMi_HOK_Game_Translator.config.schema.LanguageProfile`。

**支持的文件格式**：

* ``.yaml`` / ``.yml``（项目新规范首选，PyYAML 已是硬依赖）
* ``.json``（向后兼容；若同一 id 同时存在 YAML 和 JSON，后扫到的覆盖前者
  并记告警——建议迁移完成后删掉 JSON 旧文件）

YAML 结构示例::

    id: vi
    display_name: Vietnamese
    source_locale: en
    target_locale: vi
    source:
      format: json
      path: strings/vi/en.json
    vcs:
      type: git
      url: "https://..."
    llm:
      provider: openai
      model: gpt-4o-mini
    reviews:
      light:  { platform: none }
      first:  { platform: phrase,  project_id: phrase-uid,
                target_language_id: vi }
      second: { platform: crowdin, project_id: "12345",
                target_language_id: vi }
    workflow:
      - pull_vcs
      - last_first_review
      - last_second_review
      - last_merge_data
      - translate
      - light_review
      - first_review
      - second_review
      - validate_data
      - push_vcs
      - push_multi_vcs
    multi_publish_targets:
      - name: vi-exp mirror
        source_path: exp/strings/vi.json
        use_trunk_vcs: true
    strategy_config:
      display_name: Vietnamese
      max_workers: 5
      returns_english_data: false

加载器故意采用**宽容**策略：

* 配置中缺失的字段使用 dataclass 默认值；
* 未识别的顶层 key 会被收集到 ``extra`` 而不报错；
* 字符串字段中的 ``{workspace}`` / ``{project_root}`` 占位符会在加载时展开；
* 标记 ``disabled: true`` 的文件会被跳过。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..commons import ConfigFileError, ReviewStage
from .schema import (
    LanguageProfile,
    LLMConfig,
    NotificationConfig,
    PublishTarget,
    ReviewConfig,
    SourceConfig,
    VcsConfig,
)

logger = logging.getLogger(__name__)

#: 本模块支持的 profile 文件后缀，按**扫描/优先匹配**顺序。
#: YAML 优先于 JSON——项目新规范首选 YAML，若同一 id 同时存在两份，
#: ``load_language_profiles`` 会告警并以**后扫描到的**为准（与旧实现一致）。
PROFILE_SUFFIXES: tuple[str, ...] = (".yaml", ".yml", ".json")


def _read_profile_data(file_path: Path) -> Dict[str, Any]:
    """按文件后缀读取 profile，返回原始 dict。

    * ``.yaml`` / ``.yml`` → ``yaml.safe_load`` （PyYAML 已是硬依赖）
    * ``.json`` → ``json.loads``
    * 其他后缀 → 退回 JSON 解析（保持最小惊讶，向后兼容）

    任何解析失败都抛 :class:`ConfigFileError`，调用方据此决定是中断还是跳过。
    """
    suffix = file_path.suffix.lower()
    raw_text = file_path.read_text(encoding="utf-8")

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # 局部导入，避免拉高模块导入时间
        except ImportError as exc:  # pragma: no cover - 安装时已硬依赖
            raise ConfigFileError(
                "PyYAML is required to load YAML language profiles. "
                "Install with 'pip install PyYAML'."
            ) from exc
        try:
            data = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as exc:
            raise ConfigFileError(f"Malformed YAML in {file_path}: {exc}") from exc
    else:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ConfigFileError(f"Malformed JSON in {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigFileError(
            f"Top-level value in {file_path} must be a mapping, got "
            f"{type(data).__name__}."
        )
    return data


# ---------------------------------------------------------------------------
# 路径变量展开
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    """返回用作 ``{project_root}`` 的进程当前工作目录。

    故意使用 *cwd* 而非探测安装位置，因为 profile 预期是用户提供的产物，
    它们与用户的 ``config.yaml`` 一同存放。
    """
    return Path.cwd()


def _expand_placeholders(value: Any, workspace: Path) -> Any:
    """递归展开字符串中的 ``{workspace}`` / ``{project_root}``。"""
    if isinstance(value, str):
        return (
            value.replace("{workspace}", str(workspace))
            .replace("{project_root}", str(_project_root()))
        )
    if isinstance(value, list):
        return [_expand_placeholders(item, workspace) for item in value]
    if isinstance(value, dict):
        return {k: _expand_placeholders(v, workspace) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# 子配置区域转换
# ---------------------------------------------------------------------------
def _apply_section(section_cls: type, raw: Any) -> Any:
    """实例化一个 dataclass 区域，容忍未知键与 ``None``。

    参数：
        section_cls: 目标 dataclass（如 :class:`SourceConfig`）。
        raw: 原始 JSON 值（通常为 dict；None 表示使用默认值）。

    返回：
        一个新的 ``section_cls`` 实例。
    """
    if raw is None:
        return section_cls()
    if not isinstance(raw, dict):
        raise ConfigFileError(
            f"Language profile section for {section_cls.__name__} must be an "
            f"object, got {type(raw).__name__}."
        )
    field_names = {f.name for f in fields(section_cls)}
    known = {k: v for k, v in raw.items() if k in field_names}
    unknown = {k: v for k, v in raw.items() if k not in field_names}
    instance = section_cls(**known)
    # 当 dataclass 存在 ``extra`` 字段时，将未知 key 收入其中。
    extra_bucket = getattr(instance, "extra", None)
    if isinstance(extra_bucket, dict) and unknown:
        extra_bucket.update(unknown)
    return instance


def _apply_reviews(raw: Any) -> Dict[str, ReviewConfig]:
    """将 ``reviews`` JSON 块转成 ``stage -> ReviewConfig`` 的 dict。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigFileError(
            f"'reviews' must be an object of stage → config, got {type(raw).__name__}."
        )
    valid_stages = set(ReviewStage.values())
    result: Dict[str, ReviewConfig] = {}
    for stage_name, cfg in raw.items():
        if stage_name not in valid_stages:
            logger.warning(
                "language profile: ignoring unknown review stage %r "
                "(expected one of %s)",
                stage_name,
                sorted(valid_stages),
            )
            continue
        review = _apply_section(ReviewConfig, cfg or {})
        review.stage = stage_name  # 以 key 为准覆盖 stage 字段
        result[stage_name] = review
    return result


def _apply_publish_targets(raw: Any) -> tuple:
    """将 ``multi_publish_targets`` JSON 列表转成 tuple。"""
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ConfigFileError(
            f"'multi_publish_targets' must be a list, got {type(raw).__name__}."
        )
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ConfigFileError(
                "Each 'multi_publish_targets' entry must be an object."
            )
            # 不可达，仅为了让 mypy 满意
        target = _apply_section(PublishTarget, entry)
        # 即使 JSON 传入 list，PublishTarget.stages 也需要是 tuple。
        raw_stages = entry.get("stages")
        if raw_stages:
            target.stages = tuple(str(s) for s in raw_stages)
        items.append(target)
    return tuple(items)


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
def load_language_profile(
    path: str | os.PathLike[str],
    *,
    workspace: Optional[Path] = None,
) -> Optional[LanguageProfile]:
    """加载单个语种配置文件（YAML 或 JSON）。

    按文件后缀自动选路：

    * ``.yaml`` / ``.yml`` → PyYAML 解析（项目新规范首选）；
    * ``.json`` → 标准库 ``json`` 解析（向后兼容旧 profile）。

    参数：
        path: ``<lang>.yaml`` / ``<lang>.yml`` / ``<lang>.json`` 文件路径。
        workspace: 用于展开 ``{workspace}`` 占位符的目录，
            默认为 :func:`Path.cwd`。

    返回：
        一个 :class:`LanguageProfile` 实例；当文件标记 ``disabled: true`` 时返回 ``None``。

    异常：
        ConfigFileError: 文件缺失或解析失败。
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ConfigFileError(f"Language profile file not found: {file_path}")

    raw = _read_profile_data(file_path)

    if raw.get("disabled") is True:
        logger.info("Skipping disabled language profile: %s", file_path)
        return None

    ws = workspace or Path.cwd()
    raw = _expand_placeholders(raw, ws)

    profile_id = raw.get("id") or file_path.stem
    display_name = raw.get("display_name") or profile_id

    # 规范化 locale_names：JSON 允许写 {"cn": "...", "en": "..."}；
    # 其他类型（list / 非字符串 value）直接报错，避免渲染提示词时发现问题。
    raw_names = raw.get("locale_names") or {}
    if not isinstance(raw_names, dict):
        raise ConfigFileError(
            f"'locale_names' in {file_path} must be an object of "
            f"str → str (got {type(raw_names).__name__})."
        )
    locale_names: Dict[str, str] = {}
    for k, v in raw_names.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ConfigFileError(
                f"'locale_names' entries in {file_path} must map str to str; "
                f"got {k!r} → {v!r}."
            )
        locale_names[k.strip().lower()] = v

    profile = LanguageProfile(
        id=profile_id,
        display_name=display_name,
        source_locale=raw.get("source_locale", ""),
        target_locale=raw.get("target_locale", profile_id),
        locale_names=locale_names,
        source=_apply_section(SourceConfig, raw.get("source")),
        vcs=_apply_section(VcsConfig, raw.get("vcs")),
        llm=_apply_section(LLMConfig, raw.get("llm")),
        notification=_apply_section(NotificationConfig, raw.get("notification")),
        reviews=_apply_reviews(raw.get("reviews")),
        workflow=tuple(raw.get("workflow") or ()),
        multi_publish_targets=_apply_publish_targets(raw.get("multi_publish_targets")),
        strategy_config=dict(raw.get("strategy_config") or {}),
        merge_start_time=str(raw.get("merge_start_time", "") or ""),
    )

    # 未识别的顶层 key 全部收集到 profile.extra。
    consumed = {
        "id", "display_name", "source_locale", "target_locale", "locale_names",
        "source", "vcs", "llm", "notification",
        "reviews", "workflow", "multi_publish_targets", "strategy_config",
        "merge_start_time",
        "disabled",
    }
    for key, value in raw.items():
        if key not in consumed:
            profile.extra[key] = value

    return profile


def load_language_profiles(
    languages_dir: str | os.PathLike[str],
    *,
    workspace: Optional[Path] = None,
) -> Dict[str, LanguageProfile]:
    """加载 ``languages_dir`` 下所有 YAML / JSON 文件，返回以 id 为键的 dict。

    文件掂描顺序：先 YAML（``.yaml`` → ``.yml``）再 JSON（``.json``），
    同后缀下按文件名字典序掂描。若两个文件声明相同 id，则后掂描
    到的覆盖前者并记告警（向后兼容旧行为）。建议迁移到 YAML 后
    **删掉同 id 的旧 JSON 文件**，避免走覆盖路径。

    参数：
        languages_dir: 存放各语种 profile 的目录。不存在时视为“无 profile”，
            返回空 dict（并记 debug 日志）。
        workspace: 透传给 :func:`load_language_profile`。

    返回：
        以 :attr:`LanguageProfile.id` 为键的 dict。
    """
    dir_path = Path(languages_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        logger.debug("Language profile directory does not exist: %s", dir_path)
        return {}

    # 按 PROFILE_SUFFIXES 顺序展开文件列表，同后缀内按文件名字典序排序。
    profile_files: list[Path] = []
    for suffix in PROFILE_SUFFIXES:
        profile_files.extend(sorted(dir_path.glob(f"*{suffix}")))

    result: Dict[str, LanguageProfile] = {}
    for profile_file in profile_files:
        try:
            profile = load_language_profile(profile_file, workspace=workspace)
        except ConfigFileError:
            logger.exception("Failed to load language profile: %s", profile_file)
            raise
        if profile is None:
            continue
        if profile.id in result:
            logger.warning(
                "Duplicate language id %r — %s overrides earlier definition",
                profile.id, profile_file,
            )
        result[profile.id] = profile

    logger.info(
        "Loaded %d language profile(s) from %s: %s",
        len(result), dir_path, sorted(result.keys()),
    )
    return result


def attach_language_profiles(config: Any) -> None:
    """从 :attr:`Config.languages_dir` 填充 :attr:`Config.languages`。

    路径解析顺序：

    1. ``Config.languages_dir`` 非空——使用该路径（相对路径以当前 cwd 为基准）。
       本仓库日常用法：在 ``conf/config.yaml`` 中显式写
       ``languages_dir: conf/languages``。
    2. 否则回落到约定默认目录 ``<cwd>/configs/languages``，
       以保证未配置任何 YAML 的 demo 场景也能开箱即用。
    """
    if not is_dataclass(config):
        return

    dir_hint = getattr(config, "languages_dir", "") or ""
    workspace = config.workspace_path() if hasattr(config, "workspace_path") else None

    if dir_hint:
        candidate = Path(dir_hint).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
    else:
        candidate = Path.cwd() / "configs" / "languages"

    if not candidate.exists():
        return

    profiles = load_language_profiles(candidate, workspace=workspace)
    if profiles:
        config.languages = profiles
        # 记录实际使用的目录，供 `config dump` 以及辅助工具展示。
        config.languages_dir = str(candidate)


__all__ = [
    "load_language_profile",
    "load_language_profiles",
    "attach_language_profiles",
]
