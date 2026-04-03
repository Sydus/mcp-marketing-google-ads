"""Entry point per il server MCP Google Ads — Agent24 pattern."""
import json as _json, os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from ads_mcp.coordinator import mcp
from ads_mcp.identity import resolve_credentials, _request_creds
from ads_mcp.session import AlertMiddleware, SessionMiddleware

# Le seguenti importazioni sono necessarie per registrare tool e resource con
# l'oggetto `mcp`, anche se non sono usate direttamente in questo file.
from ads_mcp.tools import search, core, get_resource_metadata  # noqa: F401
from ads_mcp.resources import discovery, metrics, release_notes, segments  # noqa: F401


async def _asgi_json(send, body: dict, status: int) -> None:
    data = _json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data})


class _IdentityMiddleware:
    def __init__(self, app): self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send); return
        if scope.get("path", "") == "/health":
            await self._app(scope, receive, send); return
        headers = dict(scope.get("headers", []))
        api_key = headers.get(b"x-api-key", b"").decode()
        if not api_key:
            await _asgi_json(send, {"error": "Unauthorized"}, 401); return
        creds = await resolve_credentials(api_key, mcp_name="mcp-marketing-google-ads")
        _st = creds.pop("_status", None)
        if _st == 403: await _asgi_json(send, {"error": "Forbidden"}, 403); return
        if _st == 401: await _asgi_json(send, {"error": "Unauthorized"}, 401); return
        token = _request_creds.set(creds)
        try:
            await self._app(scope, receive, send)
        finally:
            _request_creds.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(AlertMiddleware)
app.add_middleware(SessionMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", mcp.streamable_http_app())
app = _IdentityMiddleware(app)


def run_server() -> None:
    uvicorn.run("ads_mcp.server:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8125")))


if __name__ == "__main__":
    run_server()
