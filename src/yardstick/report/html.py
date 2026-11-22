"""Static HTML report (PRD §3 "Report"): one self-contained file, no scripts, no CDN.

Same content as the markdown report (built by :func:`yardstick.report.markdown.build`), autoescaped, plus bar
charts for slice pass rates and per-scorer rates with the baseline marked on each bar. The charts are HTML
and CSS rows, not SVG, so their text keeps the page's size at any width or zoom (decision 8 (b), D-90).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from jinja2 import Environment, StrictUndefined

from yardstick.models import GateResult, Run
from yardstick.report import markdown
from yardstick.report.format import NOT_REPORTED, fmt_metric

#: Suffix of report-only scorer labels (``markdown.rate_label``).
RO = " (report-only)"


@dataclass(frozen=True)
class Bar:
    """One chart row: label, this run's value (a fraction, None = not reported), the baseline's, and the
    texts shown. Widths are percentages of the track (D-90)."""

    label: str
    value: float | None
    baseline: float | None
    text: str
    base_text: str = ""
    report_only: bool = False

    @property
    def pct(self) -> float:
        return round(min(max(self.value or 0.0, 0.0), 1.0) * 100, 2)

    @property
    def base_pct(self) -> float:
        return round(min(max(self.baseline or 0.0, 0.0), 1.0) * 100, 2)


@dataclass(frozen=True)
class Chart:
    title: str
    kind: str
    bars: list[Bar]
    has_baseline: bool


def _identity(text: str) -> str:
    return text


def _env() -> Environment:
    return Environment(
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _template_source() -> str:
    return (
        resources.files("yardstick.report").joinpath("templates/report.html.j2").read_text(encoding="utf-8")
    )


def render_html(
    run: Run,
    *,
    baseline: Run | None = None,
    gate: GateResult | None = None,
    allow_suite_change: bool = False,
) -> str:
    data = markdown.build(
        run,
        baseline=baseline,
        gate=gate,
        allow_suite_change=allow_suite_change,
        cell=_identity,
        code=_identity,
    )
    has_base = data.comparison is not None
    charts = []
    if data.slice_rows:
        bars = [
            Bar(r.name, r.raw, r.base_raw, r.pass_rate, fmt_metric("pass_rate", r.base_raw))
            for r in data.slice_rows
        ]
        charts.append(Chart("Pass rate by slice", "slices", bars, has_base))
    if data.rate_rows:
        bars = [
            Bar(r.label, r.raw, r.base_raw, r.value, fmt_metric("rate:", r.base_raw), r.label.endswith(RO))
            for r in data.rate_rows
        ]
        charts.append(Chart("Rate by scorer", "rates", bars, has_base))
    # "Mean score" duplicates "Pass rate" when every scorer is pass/fail; hide it then (review item 14).
    m = data.m
    hide_mean = m.mean_score == m.pass_rate and all(sm.mean_score == sm.pass_rate for sm in m.slices.values())
    text = (
        _env()
        .from_string(_template_source())
        .render(
            **vars(data),
            charts=charts,
            hide_mean=hide_mean,
            NOT_REPORTED=NOT_REPORTED,
        )
    )
    return text.rstrip() + "\n"
