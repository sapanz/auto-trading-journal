"""Vercel serverless entrypoint. Lives at the repo root (not under
website/) because Vercel builds from the actual repository root unless
"Root Directory" is overridden in project settings — which isn't
available on every plan. This re-exports the same FastAPI app from
website/app/main.py unchanged; no code fork.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "website"))

from app.main import app  # noqa: E402,F401
