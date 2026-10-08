import hmac
import os
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import analytics, benchmark, models, schemas, sectors, settings, tax_report
from .database import Base, engine, get_db, run_migrations
from .fy import fy_bounds, fy_label_for_date, fy_options
from .insights import generate_weekly_insight
from .matching import group_by_order, ingest_trades, recompute_fifo

Base.metadata.create_all(bind=engine)
run_migrations()

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Trading Journal")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Paths a visitor must reach without having entered the PIN: the login
# page itself, static assets, and the machine-to-machine API endpoints
# that already have their own JOURNAL_API_KEY auth (the fetcher cron has
# no browser session and shouldn't need one).
_PUBLIC_API_ROUTES = {
    ("POST", "/api/trades"),
    ("DELETE", "/api/trades"),
    ("POST", "/api/positions/recompute"),
    ("GET", "/api/ping"),
}


@app.middleware("http")
async def require_pin_auth(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/static/")
        or path == "/login"
        or (request.method, path) in _PUBLIC_API_ROUTES
    ):
        return await call_next(request)
    if not request.session.get("authenticated"):
        return RedirectResponse(url=f"/login?next={path}", status_code=303)
    return await call_next(request)


# Registered AFTER require_pin_auth: Starlette's add_middleware() (which
# @app.middleware("http") also goes through) inserts each new middleware
# at the front of the stack, so whichever is added LAST ends up outermost
# and runs FIRST on a request. SessionMiddleware needs to run before
# require_pin_auth so request.session exists by the time it's checked --
# reversing this order breaks with "SessionMiddleware must be installed".
#
# Signs the session cookie -- reuses JOURNAL_API_KEY if no dedicated
# secret is set (both are already-required secrets in production; a
# fixed fallback is only ever hit in unconfigured local dev).
_SESSION_SECRET = (
    os.environ.get("JOURNAL_SESSION_SECRET")
    or os.environ.get("JOURNAL_API_KEY")
    or "insecure-local-dev-only-session-secret"
)
app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET, max_age=60 * 60 * 24 * 30)


@app.get("/login")
def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})


@app.post("/login")
def login_submit(request: Request, pin: str = Form(...), next: str = Form("/")):
    expected_pin = os.environ.get("JOURNAL_ACCESS_PIN", "")
    if not expected_pin:
        raise HTTPException(500, "JOURNAL_ACCESS_PIN is not configured on the server")
    if not hmac.compare_digest(pin.strip(), expected_pin):
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": "Incorrect PIN"}, status_code=401
        )
    request.session["authenticated"] = True
    return RedirectResponse(url=next or "/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


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
    """Deliberately light on charts -- Analytics already covers the
    equity curve, monthly breakdown, and everything else in depth. This
    page is the daily-glance summary plus the quote slider."""
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
        },
    )


