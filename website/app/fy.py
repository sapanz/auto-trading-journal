"""Indian financial year (April 1 - March 31) helpers."""
import datetime as dt


def fy_label_for_date(d: dt.date) -> str:
    start_year = d.year if d.month >= 4 else d.year - 1
    return "%d-%02d" % (start_year, (start_year + 1) % 100)


def fy_bounds(fy_label: str) -> tuple[dt.date, dt.date]:
    """'2025-26' -> (2025-04-01, 2026-03-31)."""
    start_year = int(fy_label.split("-")[0])
    return dt.date(start_year, 4, 1), dt.date(start_year + 1, 3, 31)


def fy_options(earliest: dt.date, latest: dt.date) -> list[str]:
    """All FY labels spanning [earliest, latest], most recent first."""
    if earliest is None or latest is None:
        return [fy_label_for_date(dt.date.today())]
    start = int(fy_label_for_date(earliest).split("-")[0])
    end = int(fy_label_for_date(latest).split("-")[0])
    return ["%d-%02d" % (y, (y + 1) % 100) for y in range(end, start - 1, -1)]
