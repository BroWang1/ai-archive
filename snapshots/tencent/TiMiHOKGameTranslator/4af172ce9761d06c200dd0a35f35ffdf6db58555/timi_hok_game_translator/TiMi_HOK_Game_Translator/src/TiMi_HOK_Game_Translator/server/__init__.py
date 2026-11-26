"""TiMi_HOK_Game_Translator Web 服务端（前后端一体）。

目录结构：

* :mod:`TiMi_HOK_Game_Translator.server.backend` —— FastAPI 后端（API + 服务层）
* :mod:`TiMi_HOK_Game_Translator.server.frontend` —— 静态前端资源（HTML/CSS/JS）

启动方式::

    python -m TiMi_HOK_Game_Translator.server            # 等价于 python main.py server（默认 0.0.0.0:8787）
    python main.py server --host 127.0.0.1 --port 8787   # 仅本机访问
    python main.py server --port 9000      # 自定义端口，同网段可用 http://<本机IP>:9000/ 访问

前端默认挂载在 ``/`` 根路径，API 挂载在 ``/api/*``，日志实时推送通道
位于 ``/api/logs/ws``。
"""

from .app import create_app, run

__all__ = ["create_app", "run"]