@app.get("/analytics")
def analytics_page(request: Request, db: Session = Depends(get_db), fy: str | None = None):
    closed_q = db.query(models.Position).filter(models.Position.state == "closed")
    bounds = closed_q.with_entities(func.min(models.Position.exit_date), func.max(models.Position.exit_date)).one()
    available_fys = fy_options(bounds[0], bounds[1])
    current_fy_label = fy_label_for_date(date.today())
    selected_fy = fy if fy in available_fys else (available_fys[0] if available_fys else current_fy_label)
    fy_start, fy_end = fy_bounds(selected_fy)

    positions = (
        db.query(models.Position)
        .filter(
            models.Position.state == "closed",
            models.Position.exit_date >= fy_start,
            models.Position.exit_date <= fy_end,
        )
        .order_by(models.Position.exit_time.asc())
        .all()
    )
    daily_capital_rows = (
        db.query(models.Position.exit_date, func.sum(models.Position.net_pnl), func.sum(models.Position.entry_value))
        .filter(
            models.Position.state == "closed",
            models.Position.exit_date >= fy_start,
            models.Position.exit_date <= fy_end,
        )
        .group_by(models.Position.exit_date)
        .order_by(models.Position.exit_date)
        .all()
    )
    daily_rows = [(d, pnl) for d, pnl, _ in daily_capital_rows]

    cumulative, drawdown = analytics.build_equity_curve(daily_rows)
    weekday_labels, weekday_values, weekday_counts = analytics.weekday_breakdown(positions)
    hour_labels, hour_values = analytics.hour_breakdown(positions)
    hist_labels, hist_counts = analytics.pnl_histogram(positions)
    heatmap_weeks, heatmap_months = analytics.calendar_heatmap(daily_rows, fy_start, fy_end)

    is_current_fy = selected_fy == current_fy_label
    forecast = analytics.project_forward(daily_rows, cumulative, fy_end) if is_current_fy else None

    total_pnl_all_time = closed_q.with_entities(func.sum(models.Position.net_pnl)).scalar() or 0.0
    capital = _parse_float(settings.get_setting(db, RISK_CAPITAL_KEY, "0"), 0.0)
    cagr = analytics.compute_cagr(capital, total_pnl_all_time, bounds[0], date.today())

    benchmark_data = None
    if daily_rows:
        benchmark_symbol = os.environ.get("JOURNAL_BENCHMARK_SYMBOL", "NIFTY50")
        bench_start, bench_end = daily_rows[0][0], min(fy_end, date.today())
        try:
            cache_ok = benchmark.ensure_cached(db, benchmark_symbol, bench_start, bench_end)
            prices = benchmark.get_cached_closes(db, benchmark_symbol, bench_start, bench_end) if cache_ok else []
        except Exception:
            prices = []
        if prices:
            bench_labels, bench_values = benchmark.normalize_to_100(prices)
            benchmark_data = {
                "symbol": benchmark_symbol,
                "labels": bench_labels,
                "values": bench_values,
                "your_series": benchmark.your_capital_weighted_series(daily_capital_rows),
            }

    return templates.TemplateResponse(
        request,
        "analytics.html",
        {
            "fy": selected_fy,
            "available_fys": available_fys,
            "current_fy_label": current_fy_label,
            "is_current_fy": is_current_fy,
            "stats": analytics.trade_stats(positions),
            "streaks": analytics.streaks(positions),
            "equity_labels": [d.isoformat() for d, _ in daily_rows],
            "cumulative": cumulative,
            "drawdown": drawdown,
            "max_drawdown": min(drawdown) if drawdown else 0.0,
            "weekday_labels": weekday_labels,
            "weekday_values": weekday_values,
            "weekday_counts": weekday_counts,
            "hour_labels": hour_labels,
            "hour_values": hour_values,
            "symbol_rows": analytics.symbol_breakdown(positions),
            "product_rows": analytics.product_breakdown(positions),
            "tag_rows": analytics.tag_breakdown(positions),
            "heatmap_weeks": heatmap_weeks,
            "heatmap_months": heatmap_months,
            "hist_labels": hist_labels,
            "hist_counts": hist_counts,
            "forecast": forecast,
            "benchmark_data": benchmark_data,
            "cagr": cagr,
        },
    )


@app.get("/tax-report")
def tax_report_page(request: Request, db: Session = Depends(get_db), fy: str | None = None):
    closed_q = db.query(models.Position).filter(models.Position.state == "closed")
    bounds = closed_q.with_entities(func.min(models.Position.exit_date), func.max(models.Position.exit_date)).one()
    available_fys = fy_options(bounds[0], bounds[1])
    selected_fy = fy if fy in available_fys else (available_fys[0] if available_fys else fy_label_for_date(date.today()))
    fy_start, fy_end = fy_bounds(selected_fy)

    positions = (
        closed_q.filter(models.Position.exit_date >= fy_start, models.Position.exit_date <= fy_end)
        .order_by(models.Position.exit_date.asc())
        .all()
    )
    report = tax_report.build_report(positions)

    return templates.TemplateResponse(
        request,
        "tax_report.html",
        {"fy": selected_fy, "available_fys": available_fys, "report": report},
    )


@app.get("/api/tax-report/export")
def tax_report_export(db: Session = Depends(get_db), fy: str | None = None):
    closed_q = db.query(models.Position).filter(models.Position.state == "closed")
    bounds = closed_q.with_entities(func.min(models.Position.exit_date), func.max(models.Position.exit_date)).one()
    available_fys = fy_options(bounds[0], bounds[1])
    selected_fy = fy if fy in available_fys else (available_fys[0] if available_fys else fy_label_for_date(date.today()))
    fy_start, fy_end = fy_bounds(selected_fy)

    positions = (
        closed_q.filter(models.Position.exit_date >= fy_start, models.Position.exit_date <= fy_end)
        .order_by(models.Position.exit_date.asc())
        .all()
    )
    csv_body = tax_report.export_csv(tax_report.build_report(positions))
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="tax_report_FY{selected_fy}.csv"'},
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

    open_positions = db.query(models.Position).filter(models.Position.state == "open").all()
    sector_rows, total_invested = sectors.portfolio_breakdown(db, open_positions)

    return templates.TemplateResponse(
        request,
        "positions.html",
        {
            "positions": positions,
            "state": state,
            "product": product,
            "fy": fy,
            "available_fys": available_fys,
            "sector_rows": sector_rows,
            "total_invested": total_invested,
        },
    )


