"""项目根一键启动入口。

使用方式（无需 ``pip install -e .``）：

    python main.py run --language vi --fresh
    python main.py config dump --language vi

本脚本做两件事：
    1. 把 ``src/`` 加入 ``sys.path`` 的最前面，让 ``import TiMi_HOK_Game_Translator`` 生效；
    2. 把项目根加入 ``sys.path``，让 ``import conf._bootstrap`` 生效（CLI 的
       配置粘合逻辑需要）。

同时把 cwd 锚定到本脚本所在目录，保证相对路径（``conf/config.yaml``、
``conf/languages/*.json``）无论从哪里启动都能被正确解析。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths() -> Path:
    """把 src/ 与项目根注入 sys.path，并把 cwd 切到项目根。"""
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"

    # 让 `import TiMi_HOK_Game_Translator` 可用
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # 让 `from conf._bootstrap import ...` 可用
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 锚定 cwd —— 配置文件相对路径以项目根为基准
    os.chdir(project_root)
    return project_root


def main() -> int:
    _bootstrap_paths()

    # ``server`` 子命令走独立分支（不侵入 TiMi_HOK_Game_Translator.cli 的 argparser）：
    #   python main.py server                      # 默认 0.0.0.0:8787，同网段可访问
    #   python main.py server --host 127.0.0.1     # 仅本机访问
    #   python main.py server --port 9000          # 自定义端口
    #   python main.py server --reload             # 开发时自动重载
    if len(sys.argv) >= 2 and sys.argv[1] == "server":
        from TiMi_HOK_Game_Translator.server.__main__ import main as server_main
        # 把 "server" 从 argv 中去掉，让下游 argparse 看到的是正常的 flags
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return server_main()

    from TiMi_HOK_Game_Translator.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
