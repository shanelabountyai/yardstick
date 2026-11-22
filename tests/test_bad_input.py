"""PRD-E: bad input exits 2 with one short message, never a traceback or exit 1 (review items 7 and 13)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.helpers import FAKE_TARGET, GATES, SUITES
from yardstick.cli import app

SUITE = str(SUITES / "support-bot.yaml")
GATE = str(GATES / "support-bot.yaml")
FAKE = f"{sys.executable} {FAKE_TARGET}"


def invoke(*args: str) -> Result:
    return CliRunner().invoke(app, list(args))


def assert_usage_error(r: Result, *needles: str) -> None:
    assert r.exit_code == 2, (r.exit_code, r.output, r.exception)
    assert "Traceback" not in r.output
    assert r.stderr.startswith("error: "), r.stderr
    for n in needles:
        assert n in r.stderr, (n, r.stderr)


@pytest.fixture
def healthy(tmp_path: Path) -> Path:
    out = tmp_path / "healthy.json"
    r = invoke("run", "-s", SUITE, "--cmd", FAKE, "--target-name", "fake", "--no-git", "-o", str(out))
    assert r.exit_code == 0, r.output
    return out


def _latin1(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\xff\xfe not utf-8 \xe9")
    return p


def test_bad_fixed_clock(tmp_path: Path) -> None:
    r = invoke("run", "-s", SUITE, "--cmd", FAKE, "-o", str(tmp_path / "x.json"), "--fixed-clock", "notadate")
    assert_usage_error(r, "notadate")


def test_unterminated_quote_and_non_executable_command(tmp_path: Path) -> None:
    assert_usage_error(
        invoke("run", "-s", SUITE, "--cmd", "python3 'unterminated", "-o", str(tmp_path / "x.json")),
        "quotation",
    )
    script = tmp_path / "noexec.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(script, 0o644)
    r = invoke("run", "-s", SUITE, "--cmd", str(script), "-o", str(tmp_path / "x.json"))
    assert_usage_error(r, "cannot run command")


def test_output_path_is_a_directory(tmp_path: Path, healthy: Path) -> None:
    assert_usage_error(invoke("run", "-s", SUITE, "--cmd", FAKE, "-o", str(tmp_path)), str(tmp_path))
    assert_usage_error(invoke("report", str(healthy), "-o", str(tmp_path)), str(tmp_path))
    r = invoke("gate", str(healthy), "-c", GATE, "-b", str(healthy), "--report", str(tmp_path))
    assert_usage_error(r, str(tmp_path))


def test_files_that_are_not_utf8(tmp_path: Path, healthy: Path) -> None:
    bad = _latin1(tmp_path, "bad.json")
    assert_usage_error(invoke("gate", str(bad), "-c", GATE), "not UTF-8")
    assert_usage_error(invoke("compare", str(bad), str(healthy)), "not UTF-8")
    assert_usage_error(invoke("gate", str(healthy), "-c", str(_latin1(tmp_path, "g.yaml"))), "not UTF-8")
    mapping = tmp_path / "m.yaml"
    mapping.write_text("rows: rows\nid: id\n", encoding="utf-8")
    r = invoke(
        "run", "-s", SUITE, "--results", str(bad), "--mapping", str(mapping), "-o", str(tmp_path / "x")
    )
    assert_usage_error(r, "not UTF-8")


def test_suite_input_that_is_not_json(tmp_path: Path) -> None:
    suite = tmp_path / "s.yaml"
    suite.write_text(
        "name: d\nscorers: [{name: exact}]\nitems:\n"
        "- id: a\n  input: {as_of: 2026-11-14}\n  expected: {exact: x}\n",
        encoding="utf-8",
    )
    r = invoke("run", "-s", str(suite), "--cmd", FAKE, "-o", str(tmp_path / "x.json"))
    assert_usage_error(r, "item 'a'", "not JSON")


def test_results_file_with_nan_run_cost(tmp_path: Path) -> None:
    res = tmp_path / "res.json"
    res.write_text('{"spent": NaN, "rows": [{"id": "faq-reset-password", "answer": "x"}]}', encoding="utf-8")
    mapping = tmp_path / "m.yaml"
    mapping.write_text("rows: rows\nid: id\ntext: answer\nrun_cost_usd: spent\n", encoding="utf-8")
    r = invoke(
        "run", "-s", SUITE, "--results", str(res), "--mapping", str(mapping), "-o", str(tmp_path / "x")
    )
    assert_usage_error(r, "spent")


def test_replay_file_with_an_undeclared_label(tmp_path: Path) -> None:
    suite = tmp_path / "j.yaml"
    suite.write_text(
        "name: j\nscorers:\n- {name: exact}\n- name: llm-judge\n  key: j\n  report_only: true\n"
        "  options: {rubric: r, labels: [good, bad], positive: [good]}\n"
        "items:\n- id: faq-reset-password\n  input: x\n  expected: {exact: x, j: 1.0}\n",
        encoding="utf-8",
    )
    verdicts = tmp_path / "v.json"
    verdicts.write_text(
        json.dumps(
            {"model": "m", "prompt_hash": "p", "source": "s", "labels": ["good", "odd"], "verdicts": {}}
        ),
        encoding="utf-8",
    )
    r = invoke(
        "run", "-s", str(suite), "--cmd", FAKE, "-o", str(tmp_path / "x.json"),
        "--judge", f"replay:{verdicts}", "--judge-budget-usd", "0",
    )  # fmt: skip
    assert_usage_error(r)


def test_wrong_kind_of_file_is_one_short_message(healthy: Path) -> None:
    r = invoke("gate", SUITE, "-c", GATE)
    assert_usage_error(r, "not a run file", "it looks like a suite file")
    assert len(r.stderr.splitlines()) <= 5
    assert "pydantic.dev" not in r.stderr and "input_value" not in r.stderr
    r = invoke("gate", str(healthy), "-c", str(healthy))
    assert_usage_error(r, "not a gate file", "it looks like a run file")
    assert_usage_error(invoke("baseline", "pin", GATE), "not a run file", "it looks like a gate file")


def test_misspelt_scorer_is_named(tmp_path: Path) -> None:
    text = (
        (SUITES / "support-bot.yaml")
        .read_text(encoding="utf-8")
        .replace("name: contains-all", "name: contains-al")
    )
    suite = tmp_path / "s.yaml"
    suite.write_text(text, encoding="utf-8")
    r = invoke("run", "-s", str(suite), "--cmd", FAKE, "-o", str(tmp_path / "x.json"))
    assert_usage_error(r, "unknown scorer 'contains-al'", "available:", "contains-all")


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("rules: []\n", "no rules"),
        ("rules: [{metric: pass_rate, floor: 85}]\n", "between 0 and 1"),
        ("rules: [{metric: 'rate:exact', max_drop: 2}]\n", "between 0 and 1"),
        ("rules: [{metric: pass_rate, floor: true}]\n", "not true/false"),
        ("rules: [{metric: pass_rate, floor: .nan}]\n", "finite"),
        ("rules: [{metric: latency_p95_ms, max: .inf}]\n", "finite"),
    ],
)
def test_gate_file_mistakes_exit_2(tmp_path: Path, healthy: Path, body: str, needle: str) -> None:
    gate = tmp_path / "g.yaml"
    gate.write_text(body, encoding="utf-8")
    assert_usage_error(invoke("gate", str(healthy), "-c", str(gate)), needle)


def test_latency_thresholds_are_not_capped_at_one(tmp_path: Path, healthy: Path) -> None:
    gate = tmp_path / "g.yaml"
    gate.write_text("rules: [{metric: latency_p95_ms, max: 2000}]\n", encoding="utf-8")
    assert invoke("gate", str(healthy), "-c", str(gate), "-b", str(healthy)).exit_code == 0


def test_unknown_slice_lists_the_run_slices(tmp_path: Path, healthy: Path) -> None:
    gate = tmp_path / "g.yaml"
    gate.write_text("rules: [{metric: pass_rate, slice: refusals, floor: 0.5}]\n", encoding="utf-8")
    r = invoke("gate", str(healthy), "-c", str(gate))
    assert r.exit_code == 1
    assert "slice 'refusals' not in run (slices: account, faq, refusal)" in r.stdout


def test_unexpected_errors_point_at_the_debug_switch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Review of PR #8: a bare TypeError/ValueError may be a bug, so the one-line message says how to get the
    traceback, and YARDSTICK_DEBUG=1 lets it through."""
    from yardstick import cli

    def boom(*_: object, **__: object) -> None:
        raise TypeError("unexpected internal error")

    monkeypatch.setattr(cli, "load_suite", boom)
    args = ["run", "-s", SUITE, "--cmd", FAKE, "-o", str(tmp_path / "x.json")]
    r = invoke(*args)
    assert_usage_error(r, "unexpected internal error", "YARDSTICK_DEBUG=1")
    monkeypatch.setenv("YARDSTICK_DEBUG", "1")
    r = invoke(*args)
    assert isinstance(r.exception, TypeError)


@pytest.mark.parametrize(
    "body",
    [
        "min_items: true\nrules: [{metric: pass_rate, floor: 0.5}]\n",
        "rules: [{metric: pass_rate, floor: 0.5, min_items: true}]\n",
    ],
)
def test_min_items_true_is_refused(tmp_path: Path, healthy: Path, body: str) -> None:
    gate = tmp_path / "g.yaml"
    gate.write_text(body, encoding="utf-8")
    assert_usage_error(invoke("gate", str(healthy), "-c", str(gate)), "not true/false")
