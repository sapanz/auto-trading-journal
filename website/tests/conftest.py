"""Test setup: point the app at a throwaway SQLite file and known secrets
BEFORE app.main is imported (the engine and session secret are read at import
time). Run with:  cd website && pip install -r requirements-dev.txt && pytest
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="journal-tests-")
os.environ["JOURNAL_DB_PATH"] = str(Path(_TMP) / "test.db")
os.environ["JOURNAL_ACCESS_PIN"] = "4321"
os.environ["JOURNAL_API_KEY"] = "test-api-key"
os.environ.pop("DATABASE_URL", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

API_KEY = {"X-Api-Key": "test-api-key"}


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture()
def anon(app):
    """A client with no session. Wipes every trade/position first so each test
    starts from an empty journal."""
    with TestClient(app, follow_redirects=False) as c:
        assert c.delete("/api/trades", headers=API_KEY).status_code == 200
        yield c


@pytest.fixture()
def client(anon):
    """The same client, logged in with the PIN."""
    r = anon.post("/login", data={"pin": "4321", "next": "/"})
    assert r.status_code == 303
    return anon


def leg(trade_id, symbol, side, qty, price, ts, product="MIS"):
    """One Kite-style trade leg in the shape POST /api/trades takes."""
    return {
        "trade_id": trade_id, "order_id": "O" + trade_id, "tradingsymbol": symbol, "exchange": "NSE",
        "product": product, "transaction_type": side, "quantity": qty, "average_price": price,
        "exchange_timestamp": ts, "trade_date": ts[:10],
    }


def ingest(client, *legs):
    r = client.post("/api/trades", json={"trades": list(legs)}, headers=API_KEY)
    assert r.status_code == 200, r.text
    return r.json()
