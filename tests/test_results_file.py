"""results-file adapter: declarative mapping, missing values, malformed files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import CLOCK
from yardstick.adapters.base import AdapterError
from yardstick.adapters.results_file import (
    MISSING,
    RefusedRule,
    ResultsFileAdapter,
    ResultsMapping,
    get_path,
)
from yardstick.cli import app
from yardstick.models import Item, ScorerSpec, Suite
from yardstick.runner import run_suite
from yardstick.suite_io import load_run

MAPPING = ResultsMapping(
    rows="data.rows",
    id="qid",
    text="answer",
    refused=RefusedRule(path="state", values=["refused", "blocked"]),
    latency_ms="ms",
    cost_usd="usd",
    error="err",
    fields={"state": "state", "score": "meta.score"},
    model="model",
    run_cost_usd="total",
)


def _suite(*ids: str) -> Suite:
    return Suite(
        name="rf",
        scorers=[ScorerSpec(name="exact")],
        items=[Item(id=i, input=i, expected={"exact": "yes"}) for i in ids],
    )


def _write(tmp_path: Path, doc: object) -> Path:
    p = tmp_path / "results.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_get_path() -> None:
    doc = {"a": {"b": [10, {"c": 3}]}, "n": None}
    assert get_path(doc, "a.b.0") == 10
    assert get_path(doc, "a.b.1.c") == 3
    assert get_path(doc, "a.b.2") is MISSING
    assert get_path(doc, "a.x") is MISSING
    assert get_path(doc, "a.b.c") is MISSING
    assert get_path(doc, "n") is None
    assert get_path(doc, "") is doc


def test_maps_rows_and_leaves_missing_values_unreported(tmp_path: Path) -> None:
    doc = {
        "model": "m-1",
        "total": 0.25,
        "data": {
            "rows": [
                {"qid": "q1", "answer": "yes", "state": "ok", "ms": 12, "usd": 0.01, "meta": {"score": 0.7}},
                {"qid": "q2", "answer": {"k": 1}, "state": "blocked"},
                {"qid": "q3", "err": "timeout"},
            ]
        },
    }
    adapter = ResultsFileAdapter("t", _write(tmp_path, doc), MAPPING)
    out = adapter.produce(_suite("q1", "q2", "q3").items)
    assert out["q1"].text == "yes" and out["q1"].refused is False
    assert out["q1"].latency_ms == 12 and out["q1"].cost_usd == 0.01
    assert out["q1"].fields == {"score": 0.7, "state": "ok"}
    assert out["q2"].text == '{"k":1}' and out["q2"].refused is True
    assert out["q2"].latency_ms is None and out["q2"].cost_usd is None  # YS-04: never defaulted
    assert out["q2"].fields == {"state": "blocked"}
    assert out["q3"].refused is None and out["q3"].error == "timeout" and out["q3"].text == ""
    meta = adapter.run_meta()
    assert meta.model == "m-1" and meta.cost_usd == 0.25


def test_run_records_model_and_run_cost(tmp_path: Path) -> None:
    doc = {"model": "m-1", "total": 0.3, "data": {"rows": [{"qid": "q1", "answer": "yes"}]}}
    run = run_suite(_suite("q1"), ResultsFileAdapter("t", _write(tmp_path, doc), MAPPING), clock=CLOCK)
    assert run.model == "m-1"
    assert run.reported_cost_usd == 0.3
    assert run.target.kind == "results-file"


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"data": {}}, "no row list"),
        ({"data": {"rows": [1]}}, "not an object"),
        ({"data": {"rows": [{"answer": "x"}]}}, "no string id"),
        ({"data": {"rows": [{"qid": "q1"}, {"qid": "q1"}]}}, "duplicate"),
        ({"data": {"rows": [{"qid": "zz"}]}}, "unknown item id"),
        ({"data": {"rows": [{"qid": "q1", "ms": 1.5}]}}, "not an integer"),
        ({"data": {"rows": [{"qid": "q1", "usd": "1"}]}}, "not a number"),
        ({"data": {"rows": [{"qid": "q1", "ms": -1}]}}, "bad output"),
    ],
)
def test_malformed_files_fail_the_run(tmp_path: Path, doc: object, message: str) -> None:
    adapter = ResultsFileAdapter("t", _write(tmp_path, doc), MAPPING)
    with pytest.raises(AdapterError, match=message):
        adapter.produce(_suite("q1").items)


def test_unreadable_and_non_json_files(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="cannot read"):
        ResultsFileAdapter("t", tmp_path / "nope.json", MAPPING).produce([])
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(AdapterError, match="not JSON"):
        ResultsFileAdapter("t", bad, MAPPING).produce([])


def test_bad_run_level_values(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="not a non-negative number"):
        ResultsFileAdapter("t", _write(tmp_path, {"total": -1}), MAPPING).run_meta()
    with pytest.raises(AdapterError, match="not a string"):
        ResultsFileAdapter("t", _write(tmp_path, {"model": 3}), MAPPING).run_meta()


def test_cli_run_with_a_mapping_file(tmp_path: Path) -> None:
    results = _write(tmp_path, {"rows": [{"id": "q1", "out": "yes"}, {"id": "q2", "out": "no"}]})
    mapping = tmp_path / "map.yaml"
    mapping.write_text("rows: rows\nid: id\ntext: out\n", encoding="utf-8")
    suite = tmp_path / "suite.json"
    suite.write_text(_suite("q1", "q2").model_dump_json(), encoding="utf-8")
    out = tmp_path / "run.json"
    args = ["run", "-s", str(suite), "--results", str(results), "--mapping", str(mapping), "-o", str(out)]
    res = CliRunner().invoke(app, [*args, "--no-git", "--fixed-clock", "2026-11-14T00:00:00Z"])
    assert res.exit_code == 0, res.output
    run = load_run(out)
    assert [i.passed for i in run.items] == [True, False]
    assert run.target.kind == "results-file"


@pytest.mark.parametrize(
    "extra",
    [
        [],  # no target
        ["--cmd", "true", "--results", "x.json"],  # two targets
        ["--results", "x.json"],  # no mapping
        ["--cmd", "true", "--mapping", "footnote"],  # mapping without results
    ],
)
def test_cli_target_options_are_validated(tmp_path: Path, extra: list[str]) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(_suite("q1").model_dump_json(), encoding="utf-8")
    res = CliRunner().invoke(
        app, ["run", "-s", str(suite), "-o", str(tmp_path / "r.json"), "--no-git", *extra]
    )
    assert res.exit_code == 2
