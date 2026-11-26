# pylint: disable=line-too-long

"""配置文件读写服务。

统一管理：
    * conf/config.yaml       —— 全局配置
    * conf/llm.yaml          —— LLM profile 注册表
    * conf/languages/*.yaml  —— 单语种 profile（文件名即 id）
    * workspace/server_meta/preferences.json —— 用户初始化偏好
    * workspace/server_meta/schedules.json   —— Web 面板专属元数据

所有写操作保留 YAML 可读格式（``default_flow_style=False``、
``allow_unicode=True``），不打乱注释是做不到的（PyYAML 默认不保留），
但键顺序会按业务常见顺序排列。
"""



from __future__ import annotations

import io  # pylint: disable=unused-import
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # 仅在 ruamel 不可用时兜底使用

# ruamel.yaml 支持 round-trip（保留注释、顺序、空行）。
# 没装时降级到 PyYAML（会丢注释，但功能可用）。
try:
    from ruamel.yaml import YAML as _RuamelYAML  # type: ignore
    from ruamel.yaml.comments import CommentedMap  # type: ignore
    _HAS_RUAMEL = True
except Exception:  # pylint: disable=broad-except  # pragma: no cover
    _RuamelYAML = None  # pylint: disable=invalid-name  # type: ignore
    CommentedMap = dict  # type: ignore
    _HAS_RUAMEL = False

logger = logging.getLogger(__name__)


def _make_yaml():
    """构造一个 round-trip 的 ruamel.yaml.YAML 实例。"""
    y = _RuamelYAML()  # 默认 typ='rt'
    y.preserve_quotes = True
    y.width = 4096
    y.allow_unicode = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


