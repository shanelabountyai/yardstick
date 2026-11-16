"""Phase 3 gate: kappa on Footnote's graded sentences matches its eval:kappa output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from yardstick import footnote_kappa as fk
from yardstick.adapters.footnote import JUDGE_KEY, FootnoteAdapter, suite_from_golden, verdicts_from_answers
from yardstick.cli import app
from yardstick.clock import FixedClock
from yardstick.judge.recorded import load_verdicts, verdict_file_json
from yardstick.kappa import js_fixed, load_calibration
from yardstick.metrics import compute
from yardstick.runner import run_suite

ROOT = Path(__file__).resolve().parent.parent
FN = ROOT / "fixtures" / "footnote"
ANSWERS = FN / "results" / "answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json"
SHEETS = [FN / "grades" / "grades.md", FN / "grades" / "grades-2.md"]
REFERENCE = FN / "kappa-reference.yaml"
CLOCK = FixedClock(datetime(2026, 11, 16, tzinfo=UTC))


@pytest.fixture(scope="module")
def rep() -> fk.Reproduction:
    return fk.reproduce(FN / "golden.json", ANSWERS, SHEETS, REFERENCE, CLOCK)


def test_every_opus_figure_matches_and_nothing_differs(rep: fk.Reproduction) -> None:
    status = [c.status for c in rep.checks]
    assert status.count("differs") == 0
    assert status.count("match") == 19
    opus = [c for c in rep.checks if c.judge == "opus"]
    assert opus and all(c.status == "match" for c in opus)
    assert {c.set for c in opus} == {"sheet-1", "sheet-2", "pooled"}


def test_headline_figures(rep: fk.Reproduction) -> None:
    s1, s2 = rep.calibration.sets
    pooled = rep.calibration.pooled
    got = [(s.n, js_fixed((s.observed or 0) * 100, 0), js_fixed(s.kappa or 0, 2)) for s in (s1, s2, pooled)]
    assert got == [(20, "90", "0.44"), (20, "75", "0.00"), (40, "83", "0.17")]
    assert all(s.missing == 0 for s in (s1, s2, pooled))  # every graded sentence has an ok Opus verdict
    assert rep.calibration.judge_model == "claude-opus-5-5" and rep.calibration.prompt_hash == "071689f33855"


def test_sonnet_lines_are_not_reproducible_and_name_the_missing_input(rep: fk.Reproduction) -> None:
    sonnet = [c for c in rep.checks if c.judge == "sonnet"]
    assert len(sonnet) == 5 and all(c.status == "not reproducible" for c in sonnet)
    assert all(fk.SONNET_RUN in c.note and "no committed file" in c.note for c in sonnet)


def test_console_matches_kappa_ts_format(rep: fk.Reproduction) -> None:
    assert rep.console[1] == (
        "  n 20 (0 without a usable verdict)  raw agreement 90%  p_e 0.820  κ 0.44  target ≥ 0.7"
    )
    assert "  Shane s18/p2/u0  judge s18/p2/u0" in rep.console
    assert "  disagree S-23: Shane unsupported, judge supported" in rep.console
    assert rep.console[-11].startswith("pooled · opus · " + fk.OPUS_RUN)


def test_reference_transcription_is_guarded() -> None:
    """Every reference quote is verbatim in kappa-sources.md (lines copied from Footnote), and every value and
    disagreement id appears in its quote, so a typo in the transcription fails here."""
    sources = (FN / "kappa-sources.md").read_text(encoding="utf-8")
    ref = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    for check in ref["checks"]:
        assert check["quote"] in sources, check["quote"]
        for value in check.get("values", {}).values():
            assert str(value) in check["quote"], value
        for sid in check.get("disagree", []):
            assert sid in check["quote"], sid


def test_a_wrong_reference_figure_is_reported_as_a_difference(tmp_path: Path) -> None:
    ref = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    ref["checks"][0]["values"]["kappa"] = "κ 0.45"
    bad = tmp_path / "ref.yaml"
    bad.write_text(yaml.safe_dump(ref, allow_unicode=True), encoding="utf-8")
    rep = fk.reproduce(FN / "golden.json", ANSWERS, SHEETS, bad, CLOCK)
    diffs = [c for c in rep.checks if c.status == "differs"]
    assert [(c.set, c.figure, c.yardstick) for c in diffs] == [("sheet-1", "kappa", "0.44")]


def test_replayed_judge_spends_nothing_and_matches_phase2_support(rep: fk.Reproduction) -> None:
    rec = rep.run.judges[JUDGE_KEY]
    assert (rec.calls, rec.units_judged, rec.units_invalid, rec.spent_usd, rec.cap_usd) == (55, 55, 0, 0, 0)
    m = compute(rep.run)
    judge_rate = m.rate(JUDGE_KEY, "A+M+V")
    assert judge_rate is not None and (judge_rate.hits, judge_rate.total) == (49, 51)
    # Phase 2's deterministic label-rate over the same verdicts gives the same pooled count.
    plain = run_suite(
        suite_from_golden(json.loads((FN / "golden.json").read_text(encoding="utf-8"))),
        FootnoteAdapter("x", ANSWERS),
        clock=CLOCK,
    )
    support = compute(plain).rate("support", "A+M+V")
    assert support is not None and (support.hits, support.total) == (49, 51)


def test_committed_fixtures_regenerate() -> None:
    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    vf = verdicts_from_answers(answers, load_verdicts(FN / "judge" / "verdicts-opus-1646.json").source)
    assert verdict_file_json(vf) == (FN / "judge" / "verdicts-opus-1646.json").read_text(encoding="utf-8")
    assert load_calibration(FN / "judge" / "calibration-opus-1646.json").pooled.kappa == pytest.approx(1 / 6)


def test_unjudged_answers_file_is_refused() -> None:
    other = json.loads(
        (
            FN / "results" / "answers-fts-claude-haiku-5-5-theta-on-cd1252c6a407-2026-10-28T0056.json"
        ).read_text()
    )
    with pytest.raises(ValueError):
        verdicts_from_answers(other, "x")


def test_cli_footnote_kappa_and_judged_gate(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "kappa.md"
    res = runner.invoke(
        app,
        [
            "footnote", "kappa", "--golden", str(FN / "golden.json"), "--answers", str(ANSWERS),
            "--sheet", str(SHEETS[0]), "--sheet", str(SHEETS[1]), "--reference", str(REFERENCE),
            "-o", str(out),
        ],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "**19 match, 0 differ, 5 not reproducible.**" in out.read_text(encoding="utf-8")

    run_path = tmp_path / "judged.json"
    base = ["run", "-s", str(FN / "judge-suite.yaml"), "--mapping", "footnote", "--results", str(ANSWERS)]
    res = runner.invoke(app, [*base, "--no-git", "-o", str(run_path)])
    assert res.exit_code == 2 and "pass --judge" in res.output
    res = runner.invoke(
        app,
        [
            *base,
            "--no-git",
            "-o",
            str(run_path),
            "--judge",
            f"replay:{FN / 'judge' / 'verdicts-opus-1646.json'}",
        ],
    )
    assert res.exit_code == 2 and "--judge-budget-usd" in res.output
    verdicts = f"replay:{FN / 'judge' / 'verdicts-opus-1646.json'}"
    res = runner.invoke(
        app, [*base, "--no-git", "-o", str(run_path), "--judge", verdicts, "--judge-budget-usd", "0"]
    )
    assert res.exit_code == 0, res.output

    res = runner.invoke(
        app, ["gate", str(run_path), "-c", str(ROOT / "fixtures" / "gates" / "footnote-judged.yaml")]
    )
    assert res.exit_code == 1
    assert "(pass)  rate:judge[A+M+V]" in res.output and "judge kappa 0.17 (n 40) < floor 0.6" in res.output

    cal = tmp_path / "cal.json"
    res = runner.invoke(
        app,
        ["kappa", "--grades", str(FN / "grades" / "sheet-1.yaml"),
         "--grades", str(FN / "grades" / "sheet-2.yaml"),
         "--run", str(run_path), "--key", "judge", "-o", str(cal)],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "pooled: n 40 (0 without a usable verdict), raw agreement 83%, p_e 0.790, kappa 0.17" in res.output
    assert (
        load_calibration(cal).pooled == load_calibration(FN / "judge" / "calibration-opus-1646.json").pooled
    )
