"""Kukkaro's FastAPI app: every endpoint lives under /api (root AGENTS.md §5.4).

Run from backend/:  uvicorn kukkaro.api.main:app --reload   (the web dev server proxies /api to port 8000)

Other workstreams expose `router` (a FastAPI APIRouter) in their own `router.py`, with paths
written WITHOUT the /api prefix (e.g. "/transactions/{tx_id}/receipt"); this file mounts them
under /api. A router that does not exist yet is skipped, so main always runs.

Public demo: if the web app is built (web/dist, or WEB_DIST), it is served at "/" by the same
server, so one process and one URL hold the whole app. The LLM endpoints are rate-limited per
visitor so a public URL cannot burn through the Gemini/Exa credits.
"""
from __future__ import annotations

import importlib
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from kukkaro.api import routes_data
from kukkaro.data import metrics
from kukkaro.data.db import get_conn
from kukkaro.data.settings import REPO_ROOT

log = logging.getLogger("kukkaro.api")

OPTIONAL_ROUTERS = ("kukkaro.coach.router", "kukkaro.receipts.router", "kukkaro.butler.router", "kukkaro.orders.router")
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"]
state: dict = {"data_loaded": False, "routers": []}

# POST path prefix -> (requests, window in seconds) per visitor IP. Set RATE_LIMIT=0 to turn off.
RATE_LIMITS: dict[str, tuple[int, int]] = {"/api/chat": (30, 600), "/api/butler": (15, 600)}
RATE_LIMIT_TEXT = "The public demo allows a limited number of questions per visitor. Please wait a few minutes."
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the dataset and fill DATA's caches once (about 5 s) so the first user request is fast.
    try:
        get_conn()
        metrics.warm_up()
        state["data_loaded"] = True
    except Exception as e:  # the app still starts; /api/health says what is wrong
        log.warning("Data not loaded: %s", e)
    demo = os.environ.get("DEMO_CUSTOMER_ID")
    if state["data_loaded"] and demo:
        try:
            metrics.warm_up(demo)  # also the age-band medians for the demo period
        except metrics.DataError as e:
            log.warning("Warm-up for DEMO_CUSTOMER_ID=%s failed: %s", demo, e)
    yield


app = FastAPI(title="Kukkaro API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Sliding-window limit per visitor on the LLM endpoints. Behind Caddy, the first
    X-Forwarded-For entry is the real visitor (Caddy does not trust a client-sent header)."""
    path = request.url.path
    rule = next((v for k, v in RATE_LIMITS.items() if path.startswith(k)), None)
    if request.method == "POST" and rule and os.environ.get("RATE_LIMIT", "1") != "0":
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")
        limit, window = rule
        q, now = _hits[(ip, path)], time.monotonic()
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return JSONResponse(status_code=429, content={"detail": RATE_LIMIT_TEXT})
        q.append(now)
    return await call_next(request)


@app.exception_handler(metrics.UnknownCustomer)
async def unknown_customer(_: Request, exc: metrics.UnknownCustomer) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(metrics.DataError)
async def bad_input(_: Request, exc: metrics.DataError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "data_loaded": state["data_loaded"],
        "today": metrics.get_today().isoformat() if state["data_loaded"] else None,
        "demo_customer_id": os.environ.get("DEMO_CUSTOMER_ID") or None,
        "routers": state["routers"],
    }


app.include_router(routes_data.router, prefix="/api")

for name in OPTIONAL_ROUTERS:
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name == name:
            log.info("%s not available yet; skipping", name)
            continue
        log.warning("%s failed to import (%s); skipping so the API still runs", name, e)
        continue
    except Exception as e:  # a bug in another workstream's router must not take the API down
        log.warning("%s failed to import (%s); skipping so the API still runs", name, e)
        continue
    app.include_router(module.router, prefix="/api")
    state["routers"].append(name)


def mount_web(target: FastAPI, dist: Path) -> bool:
    """Serve the built web app at "/" (after all /api routes, so they still win)."""
    if not (dist / "index.html").exists():
        return False
    target.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return True


state["web"] = mount_web(app, Path(os.environ.get("WEB_DIST") or REPO_ROOT / "web" / "dist"))