class ConfigService:
    """封装 ``conf/`` 目录下所有读写。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.conf_dir = self.project_root / "conf"
        self.languages_dir = self.conf_dir / "languages"
        self.server_meta_dir = self.project_root / "workspace" / "server_meta"
        self.backup_dir = self.conf_dir / ".backup"

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    def config_file(self) -> Path:
        return self.conf_dir / "config.yaml"

    def llm_file(self) -> Path:
        return self.conf_dir / "llm.yaml"

    def language_file(self, lang_id: str) -> Path:
        safe = _safe_lang_id(lang_id)
        return self.languages_dir / f"{safe}.yaml"

    def schedules_file(self) -> Path:
        self.server_meta_dir.mkdir(parents=True, exist_ok=True)
        return self.server_meta_dir / "schedules.json"

    def preferences_file(self) -> Path:
        self.server_meta_dir.mkdir(parents=True, exist_ok=True)
        return self.server_meta_dir / "preferences.json"

    def runs_file(self) -> Path:
        self.server_meta_dir.mkdir(parents=True, exist_ok=True)
        return self.server_meta_dir / "runs.json"

    def logs_dir(self) -> Path:
        d = self.project_root / "workspace" / "server_logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # 偏好（用户初始化时选择要启用的模块）
    # ------------------------------------------------------------------
    def load_preferences(self) -> Dict[str, Any]:
        p = self.preferences_file()
        if not p.exists():
            return {
                "enable_platform_first": False,
                "enable_platform_second": False,
                "enable_notification": False,
                "first_platform_type": "none",   # phrase | crowdin | none
                "second_platform_type": "none",
                "notification_type": "none",     # wecom | slack | console | email | none
            }
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_preferences(self, data: Dict[str, Any]) -> None:
        p = self.preferences_file()
        tmp = p.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(p)

    # ------------------------------------------------------------------
    # Setup / 初始化状态检查
    # ------------------------------------------------------------------
    def setup_status(self) -> Dict[str, Any]:
        """返回初始化状态与分模块健康检查。

        返回结构：
            {
              initialized: bool,            # 核心配置是否已可以跑 workflow
              config_yaml_exists: bool,
              llm_yaml_exists: bool,
              languages_count: int,
              missing_fields: [str],        # 核心阻塞字段
              checks: [                     # 分模块健康检查
                {
                  module: str,  -- project / vcs / llm / platform_first / platform_second / notification / languages
                  label: str,               # 中文名
                  status: str,              # ok | warn | fail | skip
                  message: str,             # 简短摘要
                  details: [str],           # 问题清单
                  env_hints: [str],         # 需要配置的环境变量提示
                },
                ...
              ]
            }
        """
        config_exists = self.config_file().exists()
        llm_exists = self.llm_file().exists()
        langs = self.list_languages()
        prefs = self.load_preferences()

        config_data: Dict[str, Any] = {}
        if config_exists:
            try:
                config_data = self.load_global_config() or {}
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
                logger.warning("Failed to parse config.yaml: %s", exc)

        llm_data: Dict[str, Any] = {}
        if llm_exists:
            try:
                llm_data = self.load_llm_registry() or {}
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
                logger.warning("Failed to parse llm.yaml: %s", exc)

        checks: List[Dict[str, Any]] = []
        missing: List[str] = []

        # 1) 文件是否存在
        if not config_exists:
            missing.append("conf/config.yaml")
        if not llm_exists:
            missing.append("conf/llm.yaml")

        # 2) 项目基础
        proj_details: List[str] = []
        if not config_data.get("project_code"):
            proj_details.append("project_code 未填")
        if not config_data.get("source_locale"):
            proj_details.append("source_locale 未填（建议 zh-CN）")
        checks.append(_mk_check(
            module="project", label="项目基础",
            details=proj_details,
            ok_msg="项目基础配置完整",
            fail_msg="项目基础字段缺失",
        ))

        # 3) VCS
        vcs = config_data.get("vcs") or {}
        vcs_details: List[str] = []
        vcs_env_hints: List[str] = []
        vcs_type = (vcs.get("type") or "").strip()
        if not vcs_type:
            vcs_details.append("vcs.type 未选择")
        # local_path 对所有 vcs 类型（含 local）都必填 —— 它决定流水线在哪里读写
        if not vcs.get("local_path"):
            vcs_details.append("vcs.local_path 未填（流水线读写工作副本的根目录；local 推荐填绝对路径）")
        # local 和老别名 mock 都不需要 vcs.url
        if vcs_type not in {"local", "mock", ""} and not vcs.get("url"):
            vcs_details.append("vcs.url 未填（远端仓库地址）")
        if vcs_type in {"svn", "perforce"}:
            if not vcs.get("username") and not _env_set("GAME_TRANS_TOOLCHAIN__VCS__USERNAME"):
                vcs_details.append("vcs.username 未填 且 环境变量未设置")
                vcs_env_hints.append("GAME_TRANS_TOOLCHAIN__VCS__USERNAME")
            if not vcs.get("password") and not _env_set("GAME_TRANS_TOOLCHAIN__VCS__PASSWORD"):
                vcs_details.append("vcs.password 未填 且 环境变量未设置")
                vcs_env_hints.append("GAME_TRANS_TOOLCHAIN__VCS__PASSWORD")
        checks.append(_mk_check(
            module="vcs", label="版本控制 (VCS)",
            details=vcs_details, env_hints=vcs_env_hints,
            ok_msg=f"VCS 已配置 ({vcs_type or '未选'})",
            fail_msg="VCS 配置不完整",
        ))

        # 4) LLM
        llm_details: List[str] = []
        llm_env_hints: List[str] = []
        profiles = (llm_data.get("profiles") or {}) if isinstance(llm_data, dict) else {}
        default_profile = (llm_data.get("default") or "") if isinstance(llm_data, dict) else ""
        if not profiles:
            llm_details.append("conf/llm.yaml 中没有任何 profile")
        else:
            if default_profile and default_profile not in profiles:
                llm_details.append(f"默认 profile '{default_profile}' 不在 profiles 列表中")
            # 结构性检查（所有 profile）：provider 必须填
            for name, prof in profiles.items():
                if not isinstance(prof, dict):
                    llm_details.append(f"profile '{name}' 结构非法")
                    continue
                provider = prof.get("provider") or ""
                if not provider:
                    llm_details.append(f"profile '{name}' 缺 provider")
            # **严格 api_key / 必填 extra** 检查只针对**默认 profile**。
            # 其他 profile 允许作为"示例/占位 YAML 存在"，api_key 为空也不阻塞
            # 初始化（真正使用时才由 run 流水线报错，更符合用户心智）。
            if default_profile and default_profile in profiles:
                prof = profiles[default_profile]
                if isinstance(prof, dict):
                    provider = (prof.get("provider") or "").strip()
                    # 老配置里的 `mock` 是 `echo` 的别名，两者都不需 api_key / model。
                    if provider and provider not in {"echo", "mock"}:
                        # model 对真实 provider 必填
                        if not (prof.get("model") or "").strip():
                            llm_details.append(
                                f"默认 profile '{default_profile}' 的 model 未填（请在 conf/llm.yaml 或 LLM 页面补充）"
                            )
                        # api_base 对部分 provider 必填
                        needs_base = {"openai_compatible", "venus", "hunyuan_translation"}
                        if provider in needs_base and not (prof.get("api_base") or "").strip():
                            llm_details.append(
                                f"默认 profile '{default_profile}' (provider={provider}) 的 api_base 未填"
                            )
                        # 鉴权凭据检查 —— 按 provider 分支：
                        #   * venus    —— 走 extra.secret_id / extra.secret_key（不走 api_key）
                        #   * hunyuan  —— 走 api_key + extra.wsid
                        #   * gemini   —— 走 api_key 或 GOOGLE_API_KEY 环境变量
                        #   * 其他真实 —— 走 api_key 或 GAME_TRANS_TOOLCHAIN__LLM__API_KEY
                        if provider == "venus":
                            ex = prof.get("extra") or {}
                            if not ex.get("server_id") or not ex.get("app_group_id"):
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 为 venus 但 extra.server_id / extra.app_group_id 未填"
                                )
                            # venus 的凭据：extra.secret_id + extra.secret_key，或走环境变量 api_key
                            has_pair = bool(ex.get("secret_id")) and bool(ex.get("secret_key"))
                            has_env = _env_set("GAME_TRANS_TOOLCHAIN__LLM__API_KEY")
                            if not has_pair and not has_env:
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 为 venus 但未配置 extra.secret_id / extra.secret_key，"
                                    f"也未设置环境变量 GAME_TRANS_TOOLCHAIN__LLM__API_KEY=<secret_id>:<secret_key>"
                                )
                                llm_env_hints.append("GAME_TRANS_TOOLCHAIN__LLM__API_KEY")
                        elif provider == "hunyuan_translation":
                            if not (prof.get("extra") or {}).get("wsid"):
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 为 hunyuan_translation 但 extra.wsid 未填"
                                )
                            if not prof.get("api_key") and not _env_set("GAME_TRANS_TOOLCHAIN__LLM__API_KEY"):
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 的 api_key 未填 且 环境变量 GAME_TRANS_TOOLCHAIN__LLM__API_KEY 未设置"
                                )
                                llm_env_hints.append("GAME_TRANS_TOOLCHAIN__LLM__API_KEY")
                        elif provider == "gemini":
                            # gemini 支持 GAME_TRANS_TOOLCHAIN__LLM__API_KEY 或 GOOGLE_API_KEY
                            if not prof.get("api_key") and not _env_set("GAME_TRANS_TOOLCHAIN__LLM__API_KEY") and not _env_set("GOOGLE_API_KEY"):
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 为 gemini 但 api_key 未填 且 环境变量 "
                                    f"GAME_TRANS_TOOLCHAIN__LLM__API_KEY / GOOGLE_API_KEY 均未设置"
                                )
                                llm_env_hints.append("GOOGLE_API_KEY")
                        else:
                            # openai / openai_compatible / anthropic 等走 api_key
                            if not prof.get("api_key") and not _env_set("GAME_TRANS_TOOLCHAIN__LLM__API_KEY"):
                                llm_details.append(
                                    f"默认 profile '{default_profile}' 的 api_key 未填 且 环境变量 GAME_TRANS_TOOLCHAIN__LLM__API_KEY 未设置"
                                )
                                llm_env_hints.append("GAME_TRANS_TOOLCHAIN__LLM__API_KEY")
        checks.append(_mk_check(
            module="llm", label="LLM 大模型",
            details=llm_details, env_hints=llm_env_hints,
            ok_msg=f"LLM 已配置 (共 {len(profiles)} 个 profile)",
            fail_msg="LLM 配置不完整",
        ))

        # 5) 全局平台（可选）
        plat = config_data.get("platform") or {}
        plat_type = (plat.get("type") or "none").strip()
        plat_details: List[str] = []
        plat_env_hints: List[str] = []
        if plat_type in {"phrase", "crowdin"}:
            # 要么写了 api_token，要么走环境变量
            tokens_ok = bool(plat.get("api_token")) or _env_set("GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN")
            # Phrase 可用 subject_token 代替 api_token
            if plat_type == "phrase":
                tokens_ok = tokens_ok or bool((plat.get("extra") or {}).get("subject_token")) or _env_set("GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN")
            if not tokens_ok:
                plat_details.append(f"{plat_type} 平台的 api_token / subject_token 未填且环境变量未设置")
                plat_env_hints.append("GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN")
                if plat_type == "phrase":
                    plat_env_hints.append("GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN")
            if not plat.get("project_id"):
                plat_details.append(f"{plat_type} 平台的 project_id 未填（可在语种 profile 的 reviews 中覆盖）")
            status_override = None
        else:
            # 用户选择 none（不启用全局平台）
            status_override = "skip"
        checks.append(_mk_check(
            module="platform", label=f"审校平台（全局兜底，{plat_type}）",
            details=plat_details, env_hints=plat_env_hints,
            ok_msg=f"全局平台已配置 ({plat_type})",
            fail_msg="全局平台配置不完整",
            status_override=status_override,
            skip_msg="未启用全局审校平台（type=none）",
        ))

        # 6) 通知
        notif = config_data.get("notification") or {}
        notif_type = (notif.get("type") or "none").strip()
        notif_details: List[str] = []
        notif_env_hints: List[str] = []
        if notif_type in {"wecom", "slack"}:
            if not notif.get("webhook") and not _env_set("GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK"):
                notif_details.append(f"{notif_type} 通知的 webhook 未填且环境变量未设置")
                notif_env_hints.append("GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK")
            notif_override = None
        elif notif_type == "email":
            notif_details.append("email 通知的详细字段请在语种 profile 中按需覆盖")
            notif_override = None
        else:
            notif_override = "skip"
        checks.append(_mk_check(
            module="notification", label=f"通知渠道 ({notif_type})",
            details=notif_details, env_hints=notif_env_hints,
            ok_msg=f"通知已配置 ({notif_type})",
            fail_msg="通知配置不完整",
            status_override=notif_override,
            skip_msg="未启用通知（type=none / console）",
        ))

        # 7) 语种
        lang_details: List[str] = []
        if not langs:
            lang_details.append("conf/languages/ 下还没有任何语种 profile，无法启动工作流")
        checks.append(_mk_check(
            module="languages", label=f"语种 profile ({len(langs)} 个)",
            details=lang_details,
            ok_msg=f"已有 {len(langs)} 个语种 profile",
            fail_msg="还没有任何语种 profile",
        ))

        # 最终 initialized 判定
        blocking_modules = {"project", "vcs", "llm"}
        has_blocker = any(
            c["module"] in blocking_modules and c["status"] == "fail"
            for c in checks
        )
        initialized = config_exists and llm_exists and not has_blocker
        # 把阻塞字段也汇总
        for c in checks:
            if c["module"] in blocking_modules and c["status"] == "fail":
                missing.extend(c["details"])

        return {
            "initialized": initialized,
            "config_yaml_exists": config_exists,
            "llm_yaml_exists": llm_exists,
            "languages_count": len(langs),
            "missing_fields": missing,
            "preferences": prefs,
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # 全局 config.yaml
    # ------------------------------------------------------------------
    def load_global_config(self) -> Dict[str, Any]:
        return _load_yaml(self.config_file())

    def save_global_config(self, data: Dict[str, Any]) -> None:
        """保存全局 config.yaml（合并模式，保留注释）。

        行为：
            - 读旧文件（含注释） → 把 ``data`` 的键值**合并**进去（已有 key 更新、
              新 key 追加）→ 写回。注释、键顺序、空行基本保留。
            - 若 ``platform.type`` 发生变化，自动把所有已存在的语种 profile
              的 ``reviews.{first,second,light}.platform`` 同步成新值。
        """
        old_type = ""
        existing: Dict[str, Any] = {}
        try:
            existing = self.load_global_config() or {}
            old_type = ((existing.get("platform") or {}).get("type") or "").strip()
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            pass

        self._backup(self.config_file())
        merged = _merge_into(existing if existing else {}, data or {})
        _dump_yaml(self.config_file(), merged)

        new_type = ((merged.get("platform") or {}).get("type") or "none").strip()
        if new_type != old_type:
            self._sync_language_platforms(new_type)

    def _sync_language_platforms(self, platform_type: str) -> None:
        """把所有语种 profile 的 reviews.*.platform 同步到 ``platform_type``。"""
        if not self.languages_dir.exists():
            return
        for p in self.languages_dir.glob("*.yaml"):
            try:
                data = _load_yaml(p)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
                logger.warning("Skip syncing %s: %s", p, exc)
                continue
            if not isinstance(data, dict):
                continue
            reviews = data.setdefault("reviews", {}) if isinstance(data.get("reviews", {}), dict) else {}
            changed = False
            for stage in ("first", "second", "light"):
                stage_cfg = reviews.setdefault(stage, {}) if isinstance(reviews.get(stage, {}), dict) else {}
                has_project = bool((stage_cfg.get("project_id") or "").strip()) or \
                              bool((stage_cfg.get("project_name") or "").strip())
                new_val = platform_type if (has_project and platform_type and platform_type != "none") else "none"
                if stage_cfg.get("platform") != new_val:
                    stage_cfg["platform"] = new_val
                    changed = True
                reviews[stage] = stage_cfg
            if changed:
                data["reviews"] = reviews
                self._backup(p)
                _dump_yaml(p, data)
                logger.info("[CONFIG] synced reviews.*.platform in %s → %r", p.name, platform_type)

    # ------------------------------------------------------------------
    # LLM llm.yaml
    # ------------------------------------------------------------------
    def load_llm_registry(self) -> Dict[str, Any]:
        data = _load_yaml(self.llm_file())
        data.setdefault("profiles", {})
        data.setdefault("default", "")
        _normalize_llm_profiles(data.get("profiles") or {})
        return data

    def save_llm_registry(self, data: Dict[str, Any]) -> None:
        """保存 llm.yaml（合并模式，保留注释与已有示例 profile）。

        行为：
            - 校验 profile 名合法；
            - 与已有 llm.yaml 做**深合并**：
                * ``default`` 若 ``data`` 有值则覆盖；否则保留旧值；
                * ``profiles`` 下已有 key → 字段级合并；新 key → 追加。
              这样向导传入的 payload 不会把 llm.yaml 里已有的示例 profile 丢弃。
        """
        profiles = (data or {}).get("profiles") or {}
        if not isinstance(profiles, dict):
            raise ValueError("llm.yaml 的 profiles 必须是对象（key -> profile 配置）")
        for name in profiles.keys():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("LLM profile 名称不能为空")
            if any(ch.isspace() for ch in name) or "/" in name or "\\" in name:
                raise ValueError(
                    f"LLM profile 名称 '{name}' 不能包含空白字符或路径分隔符，"
                    "建议使用 `provider_model` 的小写蛇形命名（如 openai_gpt4o_mini）"
                )

        # 入库前把 extra 下本该是 dict 的字段（model_params / extra 等）从
        # 可能的 JSON 字符串形式归一化回真实 dict，避免老前端的容错 bug
        # 把文本污染到持久化配置里。
        _normalize_llm_profiles(profiles)

        existing = self.load_llm_registry() or {}
        existing.setdefault("profiles", {})
        existing.setdefault("default", "")

        self._backup(self.llm_file())
        merged = _merge_into(existing, data or {})
        _dump_yaml(self.llm_file(), merged)

    def upsert_llm_profile(self, name: str, profile: Dict[str, Any]) -> None:
        reg = self.load_llm_registry()
        reg.setdefault("profiles", {})[name] = profile
        if not reg.get("default"):
            reg["default"] = name
        self.save_llm_registry(reg)

    def delete_llm_profile(self, name: str) -> None:
        reg = self.load_llm_registry()
        profiles = reg.get("profiles") or {}
        if name in profiles:
            del profiles[name]
        if reg.get("default") == name:
            reg["default"] = next(iter(profiles), "")
        self.save_llm_registry(reg)

    # ------------------------------------------------------------------
    # 语种 profile
    # ------------------------------------------------------------------
    def list_languages(self) -> List[Dict[str, Any]]:
        if not self.languages_dir.exists():
            return []
        items: List[Dict[str, Any]] = []
        for p in sorted(self.languages_dir.glob("*.yaml")):
            try:
                data = _load_yaml(p)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
                logger.warning("Failed to load %s: %s", p, exc)
                data = {}
            # id 使用文件名（p.stem）作为稳定索引键，与所有 CRUD API 的路径
            # 参数保持一致。YAML 内的 `id` 字段仅作为"业务别名"展示，便于用户
            # 识别用途（例如 de.yaml 的 id 字段 = "de_example" 表示这是示例）。
            file_id = p.stem
            business_alias = (data.get("id") or "").strip()
            items.append({
                "id": file_id,
                "alias": business_alias if business_alias and business_alias != file_id else "",
                "display_name": data.get("display_name", file_id),
                "target_locale": data.get("target_locale", ""),
                "workflow": data.get("workflow", []),
                "updated_at": _ts(p),
            })
        return items

    def load_language(self, lang_id: str) -> Dict[str, Any]:
        return _load_yaml(self.language_file(lang_id))

    def save_language(self, lang_id: str, data: Dict[str, Any]) -> None:
        """保存语种 profile（合并模式，保留注释）。

        自动化行为：
            - 与已有 YAML 做**深合并**：保留原有注释、顺序；
            - **自动同步** ``reviews.{first, second, light}.platform`` 与全局
              ``config.yaml`` 的 ``platform.type`` 保持一致（审校平台只在全局
              配置一次，所有阶段都用它）。
            - 若某阶段的 ``project_id`` / ``project_name`` 均为空，则认为该
              阶段**禁用**，platform 置为 ``"none"`` 以便 workflow 跳过。
        """
        self.languages_dir.mkdir(parents=True, exist_ok=True)
        path = self.language_file(lang_id)
        self._backup(path)
        data["id"] = lang_id

        existing = _load_yaml(path) if path.exists() else {}
        merged = _merge_into(existing if existing else {}, data)

        # 读取全局 platform.type，自动写回各阶段
        try:
            global_cfg = self.load_global_config() or {}
            global_platform_type = ((global_cfg.get("platform") or {}).get("type") or "none").strip()
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            global_platform_type = "none"

        reviews = merged.setdefault("reviews", {})
        for stage in ("first", "second", "light"):
            stage_cfg = reviews.setdefault(stage, {})
            # 判定该阶段是否"启用"：填了 project_id 或 project_name
            has_project = bool((stage_cfg.get("project_id") or "").strip()) or \
                          bool((stage_cfg.get("project_name") or "").strip())
            if has_project and global_platform_type and global_platform_type != "none":
                stage_cfg["platform"] = global_platform_type
            else:
                stage_cfg["platform"] = "none"

        _dump_yaml(path, merged)

    def delete_language(self, lang_id: str) -> None:
        path = self.language_file(lang_id)
        if path.exists():
            self._backup(path)
            path.unlink()

    # ------------------------------------------------------------------
    # 备份
    # ------------------------------------------------------------------
    def _backup(self, path: Path) -> None:
        if not path.exists():
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"{path.name}.{ts}.bak"
        try:
            shutil.copy2(path, dest)
        except OSError as exc:  # pragma: no cover
            logger.warning("Backup failed for %s: %s", path, exc)


# -----------------------------------------------------------------------------
# 辅助
# -----------------------------------------------------------------------------
def _mk_check(
    *,
    module: str,
    label: str,
    details: List[str],
    ok_msg: str,
    fail_msg: str,
    env_hints: Optional[List[str]] = None,
    status_override: Optional[str] = None,
    skip_msg: str = "",
) -> Dict[str, Any]:
    """构造一个 check 条目。"""
    if status_override:
        return {
            "module": module, "label": label,
            "status": status_override,
            "message": skip_msg or ok_msg,
            "details": [],
            "env_hints": [],
        }
    status = "ok" if not details else "fail"
    message = ok_msg if status == "ok" else fail_msg
    return {
        "module": module, "label": label,
        "status": status, "message": message,
        "details": details, "env_hints": env_hints or [],
    }


def _env_set(name: str) -> bool:
    import os
    return bool(os.environ.get(name, "").strip())


def _safe_lang_id(lang_id: str) -> str:
    if not lang_id or "/" in lang_id or "\\" in lang_id or lang_id in {".", ".."}:
        raise ValueError(f"invalid language id: {lang_id!r}")
    return lang_id


def _load_yaml(path: Path) -> Dict[str, Any]:
    """加载 YAML。使用 ruamel.yaml round-trip 读入，保留注释/顺序/锚点。

    返回值既可以当普通 dict 用（Vue 前端/其他服务），也能原地改回写时保留注释。
    """
    if not path.exists():
        return {}
    if _HAS_RUAMEL:
        yml = _make_yaml()
        with path.open("r", encoding="utf-8") as f:
            data = yml.load(f)
        return data if data is not None else {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _dump_yaml(path: Path, data: Dict[str, Any]) -> None:
    """写回 YAML。使用 ruamel.yaml round-trip 保留注释/顺序。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_RUAMEL:
        yml = _make_yaml()
        with path.open("w", encoding="utf-8") as f:
            yml.dump(data, f)
        return
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2,
        )


