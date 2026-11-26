"""分层配置加载器。

优先级（后面的覆盖前面的）：

1. :mod:`TiMi_HOK_Game_Translator.config.schema` 中声明的内置默认值；
2. ``config.yaml``（路径受 ``--config`` 命令行参数或
   ``GAME_TRANS_TOOLCHAIN_CONFIG`` 环境变量控制）；
3. 以 ``GAME_TRANS_TOOLCHAIN__`` 为前缀的环境变量，嵌套 key 以 ``__`` 分隔
   （例如 ``GAME_TRANS_TOOLCHAIN__VCS__PASSWORD``）；
4. 由 :func:`build_argparser` 解析的命令行参数——argparse 参数名与
   schema 字段对应（如 ``--vcs.type``）。

必填字段在加载时**不会**直接报错；调用方可调用 :func:`validate`
一次性拿到所有问题。这样可以让 ``TiMi_HOK_Game_Translator config dump`` 在配置不完整时仍然导出便于调试。
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TypeVar

from ..commons import (
    APP_NAME,
    CLI_COMMAND,
    DEFAULT_CONFIG_FILENAME,
    ENV_NESTED_DELIMITER,
    ENV_PREFIX,
    ConfigFileError,
    MissingRequiredConfigError,
)
from .schema import Config

T = TypeVar("T")  # pylint: disable=invalid-name

_ENV_CONFIG_PATH_KEY = f"{ENV_PREFIX}_CONFIG"


# ---------------------------------------------------------------------------
# Layer 1 — 默认值
# ---------------------------------------------------------------------------
def _default_config() -> Config:
    """返回一个使用 schema 默认值初始化的 :class:`Config`。"""
    return Config()


# ---------------------------------------------------------------------------
# Layer 2 — YAML 文件
# ---------------------------------------------------------------------------
def _load_yaml_file(path: Path) -> Dict[str, Any]:
    """解析 ``path`` 处的 YAML 文件。

    异常：
        ConfigFileError: 文件不存在或格式错误时抛出。
    """
    if not path.exists():
        raise ConfigFileError(f"Config file not found: {path}")

    try:
        import yaml  # 局部导入，避免拉高模块导入时间
    except ImportError as exc:  # pragma: no cover - 安装时已硬依赖
        raise ConfigFileError(
            "PyYAML is required to load YAML config files. "
            "Install with 'pip install PyYAML'."
        ) from exc

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigFileError(f"Malformed YAML at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigFileError(
            f"Top-level YAML value in {path} must be a mapping, got {type(data).__name__}."
        )
    return data


# ---------------------------------------------------------------------------
# Layer 3 — 环境变量
# ---------------------------------------------------------------------------
def _env_overrides(environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """收集环境变量覆盖项为与 schema 具同构型的嵌套 dict。

    示例::

        GAME_TRANS_TOOLCHAIN__VCS__PASSWORD=hunter2
        →  {"vcs": {"password": "hunter2"}}
    """
    src = environ if environ is not None else os.environ
    prefix = f"{ENV_PREFIX}{ENV_NESTED_DELIMITER}"
    result: Dict[str, Any] = {}
    for key, value in src.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):].split(ENV_NESTED_DELIMITER)
        _set_nested(result, [p.lower() for p in path], value)
    return result


def _set_nested(target: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    """将 ``value`` 写入 ``target`` 中的 ``path`` 位置，途中需要的 dict 会自动创建。"""
    cursor: Dict[str, Any] = target
    for key in path[:-1]:
        nxt = cursor.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[key] = nxt
        cursor = nxt
    cursor[path[-1]] = value


# ---------------------------------------------------------------------------
# Layer 4 — CLI
# ---------------------------------------------------------------------------
def build_argparser(prog: str = CLI_COMMAND) -> argparse.ArgumentParser:
    """返回 ``run`` / ``config dump`` 子命令的命令行解析器。

    只暴露最常用的 schema 字段；其余字段仍可通过环境变量/YAML 提供。
    """
    parser = argparse.ArgumentParser(prog=prog, description=f"{APP_NAME} command-line interface.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the localization pipeline.")
    _add_common_arguments(run_parser)
    run_parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete any previously persisted workflow state before running "
             "(mutually exclusive with --batch).",
    )
    run_parser.add_argument(
        "--batch",
        dest="batch",
        default=None,
        metavar="BATCH_NAME",
        help="Resume a previous batch by name (e.g. 'vi_20261008204338'). "
             "The runner will load archived state from "
             "workspace/batches/<BATCH_NAME>/_archive/ and continue from the "
             "first incomplete state. Mutually exclusive with --fresh.",
    )

    dump_parser = subparsers.add_parser(
        "config",
        help="Configuration utilities (dump the effective configuration).",
    )
    dump_sub = dump_parser.add_subparsers(dest="config_command")
    dump_cmd = dump_sub.add_parser("dump", help="Print the effective configuration.")
    _add_common_arguments(dump_cmd)
    dump_cmd.add_argument(
        "--format", choices=["yaml", "json"], default="yaml",
        help="Output format for 'config dump' (default: yaml).",
    )
    dump_cmd.add_argument(
        "--no-mask", action="store_true",
        help="Do not mask sensitive fields (DANGEROUS — only for local debugging).",
    )
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", "-c", default=None, help="Path to config.yaml.")
    parser.add_argument("--project-code", default=None)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--source-locale", default=None)
    parser.add_argument("--target-locale", default=None)
    parser.add_argument(
        "--language",
        dest="language",
        default=None,
        help="Language id to run (matches a LanguageProfile.id).",
    )
    parser.add_argument(
        "--languages-dir",
        dest="languages_dir",
        default=None,
        help="Directory to scan for per-language profile JSON files.",
    )
    parser.add_argument("--vcs-type", dest="vcs__type", default=None)
    parser.add_argument("--vcs-url", dest="vcs__url", default=None)
    parser.add_argument("--vcs-revision", dest="vcs__revision", default=None)
    parser.add_argument("--source-format", dest="source__format", default=None)
    parser.add_argument("--source-path", dest="source__path", default=None)
    parser.add_argument("--llm-provider", dest="llm__provider", default=None)
    parser.add_argument("--log-level", dest="logging__level", default=None)


def _cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """将 argparse namespace 转为嵌套的覆盖 dict。"""
    result: Dict[str, Any] = {}
    for key, value in vars(args).items():
        if value is None:
            continue
        if key in {"command", "config_command", "format", "no_mask", "config", "fresh", "batch"}:
            continue
        # 将平铺的 ``vcs__type`` 转为嵌套 {"vcs": {"type": ...}}。
        path = [p.replace("-", "_") for p in key.split(ENV_NESTED_DELIMITER.lower())]
        # 同时保留顶层扁平参数（如 ``project_code``）。
        if len(path) == 1:
            path = [path[0]]
        _set_nested(result, path, value)
    return result


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def _merge_into_dataclass(instance: Any, overrides: Dict[str, Any]) -> None:
    """就地将 ``overrides`` 合并到 dataclass ``instance``。

    字段类型会尽量自动转换：环境/CLI 传入的值都是字符串，
    会根据字段声明的 ``bool`` / ``int`` / ``float`` / ``list`` 进行转换。
    """
    if not is_dataclass(instance) or not isinstance(overrides, dict):
        return

    field_map = {f.name: f for f in fields(instance)}
    for key, value in overrides.items():
        target_field = field_map.get(key)
        if target_field is None:
            # 未知 key——当 dataclass 存在 ``extra`` 字段时收入其中。
            extra = getattr(instance, "extra", None)
            if isinstance(extra, dict):
                extra[key] = value
            continue

        current = getattr(instance, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge_into_dataclass(current, value)
            continue

        coerced = _coerce(value, target_field.type, current)
        setattr(instance, key, coerced)


_BOOL_TRUTHY = {"1", "true", "yes", "on"}
_BOOL_FALSY = {"0", "false", "no", "off", ""}


def _coerce(value: Any, declared_type: Any, current: Any) -> Any:
    """尽力将 ``value`` 转换为字段声明的类型。"""
    if value is None:
        return current

    # 仅字符串需要转换，其他类型直接透传。
    if not isinstance(value, str):
        return value

    type_name = str(declared_type).lower()
    if "bool" in type_name:
        low = value.strip().lower()
        if low in _BOOL_TRUTHY:
            return True
        if low in _BOOL_FALSY:
            return False
        return current
    if "int" in type_name:
        try:
            return int(value)
        except ValueError:
            return current
    if "float" in type_name:
        try:
            return float(value)
        except ValueError:
            return current
    if "list" in type_name:
        return [item.strip() for item in value.split(",") if item.strip()]
    if "dict" in type_name:
        try:
            return json.loads(value)
        except ValueError:
            return current
    return value


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
def load(
    *,
    config_path: Optional[str] = None,
    cli_args: Optional[argparse.Namespace] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Config:
    """从全部配置层加载并返回 :class:`Config`。

    参数：
        config_path: 显式指定的 YAML 路径；为 ``None`` 时，依次取 ``cli_args.config`` 、
            ``GAME_TRANS_TOOLCHAIN_CONFIG`` 环境变量，都未提供时默认尝试
            ``./config.yaml``（存在时）。
        cli_args: :func:`build_argparser` 解析后的 argparse namespace。
        environ: 自定义环境变量字典（主要供测试使用）。

    返回：
        完整合并后的 :class:`Config` 实例。

    异常：
        ConfigFileError: 显式指定的 YAML 路径无法读取时。
    """
    config = _default_config()

    # 确定待加载的 YAML 路径。
    yaml_path = _resolve_yaml_path(config_path, cli_args, environ)
    if yaml_path is not None:
        yaml_data = _load_yaml_file(yaml_path)
        _merge_into_dataclass(config, yaml_data)

    env_data = _env_overrides(environ)
    _merge_into_dataclass(config, env_data)

    if cli_args is not None:
        cli_data = _cli_overrides(cli_args)
        _merge_into_dataclass(config, cli_data)

    # 所有层合并完成后，扫描各语种的 profile JSON。
    # 延迟导入，避免包导入时循环依赖。
    from .language_loader import attach_language_profiles
    attach_language_profiles(config)

    return config


def _resolve_yaml_path(
    explicit: Optional[str],
    cli_args: Optional[argparse.Namespace],
    environ: Optional[Dict[str, str]],
) -> Optional[Path]:
    """返回实际要加载的 YAML 路径；均无时返回 ``None``。"""
    if explicit:
        return Path(explicit).expanduser().resolve()

    if cli_args is not None:
        cli_path = getattr(cli_args, "config", None)
        if cli_path:
            return Path(cli_path).expanduser().resolve()

    src = environ if environ is not None else os.environ
    env_path = src.get(_ENV_CONFIG_PATH_KEY)
    if env_path:
        return Path(env_path).expanduser().resolve()

    default_path = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if default_path.exists():
        return default_path.resolve()
    return None


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
_REQUIRED_FIELDS_BY_VCS: Dict[str, List[str]] = {
    "svn": ["vcs.url"],
    "git": ["vcs.url"],
    "perforce": ["vcs.url"],
    # ``local`` 是框架内置的"无 VCS、直接读写本地目录"后端；``mock`` 为
    # 向后兼容的老别名（见 :class:`VcsType`），两者都不需要远端 URL。
    "local": [],
    "mock": [],
}


def validate(config: Config) -> List[str]:
    """返回人可读的问题列表；空列表代表“配置合法”。"""
    problems: List[str] = []

    if not config.project_code:
        problems.append("project_code is empty.")
    if not config.source_locale:
        problems.append("source_locale is empty.")
    if not config.target_locale:
        problems.append("target_locale is empty (use --target-locale or set it in config.yaml).")

    vcs_required = _REQUIRED_FIELDS_BY_VCS.get(config.vcs.type, [])
    for dotted in vcs_required:
        section, name = dotted.split(".", 1)
        value = getattr(getattr(config, section), name, None)
        if not value:
            problems.append(
                f"{dotted} is empty but required for vcs.type = '{config.vcs.type}'."
            )

    if not config.source.path:
        problems.append("source.path is empty.")

    return problems


def require_valid(config: Config) -> None:
    """当 :func:`validate` 发现问题时抛出 :class:`MissingRequiredConfigError`。"""
    problems = validate(config)
    if problems:
        joined = "\n  - ".join(problems)
        raise MissingRequiredConfigError(
            "Configuration is incomplete. Fix the following issues then retry:\n"
            f"  - {joined}\n"
            "Hint: fields can be supplied via config.yaml, env variables "
            f"(prefix '{ENV_PREFIX}{ENV_NESTED_DELIMITER}') or CLI flags."
        )


__all__ = [
    "build_argparser",
    "load",
    "require_valid",
    "validate",
]
