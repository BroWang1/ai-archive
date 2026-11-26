"""``/api/languages`` —— 语种 profile CRUD。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("")
async def list_languages(request: Request) -> List[Dict[str, Any]]:
    cs = request.app.state.config_service
    return cs.list_languages()


@router.get("/{lang_id}")
async def get_language(lang_id: str, request: Request) -> Dict[str, Any]:
    cs = request.app.state.config_service
    path = cs.language_file(lang_id)
    if not path.exists():
        raise HTTPException(404, f"language profile {lang_id!r} not found")
    return cs.load_language(lang_id)


@router.put("/{lang_id}")
async def put_language(lang_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    cs = request.app.state.config_service
    try:
        cs.save_language(lang_id, payload)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"保存失败：{exc}") from exc
    return {"ok": True, "id": lang_id}


@router.delete("/{lang_id}")
async def delete_language(lang_id: str, request: Request) -> Dict[str, Any]:
    cs = request.app.state.config_service
    try:
        cs.delete_language(lang_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"删除失败：{exc}") from exc
    return {"ok": True}


@router.post("/{lang_id}/duplicate")
async def duplicate_language(lang_id: str, payload: Dict[str, Any], request: Request):
    """从一个已存在的 profile 克隆为新语种。``payload = {"target_id": "..."}``。"""
    cs = request.app.state.config_service
    target_id = (payload or {}).get("target_id")
    if not target_id:
        raise HTTPException(400, "target_id 必填")
    src = cs.load_language(lang_id)
    if not src:
        raise HTTPException(404, f"source {lang_id!r} not found")
    src["id"] = target_id
    try:
        cs.save_language(target_id, src)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"保存失败：{exc}") from exc
    return {"ok": True, "id": target_id}