def _plain_merged(target: Any, source: Any) -> Any:
    """构造一个**普通 dict** 版本的深合并结果（不带 ruamel 注释容器）。"""
    if not isinstance(source, dict):
        return source
    if not isinstance(target, dict):
        return dict(source)
    out: Dict[str, Any] = {}
    for k, v in target.items():
        out[k] = v
    for k, v in source.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _plain_merged(out[k], v)
        else:
            out[k] = v
    return out


def _merge_commented_subdoc(container: Any, patch: Dict[str, Any]) -> None:
    """就地把 ``patch`` 合并到 ``container`` （ruamel CommentedMap）。

    关键修复：ruamel.yaml 把"**跟在当前 subdoc 之后、属于父级的分区注释**"
    （如 ``# ---- next section ----``）错误地挂在了 subdoc 内部**最后一个
    key** 的"after-value"注释槽上（``.ca.items[last_key][2]``）。如果直接
    往 subdoc 追加新 key，这段分区注释会被挤到新 key 的中间，出现:::

        notification:
          type: none
        # ---- next section ----       ← 本应在 subdoc 结束之后
          webhook: ...                 ← 新 key 跑到了注释下方（错位）

    为此，追加前先把这段 after-注释从旧的"最后一个 key"剥离、暂存，追加
    完成后把它挂到**新的最后一个 key** 的 after 槽上，让它继续起分区注释
    作用。
    """
    # 对已存在 key：原地赋值（允许用相同 key 刷新值；ruamel 会保留其注释）
    # 对新 key：追加到末尾（追加前要先暂存旧末尾 key 的 after-注释）
    existing_keys = list(container.keys()) if hasattr(container, "keys") else []
    new_keys = [k for k in patch.keys() if k not in existing_keys]

    # 暂存"旧末尾 key"的 after-注释（如果有）
    cached_after = None
    cached_key = None
    if _HAS_RUAMEL and new_keys and existing_keys:
        tail = existing_keys[-1]
        try:
            slot = container.ca.items.get(tail) if container.ca else None
            if slot and slot[2]:
                cached_after = slot[2]
                cached_key = tail
                slot[2] = None
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            pass

    # 更新已存在的 key
    for k in existing_keys:
        if k in patch:
            v_patch = patch[k]
            v_cur = container[k]
            if isinstance(v_cur, dict) and isinstance(v_patch, dict) and _HAS_RUAMEL and isinstance(v_cur, CommentedMap):
                # 递归合并嵌套 subdoc（同样走"暂存+迁移"策略）
                _merge_commented_subdoc(v_cur, v_patch)
            else:
                container[k] = v_patch

    # 追加新 key
    for k in new_keys:
        v = patch[k]
        if _HAS_RUAMEL and isinstance(v, dict):
            inner = CommentedMap()
            _merge_commented_subdoc(inner, v)
            container[k] = inner
        else:
            container[k] = v

    # 把暂存的 after-注释挂到新末尾 key 上
    if cached_after is not None and _HAS_RUAMEL:
        all_keys = list(container.keys())
        if all_keys:
            new_tail = all_keys[-1]
            try:
                items = container.ca.items
                if new_tail not in items:
                    items[new_tail] = [None, None, None, None]
                items[new_tail][2] = cached_after
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
                logger.debug("Restore trailing comment failed on key %r: %s", new_tail, exc)
                # 回滚到原位置，不丢注释
                try:
                    container.ca.items[cached_key][2] = cached_after
                except Exception:  # pylint: disable=broad-except
                    pass


