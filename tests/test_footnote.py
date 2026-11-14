"""Footnote mapping: suite from the golden set, row mapping, the theta' replay, run-level cost."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from typer.testing import CliRunner

from tests.helpers import CLOCK, ROOT
from yardstick import metrics
from yardstick.adapters.footnote import (
    NO_RELEVANT_PASSAGE,
    FootnoteAdapter,
    apply_theta,
    suite_from_golden,
    suite_yaml,
)
from yardstick.cli import app
from yardstick.report.markdown import render
from yardstick.runner import run_suite
from yardstick.suite_io import load_suite, run_to_json

FN = ROOT / "fixtures" / "footnote"
GOLDEN = json.loads((FN / "golden.json").read_text(encoding="utf-8"))
JUDGED = FN / "results" / "answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json"
DENSE = FN / "results" / "answers-dense-claude-haiku-5-5-theta-off-cd1252c6a407-2026-10-28T0056.json"
FTS = FN / "results" / "answers-fts-claude-haiku-5-5-theta-on-cd1252c6a407-2026-10-28T0056.json"


def test_committed_suite_is_generated_from_the_golden_set() -> None:
    suite = suite_from_golden(GOLDEN)
    assert (FN / "suite.yaml").read_text(encoding="utf-8") == suite_yaml(suite)
    assert load_suite(FN / "suite.yaml").content_hash == suite.content_hash
    assert len(suite.items) == 41


def test_cli_suite_command_matches_committed_file(tmp_path: Path) -> None:
    out = tmp_path / "s.yaml"
    res = CliRunner().invoke(app, ["footnote", "suite", str(FN / "golden.json"), "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert out.read_text(encoding="utf-8") == (FN / "suite.yaml").read_text(encoding="utf-8")


def test_suite_scorers_follow_the_scorecard_rules() -> None:
    items = {i.id: i for i in suite_from_golden(GOLDEN).items}
    by_slice: dict[str, list[Any]] = {}
    for g in GOLDEN:
        by_slice.setdefault(g["slice"], []).append(g)
    for g in GOLDEN:
        item = items[g["id"]]
        refusal = g["expected"]["refusal"]
        if refusal == "OUT_OF_SCOPE":
            assert "refusal" not in item.expected
            assert item.expected["out-of-scope"] == {"refusal_code": "OUT_OF_SCOPE"}
        else:
            assert item.expected["refusal"] is (refusal is not None)
        assert ("support" in item.expected) == (g["slice"] in {"A", "M", "V"})
        assert g["slice"] in item.slices
        assert ("A+M" in item.slices) == (g["slice"] in {"A", "M"})
        assert ("A+M+V" in item.slices) == (g["slice"] in {"A", "M", "V"})


def _run(path: Path, theta: float | None = None) -> Any:
    suite = suite_from_golden(GOLDEN)
    return run_suite(suite, FootnoteAdapter("fn", path, theta), clock=CLOCK)


def test_row_mapping_fields() -> None:
    raw = {r["id"]: r for r in json.loads(JUDGED.read_text(encoding="utf-8"))["rows"]}
    run = _run(JUDGED)
    for item in run.items:
        row = raw[item.item_id]
        f = item.output.fields
        assert item.output.refused is (row["status"] == "refused")
        assert f["status"] == row["status"]
        assert f.get("refusal_code") == row["refusal"]
        assert f.get("gate_score") == row["gate"]["score"]
        assert f["verdicts"] == row["verdicts"]
        assert f["pre_call"] is (row["status"] == "refused" and row["refusal"] == NO_RELEVANT_PASSAGE)
        # Footnote reports no per-item telemetry: never invented (YS-04).
        assert item.output.latency_ms is None and item.output.cost_usd is None
    assert run.model == "claude-sonnet-5-5"


def test_run_level_cost_is_spent_usd_and_latency_not_reported() -> None:
    run = _run(JUDGED)
    m = metrics.compute(run)
    assert run.reported_cost_usd == 0.63331
    assert m.cost_source == "run" and m.cost_total_usd == 0.63331
    assert m.cost_per_item_usd == round(0.63331 / 41, 6)
    assert m.latency_p50_ms is None and m.latency_p95_ms is None
    text = render(run)
    assert "run total reported by target" in text
    assert "| Latency p95 | not reported |" in text


def test_judged_cell_pools_sentence_support() -> None:
    m = metrics.compute(_run(JUDGED))
    rm = m.rate("support", "A+M+V")
    assert rm is not None and (rm.hits, rm.total) == (49, 51)
    # An unjudged cell has no verdicts: the rate is not reported, never 0 (YS-04 spirit).
    assert metrics.compute(_run(DENSE)).value("rate:support") is None


def test_results_file_runs_are_deterministic() -> None:
    """YS-01 for results-file targets: same file + suite + clock -> byte-identical run JSON."""
    assert run_to_json(_run(JUDGED)) == run_to_json(_run(JUDGED))
    assert run_to_json(_run(DENSE, 0.52)) == run_to_json(_run(DENSE, 0.52))


_rows = st.fixed_dictionaries(
    {
        "id": st.just("GA-01"),
        "status": st.sampled_from(["answered", "partial", "refused"]),
        "refusal": st.sampled_from([None, "INSUFFICIENT_SUPPORT", "OUT_OF_SCOPE", NO_RELEVANT_PASSAGE]),
        "gate": st.fixed_dictionaries(
            {"score": st.one_of(st.none(), st.floats(0, 1)), "theta": st.just(0.559), "pass": st.booleans()}
        ),
        "verdicts": st.lists(st.sampled_from(["supported", "partial", "unsupported"]), max_size=4),
    }
)


@given(_rows, st.floats(0, 1))
def test_theta_replay_matches_footnote_at_theta(row: dict[str, Any], theta: float) -> None:
    out = apply_theta(row, theta)
    score = row["gate"]["score"]
    if score is None or score >= theta:
        assert out == row  # at/above theta' and fts (no score): unchanged
    else:
        assert out["status"] == "refused" and out["refusal"] == NO_RELEVANT_PASSAGE and out["verdicts"] == []
        assert out["id"] == row["id"] and out["gate"] == row["gate"]
    assert apply_theta(row, None) == row


def test_theta_replay_never_changes_fts_cells() -> None:
    a, b = _run(FTS), _run(FTS, 0.58)
    assert [i.output for i in a.items] == [i.output for i in b.items]
