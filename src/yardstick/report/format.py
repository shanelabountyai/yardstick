"""Value formatting shared by reports. ``None`` always renders as "not reported" (YS-04)."""

from __future__ import annotations

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


def fmt_limit(metric: str, value: float | None, *, is_change: bool = False) -> str:
    if value is None:
        return ""
    if is_change:
        return fmt_delta(metric, value).lstrip("+")
    return fmt_metric(metric, value)


def md_cell(text: str) -> str:
    """Escape a value for a markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")
