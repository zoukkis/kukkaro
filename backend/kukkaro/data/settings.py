"""Paths and environment for the DATA workstream. Reads `.env` from the repo root if present."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(REPO_ROOT / ".env", override=False)


def data_dir() -> Path:
    """`DATA_DIR` from the environment. A relative path is resolved against `backend/`
    (so the default `../data` works no matter where the process is started)."""
    raw = os.environ.get("DATA_DIR") or "../data"
    p = Path(raw)
    return (p if p.is_absolute() else BACKEND_DIR / p).resolve()


def raw_dir() -> Path:
    return data_dir() / "raw"


def processed_dir() -> Path:
    return data_dir() / "processed"


def demo_today_env() -> date | None:
    """`DEMO_TODAY` (YYYY-MM-DD) if set, else None."""
    raw = (os.environ.get("DEMO_TODAY") or "").strip()
    return date.fromisoformat(raw) if raw else None
