"""``/api/logs`` —— 日志尾读 + WebSocket 实时推送。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{run_id}")
async def tail(run_id: str, request: Request, limit: int = Query(500, ge=1, le=10000)):
    log_bus = request.app.state.log_bus
    buf = log_bus.tail(run_id, limit=limit)
    if buf:
        return {"source": "memory", "entries": buf}
    # 内存里没了，再读落盘文件
    runner = request.app.state.runner_service
    lines = runner.read_log_file(run_id, tail=limit)
    return {
        "source": "file",
        "entries": [
            {"run_id": run_id, "ts": 0, "stream": "stdout", "line": ln}
            for ln in lines
        ],
    }


@router.websocket("/ws")
async def ws(websocket: WebSocket, run_id: str | None = Query(None)):
    """订阅实时日志流。

    参数：
        run_id: 为空时订阅 ALL（全部 run 的广播）；指定时只接收该 run。
    """
    await websocket.accept()
    log_bus = websocket.app.state.log_bus
    log_bus.bind_loop(asyncio.get_running_loop())

    # 补发历史尾巴
    if run_id:
        for entry in log_bus.tail(run_id, limit=200):
            try:
                import json
                await websocket.send_text(json.dumps(entry, ensure_ascii=False))
            except Exception:  # pylint: disable=broad-except
                await websocket.close()
                return

    queue = await log_bus.subscribe(run_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
        logger.warning("ws loop error: %s", exc)
    finally:
        log_bus.unsubscribe(queue, run_id)
