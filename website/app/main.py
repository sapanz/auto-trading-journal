import hmac
import os
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db, run_migrations
from .fy import fy_bounds, fy_options
from .insights import generate_weekly_insight
from .matching import ingest_trades, recompute_fifo

Base.metadata.create_all(bind=engine)
run_migrations()

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Trading Journal")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def check_api_key(x_api_key: str = Header(default="")):
    expected = os.environ.get("JOURNAL_API_KEY", "")
    if not expected:
        raise HTTPException(500, "JOURNAL_API_KEY is not configured on the server")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(401, "unauthorized")


@app.get("/api/ping")
def ping():
    return {"status": "ok"}


@app.post("/api/trades")
def api_ingest_trades(
    payload: schemas.TradesPayload,
    db: Session = Depends(get_db),
    _=Depends(check_api_key),
):
    result = ingest_trades(db, [t.to_dict() for t in payload.trades])
    return JSONResponse(result)


@app.delete("/api/trades")
def api_reset_all_data(db: Session = Depends(get_db), _=Depends(check_api_key)):
    """Wipe every trade/position/insight (tags are kept, they're just labels).
    Meant for clearing test data or resetting before a clean re-import —
    there is no undo. Association tables are cleared explicitly first since
    bulk Query.delete() doesn't cascade through them."""
    db.execute(models.position_tags.delete())
    db.execute(models.position_entry_trades.delete())
    db.execute(models.position_exit_trades.delete())
    db.query(models.Position).delete()
    db.query(models.Trade).delete()
    db.query(models.Insight).delete()
    db.commit()
    return JSONResponse({"status": "reset"})


@app.post("/api/positions/recompute")
def api_recompute_positions(db: Session = Depends(get_db), _=Depends(check_api_key)):
    """Rebuild every position from its existing raw trade legs, without
    re-importing anything. Needed after a matching/charges logic change
    (e.g. this deploy's charges.py) since positions for symbols/products
    with no *new* trades otherwise never get touched again."""
    pairs = db.query(models.Trade.tradingsymbol, models.Trade.product).distinct().all()
    for tradingsymbol, product in pairs:
        recompute_fifo(db, tradingsymbol, product)
    db.commit()
    return JSONResponse({"status": "recomputed", "symbol_product_pairs": len(pairs)})


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    closed_q = db.query(models.Position).filter(models.Position.state == "closed")
    total_pnl = closed_q.with_entities(func.coalesce(func.sum(models.Position.net_pnl), 0.0)).scalar()
    total_gross_pnl = closed_q.with_entities(func.coalesce(func.sum(models.Position.pnl), 0.0)).scalar()
    total_charges = closed_q.with_entities(func.coalesce(func.sum(models.Position.charges), 0.0)).scalar()
    total_trades = closed_q.count()
    wins = closed_q.filter(models.Position.is_win == 1).count()
    win_rate = (wins / total_trades * 100.0) if total_trades else 0.0
    open_count = db.query(models.Position).filter(models.Position.state == "open").count()

    recent = (
        db.query(models.Position)
        .filter(models.Position.state == "closed")
        .order_by(models.Position.exit_time.desc())
        .limit(25)
        .all()
    )

    since = date.today() - timedelta(days=30)
    daily_rows = (
        db.query(models.Position.exit_date, func.sum(models.Position.net_pnl))
        .filter(models.Position.state == "closed", models.Position.exit_date >= since)
        .group_by(models.Position.exit_date)
        .order_by(models.Position.exit_date)
        .all()
    )
    chart_labels = [row[0].isoformat() for row in daily_rows]
    chart_values = [round(row[1], 2) for row in daily_rows]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total_pnl": total_pnl,
            "total_gross_pnl": total_gross_pnl,
            "total_charges": total_charges,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "open_count": open_count,
            "recent": recent,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
        },
    )


@app.get("/positions")
def positions_list(
    request: Request,
    db: Session = Depends(get_db),
    state: str | None = None,
    product: str | None = None,
    fy: str | None = None,
):
    order_col = func.coalesce(models.Position.exit_date, models.Position.entry_date)
    query = db.query(models.Position).order_by(
        func.coalesce(models.Position.exit_time, models.Position.entry_time).desc()
    )
    if state in ("open", "closed"):
        query = query.filter(models.Position.state == state)
    if product in ("CNC", "MIS", "NRML"):
        query = query.filter(models.Position.product == product)
    if fy:
        fy_start, fy_end = fy_bounds(fy)
        query = query.filter(order_col >= fy_start, order_col <= fy_end)
    positions = query.limit(500).all()

    bounds = db.query(func.min(order_col), func.max(order_col)).one()
    available_fys = fy_options(bounds[0], bounds[1])

    return templates.TemplateResponse(
        request,
        "positions.html",
        {"positions": positions, "state": state, "product": product, "fy": fy, "available_fys": available_fys},
    )


@app.get("/trades")
def raw_trades(request: Request, db: Session = Depends(get_db)):
    trades = db.query(models.Trade).order_by(models.Trade.exchange_timestamp.desc()).limit(200).all()
    return templates.TemplateResponse(request, "trades.html", {"trades": trades})


@app.get("/positions/{position_id}")
def position_detail(position_id: int, request: Request, db: Session = Depends(get_db)):
    pos = db.get(models.Position, position_id)
    if not pos:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "position_detail.html", {"pos": pos})


@app.post("/positions/{position_id}/notes")
def update_position_notes(
    position_id: int,
    notes: str = Form(""),
    rating: str = Form(""),
    db: Session = Depends(get_db),
):
    pos = db.get(models.Position, position_id)
    if not pos:
        raise HTTPException(404)
    pos.notes = notes
    pos.rating = int(rating) if rating else None
    db.commit()
    return RedirectResponse(url=f"/positions/{position_id}", status_code=303)


@app.get("/insights")
def insights_list(request: Request, db: Session = Depends(get_db)):
    insights = db.query(models.Insight).order_by(models.Insight.period_end.desc()).all()
    return templates.TemplateResponse(request, "insights.html", {"insights": insights})


@app.get("/insights/{insight_id}")
def insight_detail(insight_id: int, request: Request, db: Session = Depends(get_db)):
    insight = db.get(models.Insight, insight_id)
    if not insight:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "insight_detail.html", {"insight": insight})


@app.post("/insights/generate")
def insights_generate(db: Session = Depends(get_db)):
    generate_weekly_insight(db)
    return RedirectResponse(url="/insights", status_code=303)
