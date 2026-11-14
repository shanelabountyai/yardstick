"""Markdown report (PR comments, CI logs)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

from jinja2 import Environment, StrictUndefined

from yardstick import __version__
from yardstick import metrics as metrics_mod
from yardstick.compare import RUN_METRICS
from yardstick.compare import compare as compare_runs
from yardstick.models import Comparison, GateResult, MetricDelta, Run
from yardstick.report.format import fmt_delta, fmt_limit, fmt_metric, md_cell

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
    return Environment(
        autoescape=False,  # markdown, not HTML; cells are escaped with md_cell
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _template_source() -> str:
    return resources.files("yardstick.report").joinpath("templates/report.md.j2").read_text(encoding="utf-8")


def _coverage(metric: str, value: str, reported: int, n: int) -> str:
    if value == "not reported" and n and reported:
        return f"not reported ({reported}/{n} items)"
    return value


def render(
    run: Run,
    *,
    baseline: Run | None = None,
    gate: GateResult | None = None,
    allow_suite_change: bool = False,
) -> str:
    m = metrics_mod.compute(run)
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

    slice_rows = []
    for name, sm in m.slices.items():
        d = deltas.get(("pass_rate", name))
        slice_rows.append(
            _Row(
                {
                    "name": md_cell(name),
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
            parts = []
            for c in rr.checks:
                mark = "ok" if c.passed else "FAIL"
                parts.append(f"{c.check}: {_humanise(rr.rule.metric, c.check, c.detail)} ({mark})")
            gate_rows.append(
                _Row(
                    {
                        "label": md_cell(rr.rule.label),
                        "current": fmt_metric(rr.rule.metric, rr.current),
                        "base": fmt_metric(rr.rule.metric, rr.baseline)
                        if gate.baseline_run_id
                        else "no baseline",
                        "n": rr.n_items,
                        "min": rr.min_items,
                        "checks": md_cell("; ".join(parts)),
                        "passed": rr.passed,
                    }
                )
            )

    failing = [r for r in run.items if not r.passed]
    failing_rows = []
    for r in failing[:MAX_FAILING_ROWS]:
        bad = [f"{s.key}: {s.detail}" if s.detail else s.key for s in r.scores if not s.passed]
        if not r.scores:
            bad = ["no scorer applied"]
        failing_rows.append(
            _Row(
                {
                    "id": md_cell(r.item_id),
                    "slices": md_cell(", ".join(r.slices) or "-"),
                    "detail": md_cell("; ".join(bad))[:300],
                }
            )
        )

    text = (
        _env()
        .from_string(_template_source())
        .render(
            run=run,
            baseline=baseline,
            m=m,
            gate=gate,
            comparison=comparison,
            warnings=warnings,
            summary_rows=summary_rows,
            slice_rows=slice_rows,
            gate_rows=gate_rows,
            failing_rows=failing_rows,
            failing_total=len(failing),
            failing_more=len(failing) > MAX_FAILING_ROWS,
            version=__version__,
        )
    )
    # Headings always get a blank line around them; collapse runs of blank lines left by conditional blocks.
    text = re.sub(r"\n(#{1,6} [^\n]*)\n", r"\n\n\1\n\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _humanise(metric: str, check: str, detail: str) -> str:
    """Re-format raw numbers in a check detail using the metric's units."""
    if check in {"min_items", "reported"} or "baseline" in detail:
        return detail
    is_change = check in {"max_drop", "max_rise"}
    nums = _NUM.findall(detail)
    if len(nums) != 2:
        return detail
    a, b = (float(x) for x in nums)
    if is_change:
        word = "drop" if check == "max_drop" else "rise"
        return f"{word} {fmt_limit(metric, a, is_change=True)} <= {fmt_limit(metric, b, is_change=True)}"
    op = ">=" if check == "floor" else "<="
    return f"{fmt_metric(metric, a)} {op} {fmt_metric(metric, b)}"
