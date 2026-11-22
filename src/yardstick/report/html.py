"""Static HTML report (PRD §3 "Report"): one self-contained file, charts as inline SVG, no scripts, no CDN.

Same content as the markdown report (built by :func:`yardstick.report.markdown.build`), autoescaped, plus bar
charts for slice pass rates and per-scorer rates with the baseline drawn beside the current value.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from jinja2 import Environment, StrictUndefined

from yardstick.models import GateResult, Run
from yardstick.report import markdown
from yardstick.report.format import NOT_REPORTED

CHART_WIDTH = 640
LABEL_WIDTH = 220
VALUE_WIDTH = 120
ROW_HEIGHT = 26


@dataclass(frozen=True)
class Bar:
    label: str
    value: float | None
    baseline: float | None
    text: str

    @property
    def plot_width(self) -> int:
        return CHART_WIDTH - LABEL_WIDTH - VALUE_WIDTH

    def width(self) -> float:
        return round((self.value or 0.0) * self.plot_width, 2)

    def base_x(self) -> float | None:
        if self.baseline is None:
            return None
        return round(LABEL_WIDTH + self.baseline * self.plot_width, 2)


@dataclass(frozen=True)
class Chart:
    title: str
    bars: list[Bar]
    has_baseline: bool

    @property
    def height(self) -> int:
        return ROW_HEIGHT * len(self.bars) + 8


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
        charts.append(
            Chart(
                "Pass rate by slice",
                [Bar(r.name, r.raw, r.base_raw, r.pass_rate) for r in data.slice_rows],
                has_base,
            )
        )
    if data.rate_rows:
        charts.append(
            Chart(
                "Rate by scorer",
                [Bar(r.label, r.raw, r.base_raw, r.value) for r in data.rate_rows],
                has_base,
            )
        )
    text = (
        _env()
        .from_string(_template_source())
        .render(
            **vars(data),
            charts=charts,
            W=CHART_WIDTH,
            LW=LABEL_WIDTH,
            VW=VALUE_WIDTH,
            RH=ROW_HEIGHT,
            NOT_REPORTED=NOT_REPORTED,
        )
    )
    return text.rstrip() + "\n"
