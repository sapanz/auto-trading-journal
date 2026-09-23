"""A simplified estimate of how closed positions would bucket into Indian
equity tax categories, built entirely from data already in the journal.

THIS IS NOT TAX ADVICE. It's a convenience view of your own trade data,
not a substitute for a CA or for Zerodha's own official Tax P&L report
(Console -> Reports -> Tax P&L), which is the authoritative source at
filing time. In particular:

- MIS (intraday equity, no delivery) is treated as speculative business
  income under Section 43(5) -- correct for plain intraday equity.
- CNC (delivery) is split into short-term (STCG, held <= 365 days) and
  long-term (LTCG, held > 365 days) capital gains, per the >12-month
  listed-equity threshold. It does NOT account for grandfathering rules,
  the LTCG exemption threshold, or STCG/LTCG rate changes across budgets --
  those depend on the tax year and are for the filer to apply.
- NRML is ambiguous from this app's data alone: it could be F&O (also
  non-speculative business income under Sec 43(5) since derivatives were
  carved out in 2005) or equity margin carried overnight (capital gains
  like CNC). It's bucketed separately as "other" rather than guessed.
"""
import csv
import datetime as dt
import io

STCG_THRESHOLD_DAYS = 365


def classify_position(pos) -> str:
    if pos.product == "MIS":
        return "speculative"
    if pos.product == "CNC":
        holding_days = (pos.exit_date - pos.entry_date).days
        return "ltcg" if holding_days > STCG_THRESHOLD_DAYS else "stcg"
    return "other"


def _summarize(rows):
    return {
        "count": len(rows),
        "gross_pnl": round(sum(r.pnl for r in rows), 2),
        "charges": round(sum(r.charges for r in rows), 2),
        "net_pnl": round(sum(r.net_pnl for r in rows), 2),
    }


def build_report(positions):
    buckets = {"speculative": [], "stcg": [], "ltcg": [], "other": []}
    for p in positions:
        buckets[classify_position(p)].append(p)
    return {
        "speculative": _summarize(buckets["speculative"]),
        "stcg": _summarize(buckets["stcg"]),
        "ltcg": _summarize(buckets["ltcg"]),
        "other": _summarize(buckets["other"]),
        "rows": buckets,
    }


_CATEGORY_LABELS = {
    "speculative": "Speculative Business Income (MIS)",
    "stcg": "Short-Term Capital Gains (CNC, <= 365 days)",
    "ltcg": "Long-Term Capital Gains (CNC, > 365 days)",
    "other": "Other / Ambiguous (NRML)",
}


def export_csv(report: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Category", "Symbol", "Product", "Direction", "Entry Date", "Exit Date",
        "Holding Days", "Quantity", "Buy Value", "Sell Value",
        "Gross P&L", "Charges", "Net P&L",
    ])
    for category, label in _CATEGORY_LABELS.items():
        for p in report["rows"][category]:
            buy_value = p.entry_value if p.direction == "LONG" else p.exit_value
            sell_value = p.exit_value if p.direction == "LONG" else p.entry_value
            writer.writerow([
                label, p.tradingsymbol, p.product, p.direction,
                p.entry_date.isoformat(), p.exit_date.isoformat(),
                (p.exit_date - p.entry_date).days, p.quantity,
                round(buy_value, 2), round(sell_value, 2),
                round(p.pnl, 2), round(p.charges, 2), round(p.net_pnl, 2),
            ])
    return buf.getvalue()
