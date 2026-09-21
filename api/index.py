"""Vercel serverless entrypoint. Lives at the repo root (not under
website/) because Vercel builds from the actual repository root unless
"Root Directory" is overridden in project settings — which isn't
available on every plan. This re-exports the same FastAPI app from
website/app/main.py unchanged; no code fork.

Requires DATABASE_URL (Postgres) to be set as an environment variable on
the deployment — serverless functions have no writable local disk, so the
SQLite fallback in app/database.py cannot work here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "website"))

from app.main import app  # noqa: E402,F401
