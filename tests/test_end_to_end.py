"""End to end through the CLI: the degraded fake target fails the gate, the healthy one passes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import FAKE_TARGET, GATES, SUITES
from yardstick.cli import app

runner = CliRunner()


def _run(suite: str, out: Path, *flags: str) -> None:
    cmd = f"{sys.executable} {FAKE_TARGET} {' '.join(flags)}"
    res = runner.invoke(
        app,
        [
            "run",
            "-s",
            str(SUITES / f"{suite}.yaml"),
            "--cmd",
            cmd,
            "--target-name",
            "fake",
            "--out",
            str(out),
            "--no-git",
            "--fixed-clock",
            "2026-11-14T00:00:00Z",
        ],
    )
    assert res.exit_code == 0, res.output


@pytest.mark.parametrize("suite", ["support-bot", "extraction"])
def test_healthy_passes_degraded_fails(suite: str, tmp_path: Path) -> None:
    baselines = tmp_path / ".yardstick" / "baselines"
    healthy, degraded = tmp_path / "healthy.json", tmp_path / "degraded.json"
    _run(suite, healthy)
    _run(suite, degraded, "--degrade")

    pin = runner.invoke(app, ["baseline", "pin", str(healthy), "--baselines-dir", str(baselines)])
    assert pin.exit_code == 0, pin.output
    assert (baselines / f"{suite}__fake.json").exists()

    gate_cfg = str(GATES / f"{suite}.yaml")
    ok = runner.invoke(app, ["gate", str(healthy), "-c", gate_cfg, "--baselines-dir", str(baselines)])
    assert ok.exit_code == 0, ok.output
    assert "gate PASSED" in ok.output

    report = tmp_path / "report.md"
    bad = runner.invoke(
        app,
        ["gate", str(degraded), "-c", gate_cfg, "--baselines-dir", str(baselines), "--report", str(report)],
    )
    assert bad.exit_code == 1, bad.output
    assert "gate FAILED" in bad.output
    text = report.read_text(encoding="utf-8")
    assert "**Gate: FAILED**" in text
    assert "Newly failing" in text


def test_gate_without_baseline_fails_drop_rules(tmp_path: Path) -> None:
    healthy = tmp_path / "healthy.json"
    _run("support-bot", healthy)
    res = runner.invoke(
        app, ["gate", str(healthy), "-c", str(GATES / "support-bot.yaml"), "--baselines-dir", str(tmp_path)]
    )
    assert res.exit_code == 1
    assert "no baseline" in res.output


def test_report_and_compare_commands(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _run("extraction", a)
    _run("extraction", b, "--degrade")
    cmp = runner.invoke(app, ["compare", str(a), str(b)])
    assert cmp.exit_code == 0, cmp.output
    assert "newly failing: inv-003, inv-006, inv-009" in cmp.output
    rep = runner.invoke(app, ["report", str(b), "-b", str(a), "-g", str(GATES / "extraction.yaml")])
    assert rep.exit_code == 0, rep.output
    assert rep.output.startswith("# Yardstick report: extraction")  # title as in HTML (PRD-F, D-89)


def test_bad_inputs_exit_2(tmp_path: Path) -> None:
    res = runner.invoke(app, ["report", str(tmp_path / "missing.json")])
    assert res.exit_code == 2
    res = runner.invoke(
        app,
        [
            "run",
            "-s",
            str(SUITES / "extraction.yaml"),
            "--cmd",
            "no-such-binary-ys",
            "-o",
            str(tmp_path / "x"),
        ],
    )
    assert res.exit_code == 2
    assert "not found" in res.output


def test_license_and_exit_codes_in_help() -> None:
    """PRD-D: a LICENSE matching pyproject's MIT, and the exit codes in --help (review item 3)."""
    from pathlib import Path

    from typer.testing import CliRunner

    from yardstick.cli import app

    root = Path(__file__).resolve().parent.parent
    assert root.joinpath("LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert 'license = { text = "MIT" }' in root.joinpath("pyproject.toml").read_text(encoding="utf-8")
    for args in (["--help"], ["gate", "--help"]):
        out = " ".join(CliRunner().invoke(app, args).output.split())
        assert "Exit codes: 0 ok (gate passed), 1 gate failed" in out and "2 bad input" in out
