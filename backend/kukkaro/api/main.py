"""Kukkaro's FastAPI app: every endpoint lives under /api (root AGENTS.md §5.4).

Run from backend/:  uvicorn kukkaro.api.main:app --reload   (the web dev server proxies /api to port 8000)

Other workstreams expose `router` (a FastAPI APIRouter) in their own `router.py`, with paths
written WITHOUT the /api prefix (e.g. "/transactions/{tx_id}/receipt"); this file mounts them
under /api. A router that does not exist yet is skipped, so main always runs.
"""
from __future__ import annotations

import importlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kukkaro.api import routes_data
from kukkaro.data import metrics
from kukkaro.data.db import get_conn

log = logging.getLogger("kukkaro.api")

OPTIONAL_ROUTERS = ("kukkaro.coach.router", "kukkaro.receipts.router", "kukkaro.butler.router")
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"]
state: dict = {"data_loaded": False, "routers": []}


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
