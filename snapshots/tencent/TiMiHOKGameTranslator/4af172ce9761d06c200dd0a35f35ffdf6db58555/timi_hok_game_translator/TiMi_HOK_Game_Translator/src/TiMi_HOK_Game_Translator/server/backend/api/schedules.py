"""``/api/schedules`` —— 定时任务 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import ScheduleModel
from ..services.scheduler_service import ScheduleEntry

router = APIRouter()


@router.get("")
async def list_schedules(request: Request):
    return request.app.state.scheduler_service.list()


@router.put("/{schedule_id}")
async def upsert_schedule(schedule_id: str, payload: ScheduleModel, request: Request):
    if payload.id != schedule_id:
        raise HTTPException(400, "path id mismatch body id")
    entry = ScheduleEntry(
        id=payload.id,
        language=payload.language,
        cron=payload.cron,
        enabled=payload.enabled,
        fresh=payload.fresh,
        description=payload.description,
    )
    try:
        request.app.state.scheduler_service.upsert(entry)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, request: Request):
    ok = request.app.state.scheduler_service.delete(schedule_id)
    if not ok:
        raise HTTPException(404, "schedule not found")
    return {"ok": True}


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, payload: dict, request: Request):
    enabled = bool((payload or {}).get("enabled", True))
    entry = request.app.state.scheduler_service.toggle(schedule_id, enabled)
    if not entry:
        raise HTTPException(404, "schedule not found")
    return {"ok": True, "enabled": entry.enabled}
