"""Vercel serverless entrypoint. Vercel's Python runtime looks for an ASGI
app named `app` in this module; it re-exports the real FastAPI app from
app/main.py unchanged so the same codebase runs locally (uvicorn) and on
Vercel (serverless) without duplication.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402,F401
