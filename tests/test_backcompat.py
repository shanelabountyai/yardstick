"""Phase 2 additions are additive: Phase 1 run JSON, suite hashes and run ids do not change (D-24)."""

from __future__ import annotations

import json

from tests.helpers import CLOCK, SUITES, TARGET, run_from_passes
from yardstick import metrics
from yardstick.models import Output, Run, ScorerSpec
from yardstick.report.markdown import render
from yardstick.runner import build_run
from yardstick.suite_io import load_suite, run_to_json

NEW_KEYS = {"fields", "hits", "total", "report_only", "reported_cost_usd"}


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_phase1_style_runs_carry_no_new_keys() -> None:
    run = run_from_passes([True, False, True], latency=[1, 2, 3], cost=[0.1, 0.2, 0.3])
    assert not (_keys(json.loads(run_to_json(run))) & NEW_KEYS)


def test_report_only_false_does_not_change_suite_hash() -> None:
    suite = load_suite(SUITES / "support-bot.yaml")
    assert ScorerSpec(name="exact").model_dump() == {"name": "exact", "key": None, "options": {}}
    assert suite.content_hash == load_suite(SUITES / "support-bot.yaml").content_hash
    assert "report_only" not in json.dumps([s.model_dump(mode="json") for s in suite.scorers])


def test_phase1_run_json_still_loads() -> None:
    run = run_from_passes([True, False])
    again = Run.model_validate_json(run_to_json(run))
    assert again == run and again.reported_cost_usd is None


def test_item_cost_wins_over_run_cost_and_neither_is_invented() -> None:
    """YS-04 with run-level cost: per-item costs if all items have one, else the run total, else nothing."""
    suite = load_suite(SUITES / "support-bot.yaml")
    ids = [i.id for i in suite.items]
    full = {i: Output(text="x", cost_usd=0.001) for i in ids}
    partial = {i: Output(text="x", cost_usd=0.001 if k else None) for k, i in enumerate(ids)}
    m = metrics.compute(build_run(suite, TARGET, full, clock=CLOCK, reported_cost_usd=9.0))
    assert m.cost_source == "items" and m.cost_total_usd == round(0.001 * len(ids), 6)
    m = metrics.compute(build_run(suite, TARGET, partial, clock=CLOCK, reported_cost_usd=0.5))
    assert m.cost_source == "run" and m.cost_total_usd == 0.5
    run = build_run(suite, TARGET, partial, clock=CLOCK)
    m = metrics.compute(run)
    assert m.cost_source is None and m.cost_total_usd is None and m.cost_per_item_usd is None
    assert "| Cost total | not reported" in render(run)
