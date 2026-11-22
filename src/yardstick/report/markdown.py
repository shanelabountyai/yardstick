"""Markdown report (PR comments, CI logs)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from typing import Any

from jinja2 import Environment, StrictUndefined

from yardstick import __version__
from yardstick import metrics as metrics_mod
from yardstick.compare import RUN_METRICS
from yardstick.compare import compare as compare_runs
from yardstick.models import Comparison, GateResult, MetricDelta, MetricSet, RateMetric, Run
from yardstick.report.format import NOT_REPORTED, check_text, fmt_delta, fmt_metric, md_cell, md_code, md_text

LABELS = {
    "pass_rate": "Pass rate",
    "mean_score": "Mean score",
    "latency_p50_ms": "Latency p50",
    "latency_p95_ms": "Latency p95",
    "cost_total_usd": "Cost total",
    "cost_per_item_usd": "Cost per item",
}

MAX_FAILING_ROWS = 25


@dataclass(frozen=True)
class _Row:
    data: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(name) from None


def _env() -> Environment:
    env = Environment(
        autoescape=False,  # markdown, not HTML: every free value goes through the `text` or `code` filter
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["text"] = md_text
    env.filters["code"] = md_code
    return env


def _template_source() -> str:
    return resources.files("yardstick.report").joinpath("templates/report.md.j2").read_text(encoding="utf-8")


def _coverage(metric: str, value: str, reported: int, n: int) -> str:
    if value == "not reported" and n and reported:
        return f"not reported ({reported}/{n} items)"
    return value


def fmt_rate(rm: RateMetric | None) -> str:
    """``96.1% (49/51)``; "not reported" when nothing was counted."""
    if rm is None or rm.value is None:
        return NOT_REPORTED
    return f"{fmt_metric('rate:', rm.value)} ({rm.hits}/{rm.total})"


def rate_label(key: str, report_only: set[str]) -> str:
    return f"{key} (report-only)" if key in report_only else key


def report_only_keys(run: Run) -> set[str]:
    return {s.key for r in run.items for s in r.scores if s.report_only}


@dataclass(frozen=True)
class ReportData:
    """Everything a report shows, already formatted. Shared by the markdown and HTML renderers."""

    run: Run
    baseline: Run | None
    m: MetricSet
    gate: GateResult | None
    comparison: Comparison | None
    warnings: list[str]
    summary_rows: list[_Row]
    rate_rows: list[_Row]
    slice_rows: list[_Row]
    slice_rate_rows: list[_Row]
    gate_rows: list[_Row]
    failing_rows: list[_Row]
    failing_total: int
    failing_more: bool
    not_scored: list[str]
    version: str


def build(
    run: Run,
    *,
    baseline: Run | None = None,
    gate: GateResult | None = None,
    allow_suite_change: bool = False,
    cell: Callable[[str], str] = md_cell,
    code: Callable[[str], str] = md_code,
) -> ReportData:
    """Compute and format the report's content. ``cell`` escapes free text and ``code`` renders an
    identifier for the output format (markdown: an escaped code span; HTML: as is, autoescaped later)."""
    m = metrics_mod.compute(run)
    ro = report_only_keys(run) | (report_only_keys(baseline) if baseline is not None else set())
    comparison: Comparison | None = None
    warnings: list[str] = list(gate.warnings) if gate else []
    if baseline is not None:
        comparison = compare_runs(baseline, run, allow_suite_change=allow_suite_change)
        for w in comparison.warnings:
            if w not in warnings:
                warnings.append(w)
    deltas: dict[tuple[str, str | None], MetricDelta] = (
        {(d.metric, d.slice): d for d in comparison.deltas} if comparison else {}
    )

    summary_rows = []
    for metric in RUN_METRICS:
        value = fmt_metric(metric, m.value(metric))
        if metric.startswith("latency"):
            value = _coverage(metric, value, m.latency_reported, m.n_items)
        elif metric.startswith("cost"):
            value = _coverage(metric, value, m.cost_reported, m.n_items)
            if m.cost_source == "run":
                value += " (run total reported by target)"
        d = deltas.get((metric, None))
        summary_rows.append(
            _Row(
                {
                    "label": LABELS[metric],
                    "value": value,
                    "base": fmt_metric(metric, d.a) if d else "",
                    "delta": fmt_delta(metric, d.delta) if d else "",
                }
            )
        )

    rate_rows = []
    # Rate keys of either run, so a rate the baseline had and this run lacks shows as "not reported".
    base_keys = {d.metric[5:] for d in deltas.values() if d.slice is None and d.metric.startswith("rate:")}
    for key in sorted(set(m.rates) | base_keys):
        rm = m.rates.get(key)
        d = deltas.get(("rate:" + key, None))
        rate_rows.append(
            _Row(
                {
                    "label": code(rate_label(key, ro)),
                    "n": rm.n_items if rm else 0,
                    "value": fmt_rate(rm),
                    "raw": rm.value if rm else None,
                    "base": fmt_metric("rate:", d.a) if d else "",
                    "base_raw": d.a if d else None,
                    "delta": fmt_delta("rate:", d.delta) if d else "",
                }
            )
        )

    slice_rate_rows = []
    for name, sm in m.slices.items():
        slice_keys = {
            d.metric[5:] for d in deltas.values() if d.slice == name and d.metric.startswith("rate:")
        }
        for key in sorted(set(sm.rates) | slice_keys):
            rm = sm.rates.get(key)
            d = deltas.get(("rate:" + key, name))
            slice_rate_rows.append(
                _Row(
                    {
                        "slice": cell(name),
                        "label": code(rate_label(key, ro)),
                        "n": rm.n_items if rm else 0,
                        "value": fmt_rate(rm),
                        "delta": fmt_delta("rate:", d.delta) if d else "n/a",
                    }
                )
            )

    slice_rows = []
    for name, sm in m.slices.items():
        d = deltas.get(("pass_rate", name))
        slice_rows.append(
            _Row(
                {
                    "name": cell(name),
                    "raw": sm.pass_rate,
                    "base_raw": d.a if d else None,
                    "n": sm.n_items,
                    "pass_rate": fmt_metric("pass_rate", sm.pass_rate),
                    "mean": fmt_metric("mean_score", sm.mean_score),
                    "delta": fmt_delta("pass_rate", d.delta) if d else "n/a",
                }
            )
        )

    gate_rows = []
    if gate:
        for rr in gate.rules:
            # One check per line, from the rule's numbers (PRD-B). A passing min_items check is left out:
            # the Items column shows it.
            parts = [
                f"{check_text(rr.rule.metric, c)} ({'ok' if c.passed else 'FAIL'})"
                for c in rr.checks
                if not (c.check == "min_items" and c.passed)
            ]
            if rr.note:
                parts.append(rr.note)
            gate_rows.append(
                _Row(
                    {
                        "label": code(rr.rule.label),
                        "current": fmt_metric(rr.rule.metric, rr.current),
                        "base": fmt_metric(rr.rule.metric, rr.baseline)
                        if gate.baseline_run_id
                        else "no baseline",
                        "n": rr.n_items,
                        "min": rr.min_items,
                        "checks": [cell(p) for p in parts],
                        "passed": rr.passed,
                        "report_only": rr.report_only,
                    }
                )
            )

    failing = [r for r in run.items if not r.passed and not r.not_scored]
    not_scored = [r.item_id for r in run.items if r.not_scored]
    failing_rows = []
    for r in failing[:MAX_FAILING_ROWS]:
        gating = [s for s in r.scores if not s.report_only]
        bad = [f"{s.key}: {s.detail}" if s.detail else s.key for s in gating if not s.passed]
        failing_rows.append(
            _Row(
                {
                    "id": code(r.item_id),
                    "slices": cell(", ".join(r.slices) or "-"),
                    "detail": cell("; ".join(bad)[:300]),
                }
            )
        )

    return ReportData(
        run=run,
        baseline=baseline,
        m=m,
        gate=gate,
        comparison=comparison,
        warnings=warnings,
        summary_rows=summary_rows,
        rate_rows=rate_rows,
        slice_rows=slice_rows,
        slice_rate_rows=slice_rate_rows,
        gate_rows=gate_rows,
        failing_rows=failing_rows,
        failing_total=len(failing),
        failing_more=len(failing) > MAX_FAILING_ROWS,
        not_scored=[code(i) for i in not_scored[:MAX_FAILING_ROWS]],
        version=__version__,
    )


def render(
    run: Run,
    *,
    baseline: Run | None = None,
    gate: GateResult | None = None,
    allow_suite_change: bool = False,
) -> str:
    data = build(run, baseline=baseline, gate=gate, allow_suite_change=allow_suite_change)
    text = _env().from_string(_template_source()).render(**vars(data))
    # Headings always get a blank line around them; collapse runs of blank lines left by conditional blocks.
    text = re.sub(r"\n(#{1,6} [^\n]*)\n", r"\n\n\1\n\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
