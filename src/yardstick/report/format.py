"""Value formatting shared by reports. ``None`` always renders as "not reported" (YS-04)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yardstick.models import CheckResult

NOT_REPORTED = "not reported"

PERCENT_METRICS = {"pass_rate", "mean_score"}


def is_percent(metric: str) -> bool:
    return metric in PERCENT_METRICS or metric.startswith("rate:")


def fmt_metric(metric: str, value: float | int | None) -> str:
    if value is None:
        return NOT_REPORTED
    if is_percent(metric):
        return f"{value * 100:.1f}%"
    if metric.endswith("_ms"):
        return f"{int(value)} ms"
    if metric.endswith("_usd"):
        return f"${value:.6f}"
    return f"{value:g}"


def fmt_delta(metric: str, delta: float | None) -> str:
    if delta is None:
        return "n/a"
    sign = "+" if delta > 0 else ("\u2212" if delta < 0 else "\u00b1")
    mag = abs(delta)
    if is_percent(metric):
        return f"{sign}{mag * 100:.1f} pt"
    if metric.endswith("_ms"):
        return f"{sign}{round(mag)} ms"
    if metric.endswith("_usd"):
        return f"{sign}${mag:.6f}"
    return f"{sign}{mag:g}"


# --------------------------------------------------------------------------- gate checks (PRD-B, D-81)

#: Percent figures are shown with 1 decimal, and with up to this many when 1 would make a failed check look
#: passed (or the reverse). Gate values are compared at 6 dp of a fraction (D-12), i.e. 4 dp of a percent.
_MAX_PCT_DECIMALS = 4


def _unit_number(metric: str, x: float | int, decimals: int) -> tuple[str, Decimal]:
    """``x`` in the metric's display unit: the text and the number the text shows."""
    if is_percent(metric):
        shown = f"{x * 100:.{decimals}f}"
        return f"{shown}%", Decimal(shown)
    if metric.endswith("_ms"):
        return f"{round(x)} ms", Decimal(round(x))
    if metric.endswith("_usd"):
        shown = f"{x:.6f}"
        return f"${shown}", Decimal(shown)
    return f"{x:g}", Decimal(f"{x:g}")


def _unit_change(metric: str, x: float | int, decimals: int) -> tuple[str, Decimal]:
    """A change (always a magnitude) in display units: ``41.7 pt``, ``500 ms``, ``$0.001000``."""
    text, num = _unit_number(metric, abs(x), decimals)
    return (text[:-1] + " pt" if is_percent(metric) else text), num


def _limit_text(metric: str, x: float | int, change: bool) -> tuple[str, Decimal]:
    """A configured threshold, shown exactly (``85.0%``, ``0.45 pt``), never rounded away."""
    if is_percent(metric):
        shown = f"{round(x * 100, _MAX_PCT_DECIMALS):.{_MAX_PCT_DECIMALS}f}".rstrip("0")
        shown = shown + "0" if shown.endswith(".") else shown
        return (f"{shown} pt" if change else f"{shown}%"), Decimal(shown)
    return _unit_change(metric, x, 1) if change else _unit_number(metric, x, 1)


def check_text(metric: str, check: CheckResult) -> str:
    """One gate check as value first, requirement in brackets (decision 1 (a)):

    ``58.3% (floor 85.0%)``, ``dropped 41.7 pt (max 2.0 pt)``, ``rose 22.7 pt (max drop 2.0 pt)``,
    ``22 items (min 8)``. A check with no numbers (``not reported``, ``no baseline``) is its detail.
    """
    if check.check == "min_items" and check.value is not None:
        n = int(check.value)
        return f"{n} item{'' if n == 1 else 's'} (min {check.limit})"
    if check.value is None or check.limit is None:
        return check.detail
    change = check.check in {"max_drop", "max_rise"}
    limit, lim_num = _limit_text(metric, check.limit, change)
    v = check.value
    decimals = 1
    while True:
        text, num = _unit_change(metric, v, decimals) if change else _unit_number(metric, v, decimals)
        signed = -num if change and v < 0 else num
        shows_pass = signed >= lim_num if check.check == "floor" else signed <= lim_num
        if shows_pass == check.passed or decimals >= _MAX_PCT_DECIMALS or not is_percent(metric):
            break
        decimals += 1
    if check.check == "floor":
        return f"{text} (floor {limit})"
    if check.check == "max":
        return f"{text} (max {limit})"
    up, down = ("dropped", "rose") if check.check == "max_drop" else ("rose", "fell")
    if v == 0:
        return f"no change ({check.check.replace('_', ' ')} {limit})"
    if v > 0:
        return f"{up} {text} (max {limit})"
    return f"{down} {text} ({check.check.replace('_', ' ')} {limit})"


def md_cell(text: str) -> str:
    """Escape a value for a markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")