def _merge_into(target: Any, source: Any) -> Any:
    """把 ``source`` 的键合并到 ``target``，并返回合并后的 target。

    合并策略：
        - 若 target 是 ruamel.yaml CommentedMap：使用 ``_merge_commented_subdoc``
          做"暂存分区注释 + 原地追加 key + 迁移注释"的 round-trip 友好合并；
        - 若 target 不是 dict：用 source 替换；
        - 若 ruamel 不可用：退化为普通 dict 的深合并（注释天然无保留）。

    这个实现解决了 ruamel.yaml 对"**分区注释存在前一个 subdoc 内部最后一
    个 key 的 after 槽**"的归属偏差 bug —— 追加/修改 key 时主动迁移这段
    注释，让它继续起到"分区标题"的作用，不会错位到 subdoc 内部。
    """
    if not isinstance(source, dict):
        return source
    if not isinstance(target, dict):
        if _HAS_RUAMEL:
            new = CommentedMap()
            _merge_commented_subdoc(new, source)
            return new
        return _plain_merged({}, source)
    if _HAS_RUAMEL and isinstance(target, CommentedMap):
        _merge_commented_subdoc(target, source)
        return target
    # 退化路径（没装 ruamel，或已经是普通 dict）
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            target[k] = _plain_merged(target[k], v)
        else:
            target[k] = v
    return target


