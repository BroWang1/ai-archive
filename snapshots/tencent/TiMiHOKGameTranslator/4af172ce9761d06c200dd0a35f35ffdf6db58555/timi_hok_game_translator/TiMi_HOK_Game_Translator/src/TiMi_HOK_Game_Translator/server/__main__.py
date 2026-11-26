"""``python -m TiMi_HOK_Game_Translator.server`` 入口。

读取环境变量 ``GAME_TRANS_TOOLCHAIN_SERVER_HOST`` / ``GAME_TRANS_TOOLCHAIN_SERVER_PORT``
作为默认绑定地址，命令行参数可覆盖之。

默认绑定 ``0.0.0.0``：允许同一局域网内的其它机器通过本机 IP 访问
（例如 ``http://30.23.60.41:8787/``）。若只希望本机访问，可显式传入
``--host 127.0.0.1``，或设置环境变量 ``GAME_TRANS_TOOLCHAIN_SERVER_HOST=127.0.0.1``。
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="TiMiHOKGameTranslator Web Server")
    parser.add_argument("--host", default=os.environ.get("GAME_TRANS_TOOLCHAIN_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("GAME_TRANS_TOOLCHAIN_SERVER_PORT", "8787")))
    parser.add_argument("--reload", action="store_true", help="启用自动重载（开发用）")
    args = parser.parse_args()

    from .app import run
    run(host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
