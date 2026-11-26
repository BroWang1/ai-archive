"""``TiMi_HOK_Game_Translator`` 命令行入口。

本模块通过 ``pyproject.toml`` 注册为 console-script ``TiMi_HOK_Game_Translator``，
同时作为 ``python -m TiMi_HOK_Game_Translator`` 的执行目标。

支持的子命令：

* ``TiMi_HOK_Game_Translator run``          — 执行完整工作流。
* ``TiMi_HOK_Game_Translator config dump``  — 打印当前生效配置。
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Sequence

from .commons import APP_NAME
from .config import Config, build_argparser, load, require_valid
from .llm import create_llm_client
from .notify import create_notifier
from .platforms import create_platform
from .sources import create_source
from .vcs import create_vcs_client
from .workflow import WorkflowRunner


def _configure_logging(config: Config) -> None:
    """按配置初始化根 logger。"""
    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    handlers: list = []
    if config.logging.console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers or None,
        force=True,
    )
    # 给根 logger 挂一个过滤器：
    # 1. 把第三方 SDK（如 venus_api_base）用 logger.info 打印 bytes 对象产生的
    #    形如 b'...\xe6\x88\x90\xe5\x8a\x9f...' 的转义字符串还原为 UTF-8 中文；
    # 2. 对 "response data:" 这类巨长的原始响应 payload 做压缩/截断，避免噪音。
    root_logger = logging.getLogger()
    _bytes_filter = _BytesEscapeDecoder()
    # 防止重复挂载（force=True 会清掉 handlers 但不动 filters，这里显式去重）
    for existing in list(root_logger.filters):
        if isinstance(existing, _BytesEscapeDecoder):
            root_logger.removeFilter(existing)
    root_logger.addFilter(_bytes_filter)


class _BytesEscapeDecoder(logging.Filter):
    """把 ``logger.info(bytes_obj)`` 打出来的 bytes-repr 字符串还原为可读 UTF-8。

    典型场景：venus_api_base SDK 内部 ``logger.info("response data:%s", resp.content)``
    直接把 ``bytes`` 作为 msg 参数传入，Python logging 会 ``str(bytes)``——结果
    控制台看到的中文会变成 ``\\xe6\\x88\\x90\\xe5\\x8a\\x9f`` 这种转义字面量。

    过滤器思路：
        * 识别 record.getMessage() 中的 ``b'...'`` / ``b"..."`` 字节字面量；
        * 用 ``codecs.escape_decode`` 还原为真实 bytes 后再 ``decode("utf-8")``；
        * 对超长的 ``response data:`` 做字段级压缩（只保留 message / usage / response）。
    """

    import re as _re
    _BYTES_LITERAL = _re.compile(r"""b(['"])(.*?)\1""", _re.DOTALL)
    _MAX_LEN = 1500  # 单条日志最多保留的字符数

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            return True
        if "\\x" not in msg and "b'" not in msg and 'b"' not in msg:
            return True
        new_msg = self._BYTES_LITERAL.sub(self._decode_match, msg)
        # 过长时做截断，保留头尾用于定位
        if len(new_msg) > self._MAX_LEN:
            keep = self._MAX_LEN // 2 - 20
            new_msg = (
                new_msg[:keep]
                + f" ... [truncated {len(new_msg) - 2 * keep} chars] ... "
                + new_msg[-keep:]
            )
        # 清除 args，避免 logging 再做一次 %-formatting
        record.msg = new_msg
        record.args = None
        return True

    @staticmethod
    def _decode_match(m) -> str:
        raw = m.group(2)
        try:
            import codecs
            decoded_bytes, _ = codecs.escape_decode(raw.encode("utf-8", errors="replace"))
            return decoded_bytes.decode("utf-8", errors="replace")
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            return m.group(0)


def _dump_config(args, config: Config) -> int:
    """``config dump`` 子命令：以 yaml/json 格式打印当前配置。"""
    mask = not getattr(args, "no_mask", False)
    data = config.to_dict(mask_sensitive=mask)
    fmt = getattr(args, "format", "yaml")
    if fmt == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        try:
            import yaml
            print(
                yaml.safe_dump(
                    data, default_flow_style=False, allow_unicode=True, sort_keys=True,
                )
            )
        except ImportError:  # pragma: no cover
            print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _merge_notification(profile_notify, global_notify):
    """字段级合并语种与全局 ``NotificationConfig``。

    合并策略（**字段级继承**，而非整段替换）：
        * ``type``       —— 语种填了用语种，否则用全局；
        * ``webhook``    —— 语种填了用语种，否则继承全局（**解决"语种填了 type
                            但 webhook 占位空字符串" → 消息被丢弃**的痛点）；
        * ``mentioned``  —— 语种填了（非空列表）用语种，否则继承全局；
        * ``extra``      —— 语种填了（非空字典）用语种，否则继承全局。

    这样业务侧新建语种只需关心"要 @ 谁"，webhook 自动走全局即可，避免每个
    语种 YAML 都复制粘贴相同的 webhook URL（也不容易泄露敏感字段）。
    """
    from dataclasses import replace
    if profile_notify is None:
        return global_notify
    if global_notify is None:
        return profile_notify
    return replace(
        profile_notify,
        type=profile_notify.type or global_notify.type,
        webhook=profile_notify.webhook or global_notify.webhook,
        mentioned=list(profile_notify.mentioned) if profile_notify.mentioned else list(global_notify.mentioned or []),
        extra=dict(profile_notify.extra) if profile_notify.extra else dict(global_notify.extra or {}),
    )


def _resolve_profile(args, config: Config):
    """选择本次要执行的语种配置（LanguageProfile）。

    解析顺序：
    1. 命令行显式指定的 ``--language <id>``；
    2. 与已加载 profile 匹配的 ``config.target_locale``；
    3. ``Config.languages`` 中的第一个 profile（多个时会告警）；
    4. 未加载任何 profile 时，通过 :meth:`Config.language_profile` 合成一个。
    """
    language = getattr(args, "language", None) or ""
    if not language:
        language = config.target_locale
    if language and language in config.languages:
        return config.languages[language]
    if not config.languages:
        return config.language_profile(language or "target")
    # 兜底：使用第一个 profile，并给出告警
    logger = logging.getLogger(APP_NAME)
    first_id = next(iter(config.languages))
    if language:
        logger.warning(
            "cli: language %r not found in profiles %s — falling back to %r",
            language, sorted(config.languages), first_id,
        )
    else:
        logger.warning(
            "cli: no --language given; using first profile %r out of %d",
            first_id, len(config.languages),
        )
    return config.languages[first_id]


def _run(args, config: Config, *, fresh: bool = False, batch: str | None = None) -> int:
    """``run`` 子命令：按 profile 组装各后端并驱动 WorkflowRunner。

    参数：
        args: 已解析的命令行参数。
        config: 加载完成的全局配置。
        fresh: True 时清空断点重跑，否则遵循 ``batch`` 语义。
        batch: 显式续跑指定批次（如 ``vi_20261008204338``）；为 ``None`` 时
            采用"新开批次"的宽松默认（M 语义）：不加载历史 state，但保留
            ``last_tasks.json`` 的跨批次状态。
    返回：
        进程退出码（0 表示成功）。
    """
    # 先解析语种 profile，把 profile 的 target_locale / source 等关键字段
    # 下沉到顶层 config，再做 require_valid 校验。否则在只用 profile 承载
    # target_locale 的常规配置下，会先炸 "target_locale is empty"。
    profile = _resolve_profile(args, config)
    if profile.target_locale and not config.target_locale:
        config.target_locale = profile.target_locale
    if profile.source and profile.source.path and (not config.source or not config.source.path):
        config.source = profile.source

    require_valid(config)
    _configure_logging(config)
    logger = logging.getLogger(APP_NAME)

    workspace = config.workspace_path()
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting %s for project=%s language=%s target=%s",
        APP_NAME, config.project_code, profile.id, profile.target_locale or config.target_locale,
    )

    # 优先取 profile 上的覆盖配置，否则回退到全局配置
    source_cfg = profile.source if profile.source and profile.source.path else config.source
    vcs_cfg = profile.vcs if profile.vcs and profile.vcs.type else config.vcs
    llm_cfg = profile.llm if profile.llm and profile.llm.provider else config.llm
    notify_cfg = _merge_notification(profile.notification, config.notification)

    runner = WorkflowRunner(
        config=config,
        profile=profile,
        vcs=create_vcs_client(vcs_cfg, workspace=str(workspace)),
        source=create_source(source_cfg),
        llm=create_llm_client(llm_cfg),
        platform=create_platform(config.platform),
        notifier=create_notifier(notify_cfg),
        workspace=workspace,
    )

    final_state = runner.run(fresh=fresh, batch=batch)
    logger.info("Workflow finished with state=%s", final_state)
    return 0


def _load_config(args) -> Config:
    """加载 config。

    优先调用 ``conf._bootstrap.load_config_with_llm_profiles`` 展开 ``llm_profile``、
    合并 vcs/source 字段级字段、透传 ``locale_names`` 等粘合逻辑；当仓库中
    没有 ``conf/`` 粘合包（或 import 失败）时，回落到框架自带的 ``load()``，
    保持 ``src/TiMi_HOK_Game_Translator`` 对 ``conf/`` 的零硬依赖。

    关于 ``-c/--config``：
        * 显式传入时，直接使用该路径；
        * 省略时，由 bootstrap 自身按 ``GAME_TRANS_TOOLCHAIN_CONFIG`` 环境变量
          与 ``conf/config.yaml`` 兜底顺序解析，无需额外指定。
    """
    config_path = getattr(args, "config", None) or None
    try:
        from conf._bootstrap import load_config_with_llm_profiles  # type: ignore

        return load_config_with_llm_profiles(config_path, cli_args=args)
    except ImportError:
        return load(cli_args=args)


def main(argv: Sequence[str] | None = None) -> int:
    """``TiMi_HOK_Game_Translator`` 命令行入口。

    参数：
        argv: 命令行参数序列，None 时从 sys.argv 读取。
    返回：
        进程退出码。
    """
    parser = build_argparser()
    args = parser.parse_args(argv)

    command = getattr(args, "command", None)
    if command == "config" and getattr(args, "config_command", None) == "dump":
        config = _load_config(args)
        return _dump_config(args, config)

    if command == "run":
        fresh = bool(getattr(args, "fresh", False))
        batch = getattr(args, "batch", None) or None
        if fresh and batch:
            parser.error("--fresh and --batch are mutually exclusive.")
        config = _load_config(args)
        return _run(args, config, fresh=fresh, batch=batch)

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
