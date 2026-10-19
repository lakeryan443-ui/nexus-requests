from connection_tests import router as connection_test_router
from integration_api import router as integration_router
from fastapi.staticfiles import StaticFiles
from auth_routes import router, current_admin
from pathlib import Path
import os
import subprocess

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(

    title="Nexus Requests",
    docs_url=None,
    redoc_url=None,
)

from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

app.include_router(router)
app.include_router(integration_router)
app.include_router(connection_test_router)

@app.middleware("http")
async def require_admin(request: Request, call_next):
    path = request.url.path

    public_paths = {
        "/health",
        "/login",
        "/setup",
    }

    if path in public_paths or path.startswith("/static/"):
        return await call_next(request)

    if not current_admin(request):
        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )

        return RedirectResponse("/login", status_code=303)

    return await call_next(request)



APP_DIR = Path(__file__).resolve().parent

def get_bot_status():
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "nexus-requests-rebuild.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return "Online" if result.stdout.strip() == "active" else "Offline"
    except (OSError, subprocess.TimeoutExpired):
        return "Unknown"


app.mount("/static", StaticFiles(directory="/opt/nexus-requests-webgui/static"), name="static")

@app.get("/api/status")
async def api_status():
    return {"discord_bot": get_bot_status()}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    from pathlib import Path
    template = Path(__file__).parent / "templates" / "dashboard-v2.html"
    return HTMLResponse(template.read_text(encoding="utf-8"))


async def dashboard():
    status = get_bot_status()
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Nexus Requests</title>
        <style>
            body {
                margin: 0;
                background: #101218;
                color: #f2f4f8;
                font-family: Arial, sans-serif;
            }
            header {
                background: #191d27;
                padding: 24px 32px;
                border-bottom: 1px solid #303644;
            }
            h1 { margin: 0; font-size: 26px; }
            main { padding: 32px; max-width: 1100px; margin: auto; }
            .subtitle { color: #9ba5b7; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 18px;
                margin-top: 30px;
            }
            .card {
                background: #1b202b;
                border: 1px solid #343b4b;
                border-radius: 12px;
                padding: 24px;
            }
            .card h2 { margin-top: 0; font-size: 18px; }
            .status { color: #9ba5b7; }
            footer { margin-top: 40px; color: #8b95a8; }
        </style>
    <link rel="stylesheet" href="/static/nexus-theme.css">
</head>
    <body>
<img class="nexus-logo" src="/static/nexus-requests-logo-v3.png" alt="Nexus Requests">
        <header><h1>Nexus Requests</h1></header>
        <main>
            <h2>Dashboard</h2>
            <p class="subtitle">Self-hosted media request management</p>
            <div class="grid">
                <div class="card">
                    <h2>Discord Bot</h2>
                    <p class="status">Discord bot: __BOT_STATUS__</p>
                </div>
                <div class="card">
                    <h2>Media Requests</h2>
                    <p class="status">Request management coming soon</p>
                </div>
                <div class="card">
                    <h2>Priority Downloads</h2>
                    <p class="status">Job monitoring coming soon</p>
                </div>
                <div class="card">
                    <h2>Integrations</h2>
                    <p class="status">Configuration coming soon</p>
                </div>
            </div>
            <footer>Nexus Requests — Development Preview</footer>
        </main>
    </body>
    </html>
    """.replace("__BOT_STATUS__", status)

@app.get("/health")
async def health():
    return {"status": "ok", "application": "nexus-requests-webgui"}
