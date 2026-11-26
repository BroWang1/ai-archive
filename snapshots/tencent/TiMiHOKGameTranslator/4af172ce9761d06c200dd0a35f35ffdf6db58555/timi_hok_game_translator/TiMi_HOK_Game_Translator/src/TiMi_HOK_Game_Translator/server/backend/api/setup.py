"""``/api/setup`` —— 首次初始化配置 + 字段 schema + 健康检查。

前端进入时先查询 ``GET /api/setup/status``；若未初始化则引导用户填写
全局 config.yaml + llm.yaml，一键 ``POST /api/setup/init`` 落盘。

字段 schema 由 ``GET /api/setup/schema/{kind}`` 返回，kind ∈
{"global", "llm_profile", "language"}。前端据此渲染结构化表单。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services.field_schema import get_schema

router = APIRouter()


@router.get("/status")
async def get_status(request: Request):
    """返回初始化状态 + 分模块健康检查。"""
    cs = request.app.state.config_service
    return cs.setup_status()


@router.post("/init")
async def init(payload: dict, request: Request):
    """首次初始化：写入 config.yaml + llm.yaml，并记录用户偏好。"""
    cs = request.app.state.config_service
    config = payload.get("config") or {}
    llm = payload.get("llm") or {}
    preferences = payload.get("preferences") or {}
    try:
        cs.save_global_config(config)
        cs.save_llm_registry(llm)
        if preferences:
            cs.save_preferences(preferences)
    except OSError as exc:
        raise HTTPException(500, f"写入配置失败：{exc}") from exc
    return cs.setup_status()


@router.get("/global-config")
async def get_global_config(request: Request):
    cs = request.app.state.config_service
    return cs.load_global_config()


@router.put("/global-config")
async def put_global_config(payload: dict, request: Request):
    cs = request.app.state.config_service
    try:
        cs.save_global_config(payload)
    except OSError as exc:
        raise HTTPException(500, f"写入 config.yaml 失败：{exc}") from exc
    return {"ok": True}


@router.get("/llm")
async def get_llm(request: Request):
    cs = request.app.state.config_service
    return cs.load_llm_registry()


@router.put("/llm")
async def put_llm(payload: dict, request: Request):
    cs = request.app.state.config_service
    try:
        cs.save_llm_registry(payload)
    except OSError as exc:
        raise HTTPException(500, f"写入 llm.yaml 失败：{exc}") from exc
    return {"ok": True}


@router.get("/schema/{kind}")
async def get_field_schema(kind: str):
    """返回面向 UI 的字段清单。kind ∈ {global, llm_profile, language}。"""
    try:
        return {"kind": kind, "fields": get_schema(kind)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/preferences")
async def get_preferences(request: Request):
    return request.app.state.config_service.load_preferences()


@router.put("/preferences")
async def put_preferences(payload: dict, request: Request):
    cs = request.app.state.config_service
    try:
        cs.save_preferences(payload)
    except OSError as exc:
        raise HTTPException(500, f"保存失败：{exc}") from exc
    return {"ok": True}
