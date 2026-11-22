"""PRD-B: one formatter states each gate check as value first, requirement in brackets (decision 1 (a))."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tests.helpers import GATES, SUITES, fake_adapter, run_from_passes
from yardstick.cli import app
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule
from yardstick.report.format import check_text
from yardstick.report.markdown import render
from yardstick.runner import run_suite
from yardstick.suite_io import load_suite, save_run


def _rule(passes: list[bool], base: list[bool] | None, **kw: object) -> list[str]:
    run = run_from_passes(passes)
    baseline = run_from_passes(base) if base is not None else None
    res = evaluate(GateConfig(rules=[GateRule(metric="pass_rate", **kw)]), run, baseline)
    rr = res.rules[0]
    return [check_text(rr.rule.metric, c) for c in rr.checks]


def test_floor_and_drop_read_value_first() -> None:
    # 7/12 = 58.3% against a 100% baseline: the README quick start's degraded run.
    texts = _rule([True] * 7 + [False] * 5, [True] * 12, floor=0.85, max_drop=0.02)
    assert texts == ["12 items (min 1)", "58.3% (floor 85.0%)", "dropped 41.7 pt (max 2.0 pt)"]


def test_a_rise_is_never_a_negative_drop() -> None:
    texts = _rule([True] * 10, [True] * 5 + [False] * 5, max_drop=0.02)
    assert texts[-1] == "rose 50.0 pt (max drop 2.0 pt)"
    assert _rule([True] * 4, [True] * 4, max_drop=0.0)[-1] == "no change (max drop 0.0 pt)"


def test_failed_check_never_prints_two_equal_numbers() -> None:
    texts = _rule([True] * 1699 + [False] * 301, None, floor=0.85)
    assert texts[1] == "84.95% (floor 85.0%)"
    drop = _rule([True] * 179 + [False] * 21, [True] * 180 + [False] * 20, max_drop=0.0045)
    assert drop[-1] == "dropped 0.5 pt (max 0.45 pt)"


def test_max_rise_and_max_wording() -> None:
    run = run_from_passes([True], latency=[1500])
    base = run_from_passes([True], latency=[1000])
    cfg = GateConfig(rules=[GateRule(metric="latency_p95_ms", max=1200, max_rise=100)])
    rr = evaluate(cfg, run, base).rules[0]
    assert [check_text(rr.rule.metric, c) for c in rr.checks][1:] == [
        "1500 ms (max 1200 ms)",
        "rose 500 ms (max 100 ms)",
    ]


def test_terminal_and_report_use_the_same_text(tmp_path: Path) -> None:
    suite = load_suite(SUITES / "support-bot.yaml")
    healthy = tmp_path / "h.json"
    degraded = tmp_path / "d.json"
    save_run(run_suite(suite, fake_adapter()), healthy)
    save_run(run_suite(suite, fake_adapter("--degrade")), degraded)
    report = tmp_path / "r.md"
    r = CliRunner().invoke(
        app,
        [
            "gate",
            str(degraded),
            "-c",
            str(GATES / "support-bot.yaml"),
            "-b",
            str(healthy),
            "--report",
            str(report),
        ],
    )
    assert r.exit_code == 1
    line = next(x for x in r.output.splitlines() if x.startswith("FAIL") and "pass_rate " in x)
    assert line.split(None, 2)[2] == "58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)"
    md = report.read_text()
    assert "58.3% (floor 85.0%) (FAIL)<br>dropped 41.7 pt (max 2.0 pt) (FAIL)" in md
    assert ">=" not in md.split("## Gate", 1)[1]


def test_item_change_bullets_are_separate_lines() -> None:
    base = run_from_passes([True, False, True])
    run = run_from_passes([False, True, True])
    md = render(run, baseline=base)
    lines = [x for x in md.splitlines() if x.startswith("- Newly")]
    assert lines == ["- Newly failing (1): `i0`", "- Newly passing (1): `i1`"]


def test_html_code_does_not_break_mid_word() -> None:
    template = Path("src/yardstick/report/templates/report.html.j2").read_text()
    assert "overflow-wrap: anywhere" not in template