@app.post("/positions/refresh-sectors")
def refresh_sectors(db: Session = Depends(get_db)):
    symbols = [
        row[0] for row in
        db.query(models.Position.tradingsymbol).filter(models.Position.state == "open").distinct().all()
    ]
    sectors.refresh_symbols(db, symbols)
    return RedirectResponse(url="/positions?state=open", status_code=303)


@app.get("/trades")
def raw_trades(request: Request, db: Session = Depends(get_db), symbol: str = ""):
    query = db.query(models.Trade).order_by(models.Trade.exchange_timestamp.desc()).limit(1000)
    if symbol:
        query = query.filter(models.Trade.tradingsymbol.ilike(f"%{symbol.strip()}%"))
    orders = group_by_order(query.all(), descending=True)[:200]
    return templates.TemplateResponse(request, "trades.html", {"orders": orders, "symbol": symbol})


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


@app.post("/positions/{position_id}/tags")
def add_position_tag(position_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    """Attach a user-defined strategy tag (created on first use, distinct
    from the automatic discipline tags applied by matching.py)."""
    pos = db.get(models.Position, position_id)
    if not pos:
        raise HTTPException(404)
    name = name.strip()
    if name:
        tag = db.query(models.Tag).filter_by(name=name).first()
        if not tag:
            tag = models.Tag(name=name, css_class="tag-custom", is_system=0)
            db.add(tag)
            db.flush()
        if tag not in pos.tags:
            pos.tags.append(tag)
        db.commit()
    return RedirectResponse(url=f"/positions/{position_id}", status_code=303)


@app.post("/positions/{position_id}/tags/{tag_id}/remove")
def remove_position_tag(position_id: int, tag_id: int, db: Session = Depends(get_db)):
    pos = db.get(models.Position, position_id)
    if not pos:
        raise HTTPException(404)
    tag = db.get(models.Tag, tag_id)
    if not tag:
        raise HTTPException(404)
    if tag.is_system:
        raise HTTPException(400, "Automatic discipline tags can't be removed manually")
    if tag in pos.tags:
        pos.tags.remove(tag)
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


RISK_CAPITAL_KEY = "risk_capital"
RISK_PERCENT_KEY = "risk_percent"
DEFAULT_RISK_PERCENT = "1.0"


def _parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@app.get("/risk-management")
def risk_management_page(request: Request, db: Session = Depends(get_db)):
    capital_str = settings.get_setting(db, RISK_CAPITAL_KEY, "0")
    risk_percent_str = settings.get_setting(db, RISK_PERCENT_KEY, DEFAULT_RISK_PERCENT)
    return templates.TemplateResponse(
        request,
        "risk_management.html",
        {
            "capital": capital_str,
            "risk_percent": risk_percent_str,
            "capital_value": _parse_float(capital_str, 0.0),
            "risk_percent_value": _parse_float(risk_percent_str, 1.0),
            "error": None,
        },
    )


@app.post("/risk-management/settings")
def update_risk_settings(
    request: Request,
    db: Session = Depends(get_db),
    capital: str = Form(...),
    risk_percent: str = Form(...),
):
    error = None
    try:
        float(capital)
        float(risk_percent)
    except ValueError:
        error = "Capital and Risk % must both be numbers."

    if error:
        return templates.TemplateResponse(
            request,
            "risk_management.html",
            {
                "capital": capital,
                "risk_percent": risk_percent,
                "capital_value": _parse_float(capital, 0.0),
                "risk_percent_value": _parse_float(risk_percent, 1.0),
                "error": error,
            },
            status_code=400,
        )

    settings.set_setting(db, RISK_CAPITAL_KEY, capital)
    settings.set_setting(db, RISK_PERCENT_KEY, risk_percent)
    return RedirectResponse(url="/risk-management", status_code=303)