# 这些 key 在 LLM profile 的 extra 下，schema 中声明为 type="dict"。
# 老前端的容错 bug 曾把输入框原文（可能是 JSON 字符串）直接存成 string，
# 导致下次打开"没渲染"。这里在读/写时做兜底归一化。
_LLM_EXTRA_DICT_KEYS = ("model_params", "generation_config", "extra")


def _normalize_llm_profiles(profiles: Dict[str, Any]) -> None:
    """就地归一化：把被误存成 JSON 字符串的 extra 子 dict 恢复为真实 dict。

    参数：
        profiles: ``llm.yaml`` 的 ``profiles`` 节点（key -> profile 配置）。
            修改是**原地的**，调用方不需要接收返回值。
    """
    if not isinstance(profiles, dict):
        return
    for _name, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        extra = prof.get("extra")
        if not isinstance(extra, dict):
            continue
        for k in _LLM_EXTRA_DICT_KEYS:
            v = extra.get(k)
            if isinstance(v, str):
                t = v.strip()
                if not t:
                    extra[k] = {}
                    continue
                try:
                    parsed = json.loads(t)
                except Exception:  # pylint: disable=broad-except
                    # 实在解析不动就留着原字符串，前端的新 asJson 会尝试
                    # 再解一次；保守做法是不冒险扔数据。
                    continue
                if isinstance(parsed, dict):
                    extra[k] = parsed


def _ts(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""
