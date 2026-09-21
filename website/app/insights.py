import datetime as dt

from sqlalchemy.orm import Session

from . import models


def generate_weekly_insight(db: Session):
    """Build a digest of the last 7 days of closed positions: stats plus
    templated, rule-based suggestions. Extend the rules below as you learn
    what signals matter to you."""
    today = dt.date.today()
    period_start = today - dt.timedelta(days=7)

    positions = (
        db.query(models.Position)
        .filter(
            models.Position.state == "closed",
            models.Position.exit_date >= period_start,
            models.Position.exit_date <= today,
        )
        .all()
    )
    if not positions:
        return None

    total_pnl = sum(p.pnl for p in positions)
    wins = [p for p in positions if p.is_win]
    win_rate = (len(wins) / len(positions) * 100.0) if positions else 0.0

    by_symbol: dict[str, float] = {}
    for p in positions:
        by_symbol[p.tradingsymbol] = by_symbol.get(p.tradingsymbol, 0.0) + p.pnl
    best_symbol = max(by_symbol, key=by_symbol.get) if by_symbol else "-"
    worst_symbol = min(by_symbol, key=by_symbol.get) if by_symbol else "-"

    big_losses = [p for p in positions if any(t.name == "Big Loss" for t in p.tags)]
    revenge = [p for p in positions if any(t.name == "Possible Revenge Trade" for t in p.tags)]

    mis = [p for p in positions if p.product == "MIS"]
    other = [p for p in positions if p.product != "MIS"]
    mis_win_rate = (len([p for p in mis if p.is_win]) / len(mis) * 100.0) if mis else None
    other_win_rate = (len([p for p in other if p.is_win]) / len(other) * 100.0) if other else None

    suggestions = []
    if win_rate < 40:
        suggestions.append(
            f"Your win rate this week ({win_rate:.1f}%) is low — review entry criteria before adding size."
        )
    if big_losses:
        symbols = ", ".join(sorted({p.tradingsymbol for p in big_losses}))
        suggestions.append(
            f"{len(big_losses)} trade(s) were flagged as Big Loss ({symbols}) — consider tighter stop-losses."
        )
    if revenge:
        suggestions.append(
            f"{len(revenge)} trade(s) looked like revenge trading (bigger size re-entered within 10 minutes "
            "of a loss). Consider a mandatory cooldown after a loss."
        )
    if mis_win_rate is not None and other_win_rate is not None and mis_win_rate < other_win_rate - 15:
        suggestions.append(
            f"Intraday (MIS) win rate ({mis_win_rate:.1f}%) is well below your delivery/positional win rate "
            f"({other_win_rate:.1f}%) — you may be forcing intraday trades."
        )
    if not suggestions:
        suggestions.append("No major red flags this week — keep following your process.")

    body_html = (
        f"<p><strong>Period:</strong> {period_start} to {today}</p>"
        f"<p><strong>Closed trades:</strong> {len(positions)} &nbsp;|&nbsp; "
        f"<strong>Win rate:</strong> {win_rate:.1f}% &nbsp;|&nbsp; "
        f"<strong>Net P&amp;L:</strong> {total_pnl:.2f}</p>"
        f"<p><strong>Best symbol:</strong> {best_symbol} &nbsp;|&nbsp; "
        f"<strong>Worst symbol:</strong> {worst_symbol}</p>"
        f"<ul>{''.join(f'<li>{s}</li>' for s in suggestions)}</ul>"
    )

    insight = models.Insight(
        name=f"Weekly Trading Insight ({period_start} - {today})",
        period_start=period_start,
        period_end=today,
        body_html=body_html,
    )
    db.add(insight)
    db.commit()
    return insight
