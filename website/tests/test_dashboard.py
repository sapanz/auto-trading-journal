import json
import re

from conftest import ingest, leg


def payload_from(html: str) -> dict:
    """Pull the JSON the page embeds for dashboard.js."""
    m = re.search(r'<script id="journal-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "the page must embed its data as <script id=\"journal-data\">"
    return json.loads(m.group(1))


def two_round_trips(client):
    ingest(
        client,
        # a winner: bought 2500, sold 2530 -> +300 gross, 45 minutes
        leg("T1", "RELIANCE", "BUY", 10, 2500.0, "2026-11-20 09:20:00"),
        leg("T2", "RELIANCE", "SELL", 10, 2530.0, "2026-11-20 10:05:00"),
        # a loser held under 2 minutes on MIS -> flagged "Quick Scalp"
        leg("T3", "INFY", "BUY", 50, 1500.0, "2026-11-21 11:00:00"),
        leg("T4", "INFY", "SELL", 50, 1496.0, "2026-11-21 11:01:00"),
        # still open: only a buy
        leg("T5", "TCS", "BUY", 5, 3200.0, "2026-11-21 14:00:00", product="CNC"),
    )


def test_home_requires_the_pin(anon):
    r = anon.get("/")
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_home_embeds_closed_positions_oldest_first(client):
    two_round_trips(client)
    r = client.get("/")
    assert r.status_code == 200
    data = payload_from(r.text)
    trades = data["trades"]
    assert [t["sym"] for t in trades] == ["RELIANCE", "INFY"]           # oldest exit first; the open TCS is not a closed trade
    win, loss = trades
    assert (win["prod"], win["dir"], win["qty"]) == ("MIS", "LONG", 10)
    assert (win["entry"], win["exit"], win["date"]) == (2500.0, 2530.0, "2026-11-20")
    assert win["entryTs"] == "2026-11-20T09:20:00" and win["exitTs"] == "2026-11-20T10:05:00"
    assert win["hold"] == 45.0
    assert win["gross"] == 300.0
    assert win["charges"] > 0 and win["net"] == round(win["gross"] - win["charges"], 2)
    assert loss["gross"] == -200.0 and loss["net"] < -200.0              # charges make a loss slightly bigger
    assert "Quick Scalp" in loss["tags"]
    assert data["meta"]["openCount"] == 1


def test_home_renders_with_an_empty_journal(client):
    r = client.get("/")
    assert r.status_code == 200
    data = payload_from(r.text)
    assert data["trades"] == [] and data["meta"]["openCount"] == 0 and data["meta"]["capital"] == 0


def test_capital_from_risk_settings_reaches_the_page(client):
    client.post("/risk-management/settings", data={"capital": "250000", "risk_percent": "1"})
    assert payload_from(client.get("/").text)["meta"]["capital"] == 250000.0


def test_user_text_cannot_break_out_of_the_embedded_json(client):
    two_round_trips(client)
    pid = payload_from(client.get("/").text)["trades"][0]["id"]
    evil = "</script><script>alert(1)</script> & <b>"
    assert client.post(f"/api/positions/{pid}/review", json={"notes": evil, "rating": 3}).status_code == 200
    html = client.get("/").text
    assert "</script><script>alert(1)" not in html                      # tojson escapes < and >
    assert payload_from(html)["trades"][0]["note"] == evil                # ...and the text round-trips intact


def test_review_saves_note_and_rating_and_trims(client):
    two_round_trips(client)
    pid = payload_from(client.get("/").text)["trades"][1]["id"]
    r = client.post(f"/api/positions/{pid}/review", json={"notes": "  chased the open  ", "rating": 2})
    assert r.status_code == 200
    assert r.json() == {"id": pid, "note": "chased the open", "rating": 2}
    saved = payload_from(client.get("/").text)["trades"][1]
    assert (saved["note"], saved["rating"]) == ("chased the open", 2)
    # clearing: empty note, no rating
    r = client.post(f"/api/positions/{pid}/review", json={"notes": "", "rating": None})
    assert r.json() == {"id": pid, "note": "", "rating": None}


def test_review_validates_input_and_missing_ids(client):
    two_round_trips(client)
    pid = payload_from(client.get("/").text)["trades"][0]["id"]
    assert client.post(f"/api/positions/{pid}/review", json={"notes": "x", "rating": 6}).status_code == 422
    assert client.post(f"/api/positions/{pid}/review", json={"notes": "x", "rating": 0}).status_code == 422
    assert client.post(f"/api/positions/{pid}/review", json={"notes": "x" * 5001}).status_code == 422
    assert client.post("/api/positions/999999/review", json={"notes": "x"}).status_code == 404


def test_review_requires_the_pin(anon):
    r = anon.post("/api/positions/1/review", json={"notes": "x"})
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_other_pages_still_load(client):
    two_round_trips(client)
    for path in ("/analytics", "/positions", "/insights", "/risk-management", "/tax-report", "/trades"):
        assert client.get(path).status_code == 200, path
