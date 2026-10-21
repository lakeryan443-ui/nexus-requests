"""Authenticated account management API."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from account_management import change_credentials
from auth_routes import current_admin
from integration_api import _check_csrf

router = APIRouter(prefix="/api/account")


@router.post("/change")
async def change_account(request: Request):
    username = current_admin(request)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    _check_csrf(request)

    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON required")

    raw = await request.body()
    if len(raw) > 4096:
        raise HTTPException(status_code=413, detail="Request too large")

    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request")

    current_password = payload.get("current_password")
    new_username = payload.get("new_username")
    new_password = payload.get("new_password")

    if not isinstance(current_password, str):
        raise HTTPException(status_code=422, detail="Current password required")

    if new_username is not None and not isinstance(new_username, str):
        raise HTTPException(status_code=422, detail="Invalid username")

    if new_password is not None and not isinstance(new_password, str):
        raise HTTPException(status_code=422, detail="Invalid password")

    try:
        await asyncio.to_thread(
            change_credentials,
            username,
            current_password,
            new_username=new_username,
            new_password=new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    response = JSONResponse(
        {"success": True, "message": "Account updated. Please log in again."},
        headers={"Cache-Control": "no-store"},
    )
    response.delete_cookie("nexus_session", path="/")
    return response
