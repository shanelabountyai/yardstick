"""PRD-C: baseline lookup, messages and file names (review item 5, decision 4 (a))."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import GATES, SUITES, fake_adapter
from yardstick.baseline import baseline_path
from yardstick.cli import app
from yardstick.runner import run_suite
from yardstick.suite_io import load_run, load_suite, save_run

GATE = str(GATES / "support-bot.yaml")


@pytest.fixture
def runs(tmp_path: Path) -> tuple[Path, Path]:
    suite = load_suite(SUITES / "support-bot.yaml")
    healthy, degraded = tmp_path / "healthy.json", tmp_path / "degraded.json"
    save_run(run_suite(suite, fake_adapter()), healthy)
    save_run(run_suite(suite, fake_adapter("--degrade")), degraded)
    return healthy, degraded


def test_report_gate_uses_the_pinned_baseline_like_gate(runs: tuple[Path, Path], tmp_path: Path) -> None:
    healthy, _ = runs
    bdir = str(tmp_path / "bl")
    runner = CliRunner()
    assert runner.invoke(app, ["baseline", "pin", str(healthy), "--baselines-dir", bdir]).exit_code == 0
    g = runner.invoke(app, ["gate", str(healthy), "-c", GATE, "--baselines-dir", bdir])
    assert g.exit_code == 0 and "gate PASSED" in g.stdout
    r = runner.invoke(app, ["report", str(healthy), "--gate", GATE, "--baselines-dir", bdir])
    assert r.exit_code == 0, r.output
    assert "**Gate: PASSED**" in r.stdout or "Gate passed" in r.stdout


def test_missing_baseline_names_the_path_and_the_fix_and_exits_1(
    runs: tuple[Path, Path], tmp_path: Path
) -> None:
    healthy, _ = runs
    bdir = tmp_path / "empty"
    r = CliRunner().invoke(app, ["gate", str(healthy), "-c", GATE, "--baselines-dir", str(bdir)])
    assert r.exit_code == 1
    expected = bdir / "support-bot__fake.json"
    assert f"note: no baseline at {expected}; pin one with: yardstick baseline pin {healthy}" in r.stderr
    assert "no baseline" in r.stdout


def test_pin_says_what_it_replaced(runs: tuple[Path, Path], tmp_path: Path) -> None:
    healthy, degraded = runs
    bdir = str(tmp_path / "bl")
    runner = CliRunner()
    first = runner.invoke(app, ["baseline", "pin", str(healthy), "--baselines-dir", bdir])
    assert "(replaced" not in first.stdout and "(unchanged" not in first.stdout
    again = runner.invoke(app, ["baseline", "pin", str(healthy), "--baselines-dir", bdir])
    assert "(unchanged)" in again.stdout
    old_id = load_run(healthy).run_id
    third = runner.invoke(app, ["baseline", "pin", str(degraded), "--baselines-dir", bdir])
    assert f"(replaced {old_id})" in third.stdout


@pytest.mark.parametrize(
    ("a", "b"),
    [(("日本", "t"), ("中文", "t")), (("a b", "c"), ("a-b", "c")), (("a", "b__c"), ("a__b", "c"))],
)
def test_baseline_names_do_not_collide(a: tuple[str, str], b: tuple[str, str]) -> None:
    assert baseline_path(*a) != baseline_path(*b)


def test_safe_names_keep_their_file_name() -> None:
    assert baseline_path("support-bot", "fake").name == "support-bot__fake.json"
    assert baseline_path("footnote-golden", "dense-sonnet").name == "footnote-golden__dense-sonnet.json"


def test_a_baseline_for_another_suite_or_target_is_refused(runs: tuple[Path, Path], tmp_path: Path) -> None:
    healthy, _ = runs
    bdir = tmp_path / "bl"
    bdir.mkdir()
    # Put another target's run where this one's baseline should be.
    other = load_run(healthy).model_copy(
        update={"target": load_run(healthy).target.model_copy(update={"name": "x"})}
    )
    save_run(other, bdir / "support-bot__fake.json")
    r = CliRunner().invoke(app, ["gate", str(healthy), "-c", GATE, "--baselines-dir", str(bdir)])
    assert r.exit_code == 2 and "is for suite 'support-bot', target 'x'" in r.stderr
