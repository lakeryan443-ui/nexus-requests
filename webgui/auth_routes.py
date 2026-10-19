import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from accounts import admin_exists, authenticate, create_admin, get_admin_session_version
from auth import create_session, verify_session
from login_pages import login_page, setup_page
from login_security import is_blocked, record_failure, clear_failures

router = APIRouter()


def current_admin(request: Request):
    token = request.cookies.get("nexus_session")

    if not token:
        return None

    session = verify_session(token)

    if not isinstance(session, dict):
        return None

    username = session.get("username")
    version = session.get("version")

    if not username or not version:
        return None

    if version != get_admin_session_version(username):
        return None

    return username


def is_localhost(request: Request):
    return (
        request.client is not None
        and request.client.host in ("127.0.0.1", "::1")
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if admin_exists():
        return RedirectResponse("/login", status_code=303)

    if not is_localhost(request):
        return HTMLResponse(
            "Initial administrator setup must be completed locally.",
            status_code=403,
        )

    return HTMLResponse(setup_page())


@router.post("/setup")
async def setup_post(request: Request):
    if not is_localhost(request):
        return HTMLResponse("Forbidden", status_code=403)

    if admin_exists():
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    confirmation = str(form.get("confirm_password", ""))

    if not secrets.compare_digest(password, confirmation):
        return HTMLResponse(
            setup_page("Passwords do not match."),
            status_code=400,
        )

    try:
        create_admin(username, password)
    except ValueError as exc:
        return HTMLResponse(
            setup_page(str(exc)),
            status_code=400,
        )

    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if not admin_exists():
        return RedirectResponse("/setup", status_code=303)

    if current_admin(request):
        return RedirectResponse("/", status_code=303)

    return HTMLResponse(login_page())


@router.post("/login")
async def login_post(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    ip = request.client.host if request.client else "unknown"

    if is_blocked(ip):
        return HTMLResponse(
            login_page("Too many failed attempts. Try again later."),
            status_code=429,
        )

    if not authenticate(username, password):
        record_failure(ip)
        return HTMLResponse(
            login_page("Invalid username or password."),
            status_code=401,
        )

    clear_failures(ip)
    response = RedirectResponse("/", status_code=303)

    response.set_cookie(
        "nexus_session",
        create_session({
            "username": username,
            "version": get_admin_session_version(username),
        }),
        httponly=True,
        secure=False,  # LAN HTTP development only
        samesite="strict",
        max_age=86400,
        path="/",
    )

    return response


@router.post("/logout")
async def logout_post():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("nexus_session", path="/")
    return response
