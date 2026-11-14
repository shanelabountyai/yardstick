"""YS-03: different suite content cannot be compared without --allow-suite-change, and the report says so."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import GATES, SUITES, fake_adapter, run_from_passes
from yardstick.cli import app
from yardstick.compare import compare
from yardstick.gate import evaluate
from yardstick.models import GateConfig, GateRule, Suite
from yardstick.report.markdown import render
from yardstick.runner import run_suite
from yardstick.suite_check import SuiteChangedError
from yardstick.suite_io import load_suite, save_run

CFG = GateConfig(rules=[GateRule(metric="pass_rate", floor=0.0)])


def _changed_suite() -> tuple[Suite, Suite]:
    base = load_suite(SUITES / "support-bot.yaml")
    data = base.model_dump(mode="json")
    data["items"][0]["expected"]["contains-all"] = ["Forgot password"]
    return base, Suite.model_validate(data)


def test_hash_ignores_description_but_not_items() -> None:
    base, changed = _changed_suite()
    assert base.content_hash != changed.content_hash
    data = base.model_dump(mode="json")
    data["description"] = "different words"
    assert Suite.model_validate(data).content_hash == base.content_hash


def test_compare_gate_and_report_refuse_then_warn() -> None:
    base_suite, new_suite = _changed_suite()
    a = run_suite(base_suite, fake_adapter())
    b = run_suite(new_suite, fake_adapter())
    with pytest.raises(SuiteChangedError):
        compare(a, b)
    with pytest.raises(SuiteChangedError):
        evaluate(CFG, b, a)
    with pytest.raises(SuiteChangedError):
        render(b, baseline=a)

    c = compare(a, b, allow_suite_change=True)
    assert c.suite_changed and c.warnings
    g = evaluate(CFG, b, a, allow_suite_change=True)
    assert g.suite_changed
    text = render(b, baseline=a, gate=g, allow_suite_change=True)
    assert "Suite content changed" in text
    assert text.count("Suite content changed") == 1


def test_same_suite_has_no_warning() -> None:
    a = run_from_passes([True, False])
    text = render(a, baseline=a)
    assert "Suite content changed" not in text


def test_cli_exit_codes(tmp_path: pytest.TempPathFactory) -> None:
    from pathlib import Path

    d = Path(str(tmp_path))
    base_suite, new_suite = _changed_suite()
    save_run(run_suite(base_suite, fake_adapter()), d / "a.json")
    save_run(run_suite(new_suite, fake_adapter()), d / "b.json")
    runner = CliRunner()
    gate_cfg = str(GATES / "support-bot.yaml")

    refused = runner.invoke(app, ["gate", str(d / "b.json"), "-c", gate_cfg, "-b", str(d / "a.json")])
    assert refused.exit_code == 2
    assert "allow-suite-change" in refused.output

    allowed = runner.invoke(
        app,
        [
            "gate",
            str(d / "b.json"),
            "-c",
            gate_cfg,
            "-b",
            str(d / "a.json"),
            "--allow-suite-change",
            "--report",
            str(d / "r.md"),
        ],
    )
    assert allowed.exit_code == 0, allowed.output
    assert "Suite content changed" in (d / "r.md").read_text(encoding="utf-8")

    cmp_refused = runner.invoke(app, ["compare", str(d / "a.json"), str(d / "b.json")])
    assert cmp_refused.exit_code == 2
