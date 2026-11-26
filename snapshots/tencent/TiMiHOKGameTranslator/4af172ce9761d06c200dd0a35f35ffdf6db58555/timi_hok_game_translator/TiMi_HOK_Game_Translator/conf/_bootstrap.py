"""conf 层的 LLM profile 粘合器。

作用：
    1) 把 config.yaml / 语种 profile 里的 ``llm_profile: <name>`` 字符串
       展开成 conf/llm.yaml 中对应 profile 的完整 LLM 参数；
    2) 对 ``vcs`` / ``source`` 做**字段级合并**（而不是 src/TiMi_HOK_Game_Translator/cli.py
       的「整段替换」）：全局 config 提供项目恒定字段（vcs.type、vcs.username、
       source.format、source.encoding 等），语种 profile 只写按语种差异的字段
       （vcs.url、vcs.local_path、source.path）。

设计目标：
    - 不修改 src/TiMi_HOK_Game_Translator/ 任何代码；
    - 对框架透明——粘合完成后，``Config``/``LanguageProfile`` 的字段
      与直接写满参数的效果完全等价；
    - 项目上线/开源时 ``conf/`` 目录保留（_bootstrap 等粘合代码运行时使用），
      仅清理 ``config.yaml`` / ``languages/*.json`` 中的真实敏感值
      （账号密码、API token、分支 URL 等），替换为占位符或改为环境变量注入。

使用方式：
    from conf._bootstrap import load_config_with_llm_profiles
    config = load_config_with_llm_profiles("conf/config.yaml")
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Optional

from TiMi_HOK_Game_Translator.commons import ConfigFileError
from TiMi_HOK_Game_Translator.config.loader import load as _framework_load
from TiMi_HOK_Game_Translator.config.schema import (
    Config,
    LanguageProfile,
    LLMConfig,
    SourceConfig,
    VcsConfig,
)

_DEFAULT_LLM_REGISTRY = Path(__file__).resolve().parent / "llm.yaml"
_DEFAULT_CONFIG_YAML = Path(__file__).resolve().parent / "config.yaml"


def _read_llm_registry(path: Path) -> Dict[str, Any]:
    """读取并解析 llm.yaml 注册表。

    参数：
        path: llm.yaml 的绝对路径。
    返回：
        包含 ``default`` 与 ``profiles`` 两个键的 dict。
    """
    if not path.exists():
        raise ConfigFileError(f"LLM registry not found: {path}")
    import yaml  # 延迟导入，避免引入副作用
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigFileError(f"Top-level value in {path} must be a mapping.")
    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise ConfigFileError(f"'profiles' in {path} must be a mapping.")
    return {"default": data.get("default", ""), "profiles": profiles}


def _dict_to_llm_config(name: str, raw: Dict[str, Any]) -> LLMConfig:
    """把 YAML 中的一段 profile dict 转成 ``LLMConfig`` 实例。

    参数：
        name: profile 名称，仅用于错误提示。
        raw: 从 llm.yaml 读到的参数字典。
    返回：
        填充好字段的 ``LLMConfig``；未识别的键进入 ``extra``。
    """
    if not isinstance(raw, dict):
        raise ConfigFileError(f"LLM profile '{name}' must be a mapping.")
    field_names = {f.name for f in fields(LLMConfig)}
    known = {k: v for k, v in raw.items() if k in field_names and k != "extra"}
    unknown = {k: v for k, v in raw.items() if k not in field_names}
    cfg = LLMConfig(**known)
    base_extra = raw.get("extra") or {}
    if isinstance(base_extra, dict):
        cfg.extra.update(base_extra)
    if unknown:
        cfg.extra.update(unknown)
    return cfg


def _resolve_profile_name(
    registry: Dict[str, Any],
    requested: str,
    *,
    scope: str,
) -> LLMConfig:
    """按名在注册表里找 profile；找不到抛明确错误。

    参数：
        registry: ``_read_llm_registry`` 返回的 dict。
        requested: 配置里出现的 profile 名称。
        scope: 调用位置描述（如 ``'global config'`` 或 ``'profile vi'``），
            用于错误信息。
    返回：
        对应的 ``LLMConfig``。
    """
    profiles = registry["profiles"]
    if requested not in profiles:
        available = sorted(profiles.keys())
        # 用 difflib 给出相似名建议——用户常见拼错（漏写 _plus / 多余后缀 /
        # 大小写等），这里把"你是不是想写 xxx"直接写进错误消息，省得翻 YAML。
        import difflib
        suggestions = difflib.get_close_matches(requested, available, n=3, cutoff=0.6)
        hint = (
            f" 你是不是想写：{suggestions}？"
            if suggestions else ""
        )
        raise ConfigFileError(
            f"[{scope}] llm_profile '{requested}' not found in conf/llm.yaml.{hint} "
            f"Available: {available}"
        )
    return _dict_to_llm_config(requested, profiles[requested])


def _apply_global_llm(config: Config, registry: Dict[str, Any]) -> None:
    """把全局 llm_profile 展开写入 ``config.llm``。

    参数：
        config: 已由框架加载完成的 ``Config``。
        registry: llm 注册表。
    返回：
        None（就地修改）。
    """
    # 顶层未识别字段 llm_profile 会被 loader 收进 Config.extra
    name = str(config.extra.pop("llm_profile", "") or registry["default"] or "")
    if not name:
        return  # 用户没指定、也没有 default，保持 src 默认值
    config.llm = _resolve_profile_name(registry, name, scope="global config")


def _apply_language_llm(
    profile: LanguageProfile, registry: Dict[str, Any], fallback: LLMConfig,
) -> None:
    """为单个语种 profile 展开 llm_profile；没写则沿用全局配置。

    参数：
        profile: 单语种 profile。
        registry: llm 注册表。
        fallback: 全局 llm 配置（当语种未指定 llm_profile 时直接复用）。
    返回：
        None（就地修改）。
    """
    name = str(profile.extra.pop("llm_profile", "") or "")
    if name:
        profile.llm = _resolve_profile_name(
            registry, name, scope=f"profile {profile.id}",
        )
    else:
        # 关键：显式复制一份全局 llm 给 profile，避免 cli.py 的
            # fallback 分支因 profile.llm.provider 默认 'echo' 而被误判。
        profile.llm = _copy_llm(fallback)

    # 把语种 JSON 顶层的 locale_names 透传进 profile.llm.extra，
    # 供 provider 构造提示词时覆盖内置的中/英文语种名字典。
    if profile.locale_names:
        profile.llm.extra["locale_names"] = dict(profile.locale_names)


def _copy_llm(src: LLMConfig) -> LLMConfig:
    """浅拷贝 ``LLMConfig``（含 extra dict）。"""
    copy = LLMConfig(
        provider=src.provider,
        model=src.model,
        temperature=src.temperature,
        max_tokens=src.max_tokens,
        batch_size=src.batch_size,
        timeout_seconds=src.timeout_seconds,
        retries=src.retries,
        retry_interval_seconds=src.retry_interval_seconds,
        api_key=src.api_key,
        api_base=src.api_base,
    )
    copy.extra.update(src.extra)
    return copy


# ---------------------------------------------------------------------------
# VCS / Source 的字段级合并
# ---------------------------------------------------------------------------
# cli.py 对 profile.vcs / profile.source 是「整段替换」（全有或全无）：
# 一旦 profile.vcs.type / profile.source.path 为空就整段丢弃。那种模式
# 要求每个语种 profile 把 vcs.type / source.format 等项目恒定字段重复
# 写一遍，噪声且易错。
#
# 这里改为：先拿全局配置做基线，再把 profile 里显式写了的字段叠加上去。
# 这样 vi.json 只需写 { "vcs": {"url": "..."} } 就能复用全局的 type/username
# 等参数。
_VCS_DEFAULTS = VcsConfig()
_SOURCE_DEFAULTS = SourceConfig()


def _merge_vcs(global_vcs: VcsConfig, profile_vcs: VcsConfig) -> VcsConfig:
    """按字段把 ``profile_vcs`` 的非默认值叠加到 ``global_vcs`` 之上。

    参数：
        global_vcs: 来自 config.yaml 的全局 vcs 配置。
        profile_vcs: 来自语种 profile 的 vcs 配置（可能只写了部分字段）。
    返回：
        合并后的新 ``VcsConfig``；原始对象均不被修改。
    """
    merged = VcsConfig(
        type=global_vcs.type,
        url=global_vcs.url,
        revision=global_vcs.revision,
        local_path=global_vcs.local_path,
        username=global_vcs.username,
        password=global_vcs.password,
        cli_timeout_seconds=global_vcs.cli_timeout_seconds,
        default_commit_message=global_vcs.default_commit_message,
    )
    merged.extra.update(global_vcs.extra)

    for f in fields(VcsConfig):
        if f.name == "extra":
            continue
        profile_value = getattr(profile_vcs, f.name)
        default_value = getattr(_VCS_DEFAULTS, f.name)
        # 仅当 profile 显式写了（即与 schema 默认值不同）才覆盖。
        if profile_value != default_value:
            setattr(merged, f.name, profile_value)
    if profile_vcs.extra:
        merged.extra.update(profile_vcs.extra)
    return merged


def _merge_source(
    global_source: SourceConfig, profile_source: SourceConfig,
) -> SourceConfig:
    """按字段把 ``profile_source`` 叠加到 ``global_source`` 之上。

    参数：
        global_source: 来自 config.yaml 的全局 source 配置。
        profile_source: 来自语种 profile 的 source 配置。
    返回：
        合并后的新 ``SourceConfig``。

    .. note::
        **扩展名推断兜底**：由于 ``SourceConfig`` 的字段级合并用
        "值 != dataclass 默认值" 判断是否覆盖，当 profile 显式写
        ``"format": "json"`` 而 schema 默认值恰好也是 ``"json"`` 时，会被误
        判为"没显式写"，导致全局 ``format: dtxml`` 继续生效 ——
        造成"读 json 文件却用 DtxmlSource 解析"的致命错误。

        修复：合并完成后，若 ``merged.path`` 与 ``merged.format`` 的扩展名
        明显不符（例如 ``path="...99.incr.json"`` 但 ``format="dtxml"``），
        用 ``path`` 的扩展名重新推断 format。这既是对配置漂移的兜底，也
        让 "切 profile.source.path 后缀就能切 format" 成为真实能力。
    """
    merged = SourceConfig(
        format=global_source.format,
        path=global_source.path,
        encoding=global_source.encoding,
    )
    merged.extra.update(global_source.extra)
    for f in fields(SourceConfig):
        if f.name == "extra":
            continue
        profile_value = getattr(profile_source, f.name)
        default_value = getattr(_SOURCE_DEFAULTS, f.name)
        # 仅当 profile 显式写了（即与 schema 默认值不同）才覆盖。
        if profile_value != default_value:
            setattr(merged, f.name, profile_value)
    if profile_source.extra:
        merged.extra.update(profile_source.extra)

    # 关键兜底：按 merged.path 的扩展名重新推断 format，
    # 当 (path 扩展名有对应 format) 且 (该推断值与当前 merged.format 不同)
    # 时触发——避免"path 换了但 format 字段因 dataclass 默认值陷阱保留旧值"。
    inferred = _infer_format_from_path(merged.path)
    if inferred and inferred != merged.format:
        merged.format = inferred
    return merged


#: 常见 source 文件扩展名 → format 名的映射。
#: 源于 ``TiMi_HOK_Game_Translator.sources`` 已注册的 format 工厂。
_EXT_TO_SOURCE_FORMAT: Dict[str, str] = {
    ".dtxml": "dtxml",
    ".json": "json",
    ".xliff": "xliff",
    ".xlf": "xliff",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
}


def _infer_format_from_path(path: str) -> Optional[str]:
    """按文件扩展名推断 source format；无法识别时返回 ``None``。

    参数：
        path: ``source.path`` 字段值（可能带目录前缀）。
    返回：
        format 名（如 ``"json"``）或 ``None``。
    """
    if not path:
        return None
    ext = Path(path).suffix.lower()
    return _EXT_TO_SOURCE_FORMAT.get(ext)


def _apply_language_vcs_source(
    profile: LanguageProfile, config: Config,
) -> None:
    """为单个语种 profile 合并 vcs 与 source。

    参数：
        profile: 单语种 profile（就地修改）。
        config: 全局配置，提供基线字段。
    返回：
        None。
    """
    profile.vcs = _merge_vcs(config.vcs, profile.vcs)
    profile.source = _merge_source(config.source, profile.source)


def load_config_with_llm_profiles(
    config_path: Optional[str | Path] = None,
    *,
    llm_registry_path: Optional[Path] = None,
    cli_args: Any = None,
    environ: Optional[Dict[str, str]] = None,
) -> Config:
    """加载 config 并把 llm_profile 名称展开成完整参数。

    参数：
        config_path: ``conf/config.yaml`` 路径；为 ``None`` 时按以下顺序兜底：
            ① ``cli_args.config``（``-c/--config`` 命令行参数）；
            ② ``GAME_TRANS_TOOLCHAIN_CONFIG`` 环境变量；
            ③ 本仓库同目录下的 ``conf/config.yaml``。
        llm_registry_path: 自定义 llm.yaml 位置；默认 conf/llm.yaml。
        cli_args: 可选，透传给框架 loader。
        environ: 可选，透传给框架 loader（测试用）。
    返回：
        经过 llm_profile 展开的 ``Config``；可直接交给
        ``TiMi_HOK_Game_Translator.cli._run`` 使用。
    """
    resolved = _resolve_config_path(config_path, cli_args, environ)
    config = _framework_load(
        config_path=str(resolved) if resolved else None,
        cli_args=cli_args,
        environ=environ,
    )
    registry = _read_llm_registry(llm_registry_path or _DEFAULT_LLM_REGISTRY)
    _apply_global_llm(config, registry)
    for profile in config.languages.values():
        _apply_language_llm(profile, registry, fallback=config.llm)
        _apply_language_vcs_source(profile, config)
    return config


def _resolve_config_path(
    explicit: Optional[str | Path],
    cli_args: Any,
    environ: Optional[Dict[str, str]],
) -> Optional[Path]:
    """按优先级选出要加载的 config.yaml 路径；均缺失时返回 ``None``。

    参数：
        explicit: 调用方显式传入的路径。
        cli_args: argparse namespace；读取其中的 ``config`` 属性。
        environ: 可选自定义环境变量字典。
    返回：
        实际存在的 YAML 路径，或 ``None`` 让框架 loader 自己回落默认行为。
    """
    import os

    if explicit:
        return Path(explicit).expanduser().resolve()

    if cli_args is not None:
        cli_path = getattr(cli_args, "config", None)
        if cli_path:
            return Path(cli_path).expanduser().resolve()

    src = environ if environ is not None else os.environ
    env_path = src.get("GAME_TRANS_TOOLCHAIN_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if _DEFAULT_CONFIG_YAML.exists():
        return _DEFAULT_CONFIG_YAML
    return None


__all__ = ["load_config_with_llm_profiles"]
