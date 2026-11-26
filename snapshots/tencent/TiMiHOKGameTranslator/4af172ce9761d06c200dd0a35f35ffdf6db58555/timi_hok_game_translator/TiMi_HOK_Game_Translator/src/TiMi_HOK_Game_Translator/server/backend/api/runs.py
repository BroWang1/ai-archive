"""``/api/runs`` —— 启动 / 停止 / 查询工作流运行。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import RunStartRequest

router = APIRouter()


@router.post("")
async def start_run(payload: RunStartRequest, request: Request):
    runner = request.app.state.runner_service
    rec = runner.start(
        language=payload.language,
        fresh=payload.fresh,
        batch=payload.batch,
        stage=payload.stage,
    )
    return rec.to_public()


@router.get("")
async def list_runs(request: Request, limit: int = 50):
    runner = request.app.state.runner_service
    return runner.list_runs(limit=limit)


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request):
    runner = request.app.state.runner_service
    rec = runner.get(run_id)
    if not rec:
        raise HTTPException(404, "run not found")
    return rec.to_public()


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: Request):
    runner = request.app.state.runner_service
    ok = runner.stop(run_id)
    if not ok:
        raise HTTPException(404, "run not running")
    return {"ok": True}
