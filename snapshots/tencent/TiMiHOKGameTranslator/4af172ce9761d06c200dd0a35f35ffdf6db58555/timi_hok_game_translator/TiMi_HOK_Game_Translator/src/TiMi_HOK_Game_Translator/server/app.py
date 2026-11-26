"""FastAPI 应用工厂。

本模块只负责：
    1. 装配 FastAPI 应用、CORS、静态文件挂载；
    2. 注册 ``/api/*`` 路由；
    3. 应用生命周期钩子（启动 scheduler / 关闭时优雅停止子进程）。

真正的业务代码分散在 ``backend/api/*`` 与 ``backend/services/*``。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "TiMiHOKGameTranslator Web 服务依赖 fastapi / uvicorn，请先执行：\n"
        "    pip install fastapi uvicorn[standard]"
    ) from exc

from .backend.api import setup as setup_api
from .backend.api import languages as languages_api
from .backend.api import runs as runs_api
from .backend.api import schedules as schedules_api
from .backend.api import logs as logs_api
from .backend.api import meta as meta_api
from .backend.services.scheduler_service import SchedulerService
from .backend.services.runner_service import RunnerService
from .backend.services.log_bus import LogBus
from .backend.services.config_service import ConfigService

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


def create_app(project_root: Path | None = None) -> FastAPI:
    """创建并返回一个配置好的 ``FastAPI`` 实例。

    参数：
        project_root: TiMiHOKGameTranslator 项目根目录（含 ``conf/``、``main.py``）。
            省略时自动按 ``src/TiMi_HOK_Game_Translator/server/app.py`` 向上三级定位到项目根。
    """
    if project_root is None:
        # <root>/src/TiMi_HOK_Game_Translator/server/app.py → <root>
        project_root = Path(__file__).resolve().parents[3]

    app = FastAPI(
        title="TiMiHOKGameTranslator Web Console",
        version="0.1.0",
        description="游戏本地化流水线可视化配置 / 调度 / 监控面板",
    )

    # CORS：允许开发期任意来源，生产部署可通过反向代理锁定。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- 服务层（单例，挂到 app.state） ----------
    config_service = ConfigService(project_root)
    log_bus = LogBus(max_buffer=5000)
    runner_service = RunnerService(project_root=project_root, log_bus=log_bus)
    scheduler_service = SchedulerService(runner_service=runner_service)

    app.state.project_root = project_root
    app.state.config_service = config_service
    app.state.log_bus = log_bus
    app.state.runner_service = runner_service
    app.state.scheduler_service = scheduler_service

    # ---------- 路由 ----------
    app.include_router(setup_api.router, prefix="/api/setup", tags=["setup"])
    app.include_router(languages_api.router, prefix="/api/languages", tags=["languages"])
    app.include_router(runs_api.router, prefix="/api/runs", tags=["runs"])
    app.include_router(schedules_api.router, prefix="/api/schedules", tags=["schedules"])
    app.include_router(logs_api.router, prefix="/api/logs", tags=["logs"])
    app.include_router(meta_api.router, prefix="/api/meta", tags=["meta"])

    # ---------- 静态前端 ----------
    # 开发/联调场景下，前端 app.js 频繁改动——给静态资源统一加 no-cache 响应头，
    # 让浏览器每次都走条件请求（If-Modified-Since / 304），避免陈旧缓存命中。
    class _NoCacheStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):  # type: ignore[override]
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

    static_dir = FRONTEND_DIR / "static"
    if static_dir.exists():
        app.mount("/static", _NoCacheStaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def _index() -> Any:
        index_html = FRONTEND_DIR / "index.html"
        if not index_html.exists():
            return {"message": "Frontend not built. See src/TiMi_HOK_Game_Translator/server/frontend/."}
        # index.html 自身也禁缓存，确保用户刷新即可加载最新前端代码
        return FileResponse(
            str(index_html),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.on_event("startup")
    async def _startup() -> None:
        scheduler_service.start()
        scheduler_service.restore_from_disk(config_service.schedules_file())
        logger.info("TiMiHOKGameTranslator Web Console started.")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        scheduler_service.shutdown()
        runner_service.shutdown_all()
        logger.info("TiMiHOKGameTranslator Web Console stopped.")

    return app


def run(*, host: str = "0.0.0.0", port: int = 8787, reload: bool = False) -> None:
    """便捷启动器——直接调用 ``uvicorn`` 启动当前 app。

    默认绑定 ``0.0.0.0``：允许同一局域网内的其它机器通过本机 IP 访问。
    若只希望本机访问，可显式传入 ``host="127.0.0.1"``。
    """
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "缺少 uvicorn，请执行：pip install uvicorn[standard]"
        ) from exc

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _print_access_urls(host, port)

    if reload:
        # 开启 reload 时必须以 import string 传入
        uvicorn.run(
            "TiMi_HOK_Game_Translator.server.app:create_app",
            host=host, port=port, reload=True, factory=True,
        )
    else:
        uvicorn.run(create_app(), host=host, port=port)


def _print_access_urls(host: str, port: int) -> None:
    """在启动日志中打印可访问的 URL 列表，方便用户把地址发给同事。"""
    import socket

    banner_lines: list[str] = []
    banner_lines.append("")
    banner_lines.append("=" * 60)
    banner_lines.append(" TiMiHOKGameTranslator Web Console")
    banner_lines.append("=" * 60)

    if host in ("0.0.0.0", "::"):
        banner_lines.append(f"  本机访问: http://127.0.0.1:{port}/")
        # 枚举所有 IPv4 地址，筛掉环回
        try:
            hostname = socket.gethostname()
            addrs = {info[4][0] for info in socket.getaddrinfo(hostname, None, socket.AF_INET)}
            addrs.discard("127.0.0.1")
            for addr in sorted(addrs):
                banner_lines.append(f"  局域网访问: http://{addr}:{port}/")
        except OSError:
            pass
        banner_lines.append("")
        banner_lines.append("  [!] 已监听 0.0.0.0，同网段任意机器均可访问。")
        banner_lines.append(f"  [!] 若无法访问，请检查本机防火墙是否放通 TCP {port}。")
    else:
        banner_lines.append(f"  访问地址: http://{host}:{port}/")

    banner_lines.append("=" * 60)
    banner_lines.append("")

    for line in banner_lines:
        logger.info(line)
