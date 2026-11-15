"""Phase 2 gate (PRD §8): Footnote runs reproduce the numbers its own scorecard reports, and every number
that is not reproduced is listed with its reason."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from typer.testing import CliRunner

from tests.helpers import CLOCK, ROOT
from yardstick.cli import app
from yardstick.footnote_scorecard import Check, frac, parse_tables, render, reproduce

FN = ROOT / "fixtures" / "footnote"
AXIS = chr(0x3B8) + chr(0x2032) + " axis"
SCORECARD = FN / "results" / "scorecard-cd1252c6a407-2026-10-28.md"


def _checks() -> list[Check]:
    return reproduce(FN / "results", FN / "golden.json", SCORECARD, CLOCK)


def test_every_reproducible_number_matches() -> None:
    checks = _checks()
    differs = [c for c in checks if c.status == "differs"]
    assert differs == []
    matched = Counter(c.metric for c in checks if c.status == "match")
    # 6 cells x 6 per-cell numbers, 2 sentence-support numbers, 3 theta' cells x 4 values x 3 numbers.
    assert matched == {
        "Answered or partial (A, M)": 6,
        "Refused before the model, by cause (A, M)": 6,
        "Refusal on unanswerable (U)": 6,
        "Refused before any model call (U)": 6,
        "Outcome as expected (P)": 6,
        "Split (all)": 6,
        "Sentence support (judge), A, M, V": 1,
        "Sentence support: schema_invalid verdicts": 1,
        "U refused": 12,
        "U pre-call": 12,
        "A, M answered or partial": 12,
    }


def test_not_reproducible_list_is_exactly_the_expected_one() -> None:
    """Nothing drops out silently: every scorecard number is either matched or listed here with a reason."""
    nr = Counter(c.metric for c in _checks() if c.status == "not reproducible")
    assert nr == {
        "Citation verbatim": 6,
        "Expected passage cited (A, M)": 6,
        "Refused schema_invalid / by model (A, M)": 6,
        "Edition labeled (V answered)": 6,
        "Split: schema_invalid answer calls": 6,
        "V edition stated by judge": 1,
        "Tier leaks": 1,
        "Planted fabrication caught": 1,
        "Judge-vs-human κ (Opus, pooled sheets)": 1,
        "Injection fixtures passed": 1,
        "Build spend": 1,
        "A, M expected cited": 12,
        "recall@k / MRR table": 1,
    }
    assert all(c.note for c in _checks() if c.status == "not reproducible")


def test_every_scorecard_cell_and_theta_row_is_covered() -> None:
    tables = parse_tables(SCORECARD.read_text(encoding="utf-8"))
    per_cell = next(v for k, v in tables.items() if k.startswith("Per cell"))
    cells = per_cell[0][3:]
    covered = {c.cell for c in _checks() if c.section == "Per cell"}
    assert set(cells) == covered and len(cells) == 6
    axis = next(v for k, v in tables.items() if k.startswith(AXIS))
    axis_cells = {f"{r[0]} @ {r[1]}" for r in axis[1:]}
    assert axis_cells == {c.cell for c in _checks() if c.section == AXIS}


def test_a_changed_number_is_reported_as_differs(tmp_path: Path) -> None:
    text = SCORECARD.read_text(encoding="utf-8").replace("| 16/22 (73%); refused", "| 15/22 (68%); refused")
    bad = tmp_path / "scorecard.md"
    bad.write_text(text, encoding="utf-8")
    differs = [c for c in reproduce(FN / "results", FN / "golden.json", bad, CLOCK) if c.status == "differs"]
    assert [(c.metric, c.cell, c.scorecard, c.yardstick) for c in differs] == [
        ("Answered or partial (A, M)", "dense+haiku θ off", "15/22 (68%)", "16/22 (73%)")
    ]
    res = CliRunner().invoke(
        app,
        [
            "footnote",
            "reproduce",
            "--results-dir",
            str(FN / "results"),
            "--golden",
            str(FN / "golden.json"),
            "--scorecard",
            str(bad),
            "-o",
            str(tmp_path / "r.md"),
        ],
    )
    assert res.exit_code == 1


def test_frac_rounds_half_up_like_math_round() -> None:
    assert frac(7, 8) == "7/8 (88%)"  # 87.5 -> 88
    assert frac(1, 8) == "1/8 (13%)"  # 12.5 -> 13 (Python's round would give 12)
    assert frac(0, 0) == "n 0"


def test_committed_reproduction_report_is_current(tmp_path: Path) -> None:
    out = tmp_path / "r.md"
    res = CliRunner().invoke(
        app,
        [
            "footnote",
            "reproduce",
            "--results-dir",
            str(FN / "results"),
            "--golden",
            str(FN / "golden.json"),
            "--scorecard",
            str(SCORECARD),
            "-o",
            str(out),
            "--source",
            "shanelabountyai/footnote @ 3c9b0c7 (eval/results, eval/golden.json)",
        ],
    )
    assert res.exit_code == 0, res.output
    assert out.read_text(encoding="utf-8") == (ROOT / "examples" / "footnote" / "reproduction.md").read_text(
        encoding="utf-8"
    )
    assert render(_checks(), source="x") == render(_checks(), source="x")
