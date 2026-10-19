from pathlib import Path

path = Path("app.py")
source = path.read_text()

import_line = "from auth_routes import router, current_admin\n"
if import_line not in source:
    source = import_line + source

# Add authentication routes and protect existing endpoints.
anchor = 'app = FastAPI('
position = source.find(anchor)
if position == -1:
    raise SystemExit("FAIL: FastAPI application not found")

# Insert the protection middleware after the FastAPI app declaration.
# Find the closing parenthesis of the FastAPI constructor.
start = source.find("(", position)
depth = 0
end = None

for i in range(start, len(source)):
    if source[i] == "(":
        depth += 1
    elif source[i] == ")":
        depth -= 1
        if depth == 0:
            end = i + 1
            break

if end is None:
    raise SystemExit("FAIL: Cannot locate FastAPI constructor end")

middleware = '''

from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

app.include_router(router)

@app.middleware("http")
async def require_admin(request: Request, call_next):
    path = request.url.path

    public_paths = {
        "/health",
        "/login",
        "/setup",
    }

    if path in public_paths:
        return await call_next(request)

    if not current_admin(request):
        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )

        return RedirectResponse("/login", status_code=303)

    return await call_next(request)

'''

if 'async def require_admin(' not in source:
    source = source[:end] + middleware + source[end:]

path.write_text(source)
print("Authentication integration: PASS")
