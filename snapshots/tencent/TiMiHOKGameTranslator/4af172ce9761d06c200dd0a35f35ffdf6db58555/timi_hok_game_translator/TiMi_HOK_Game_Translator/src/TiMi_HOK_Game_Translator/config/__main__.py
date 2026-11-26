"""``python -m TiMi_HOK_Game_Translator.config`` 命令行入口。

用法::

    python -m TiMi_HOK_Game_Translator.config dump [--format yaml|json] [--no-mask] [-c PATH]

``dump`` 子命令加载当前生效配置并输出到 stdout，默认对敏感字段做脱敏。
"""

from __future__ import annotations

import json
import sys
from typing import Sequence

from .loader import build_argparser, load


def main(argv: Sequence[str] | None = None) -> int:
    """``config`` 子命令入口。

    参数：
        argv: 命令行参数序列，None 时取 sys.argv。
    返回：
        进程退出码。
    """
    parser = build_argparser(prog="python -m TiMi_HOK_Game_Translator.config")
    args = parser.parse_args(argv)

    # 本入口只处理 ``config dump``，其余交给 :mod:`TiMi_HOK_Game_Translator.cli`。
    if (
        getattr(args, "command", None) != "config"
        or getattr(args, "config_command", None) != "dump"
    ):
        parser.print_help()
        return 2

    config = load(cli_args=args)
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
        except ImportError:  # pragma: no cover - PyYAML 是硬依赖
            print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
