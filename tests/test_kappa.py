"""Cohen's kappa (Footnote's four cases, plus properties), grade sets and calibration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from yardstick.grades import Grade, GradeSet, footnote_grade_set, load_grade_set, parse_footnote_sheet
from yardstick.judge.base import JudgeIdentity
from yardstick.kappa import calibrate, cohen_kappa, fmt_stat, js_fixed

ROOT = Path(__file__).resolve().parent.parent
FN = ROOT / "fixtures" / "footnote"
ANSWERS_1646 = FN / "results" / "answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json"
YN = ["yes", "no"]
L3 = ["supported", "partial", "unsupported"]
ID = JudgeIdentity(model="m", prompt_hash="h", source="test")


def test_textbook_2x2() -> None:
    a = ["yes"] * 25 + ["no"] * 25
    b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    r = cohen_kappa(a, b, YN)
    assert r.n == 50
    assert r.observed == pytest.approx(0.7, abs=1e-12)
    assert r.expected == pytest.approx(0.5, abs=1e-12)
    assert r.kappa == pytest.approx(0.4, abs=1e-12)


def test_perfect_and_chance() -> None:
    a = ["supported", "partial", "unsupported", "supported"]
    assert cohen_kappa(a, a, L3).kappa == 1
    assert cohen_kappa(["yes", "yes", "no", "no"], ["yes", "no", "yes", "no"], YN).kappa == pytest.approx(0)


def test_one_label_is_null_not_zero_or_one() -> None:
    r = cohen_kappa(["yes"] * 5, ["yes"] * 5, YN)
    assert (r.kappa, r.observed, r.expected, r.n) == (None, 1, 1, 5)


def test_errors() -> None:
    with pytest.raises(ValueError, match="1 vs 2"):
        cohen_kappa(["yes"], ["yes", "no"], YN)
    with pytest.raises(ValueError, match="no ratings"):
        cohen_kappa([], [], YN)
    with pytest.raises(ValueError, match="maybe"):
        cohen_kappa(["yes", "maybe"], ["yes", "no"], YN)


pairs = st.lists(st.tuples(st.sampled_from(L3), st.sampled_from(L3)), min_size=1, max_size=60)


@given(pairs)
def test_kappa_properties(ps: list[tuple[str, str]]) -> None:
    a, b = [p[0] for p in ps], [p[1] for p in ps]
    r = cohen_kappa(a, b, L3)
    swapped = cohen_kappa(b, a, L3)
    assert r.observed == swapped.observed and r.expected == pytest.approx(swapped.expected)
    if r.kappa is None:
        assert swapped.kappa is None and r.expected == pytest.approx(1)
    else:
        assert swapped.kappa is not None
        assert r.kappa == pytest.approx(swapped.kappa)
        assert r.kappa <= 1 + 1e-12
    if r.observed == 1:
        assert r.kappa is None or r.kappa == pytest.approx(1)


def test_js_fixed_matches_javascript_tofixed() -> None:
    # Values checked against node's Number.prototype.toFixed.
    assert js_fixed(0.825 * 100, 0) == "83"  # 82.5 exactly in binary: tie goes up, Python's round() says 82
    assert js_fixed(0.4444444444444447, 2) == "0.44"
    assert js_fixed(0.16666666666666677, 2) == "0.17"
    assert js_fixed(0.82, 3) == "0.820"
    assert js_fixed(-0.0666, 2) == "-0.07"
    assert js_fixed(0.0, 2) == "0.00"


def _gs(name: str, grades: dict[str, str]) -> GradeSet:
    return GradeSet(
        name=name,
        grader="g",
        source="t",
        labels=L3,
        grades=[Grade(key=k, label=v, ref=f"R{i}") for i, (k, v) in enumerate(grades.items())],
    )


def test_calibrate_per_set_pooled_and_missing() -> None:
    s1 = _gs("one", {"a:0": "supported", "a:1": "partial", "b:0": "supported"})
    s2 = _gs("two", {"c:0": "unsupported", "d:0": "supported"})
    verdicts = {"a:0": "supported", "a:1": "supported", "b:0": "supported", "c:0": "unsupported", "d:0": None}
    cal = calibrate([s1, s2], verdicts, ID)
    one, two = cal.sets
    assert (one.n, one.missing, two.n, two.missing) == (3, 0, 1, 1)  # d:0 has no valid label
    assert [d.ref for d in one.disagreements] == ["R1"]
    assert cal.pooled.n == 4 and cal.pooled.missing == 1
    assert cal.pooled.human_counts == {"supported": 2, "partial": 1, "unsupported": 1}
    assert cal.pooled.judge_counts == {"supported": 3, "partial": 0, "unsupported": 1}
    # pooled: p_o = 3/4, p_e = (2*3 + 1*0 + 1*1) / 16 = 7/16, kappa = (12/16 - 7/16) / (9/16) = 5/9
    assert cal.pooled.kappa == pytest.approx(5 / 9)
    assert two.kappa is None  # one pair, both raters on the same single label: p_e = 1
    assert "kappa undefined" in fmt_stat(two)
    assert cal.matches("m", "h") and not cal.matches("m", "other")


def test_calibrate_with_no_pairs_reports_zero_n() -> None:
    cal = calibrate([_gs("one", {"a:0": "supported"})], {}, ID)
    assert cal.pooled.n == 0 and cal.pooled.kappa is None and cal.pooled.missing == 1
    assert "kappa not computed" in fmt_stat(cal.pooled)


def test_calibrate_rejects_mismatched_labels_and_duplicate_names() -> None:
    other = GradeSet(name="x", grader="g", source="t", labels=YN, grades=[Grade(key="a:0", label="yes")])
    with pytest.raises(ValueError, match="disagree on labels"):
        calibrate([_gs("one", {"a:0": "supported"}), other], {}, ID)
    with pytest.raises(ValueError, match="unique"):
        calibrate([_gs("one", {"a:0": "supported"}), _gs("one", {"b:0": "supported"})], {}, ID)


def test_grade_set_validation() -> None:
    with pytest.raises(ValidationError, match="not '<item id>:<unit index>'"):
        Grade(key="nokey", label="supported")
    with pytest.raises(ValidationError, match="duplicate keys"):
        GradeSet(
            name="x",
            grader="g",
            source="t",
            labels=L3,
            grades=[Grade(key="a:0", label="supported"), Grade(key="a:0", label="partial")],
        )
    with pytest.raises(ValidationError, match="labels not in"):
        GradeSet(name="x", grader="g", source="t", labels=L3, grades=[Grade(key="a:0", label="maybe")])
    with pytest.raises(ValidationError, match="no grades"):
        GradeSet(name="x", grader="g", source="t", labels=L3, grades=[])


def test_footnote_sheets_parse_like_parse_grade_sheet() -> None:
    s1 = parse_footnote_sheet((FN / "grades" / "grades.md").read_text(encoding="utf-8"))
    s2 = parse_footnote_sheet((FN / "grades" / "grades-2.md").read_text(encoding="utf-8"))
    # kappa.ts requires exactly 20 per sheet, every one graded with one of the three labels.
    assert len(s1) == 20 and len(s2) == 20
    assert [x[0] for x in s1] == [f"S-{n:02d}" for n in range(1, 21)]
    assert [x[0] for x in s2] == [f"S-{n:02d}" for n in range(21, 41)]
    assert all(x[3] in L3 for x in s1 + s2)
    assert s1[0][1:4] == ("486277fc-13bc-4fb8-b708-932293c6b692", 1, "partial")
    assert s1[0][4].startswith("Claude draft, Shane approved")


def test_footnote_grade_set_maps_answer_ids_to_golden_ids() -> None:
    answers = json.loads(ANSWERS_1646.read_text(encoding="utf-8"))
    gs = footnote_grade_set(
        (FN / "grades" / "grades.md").read_text(encoding="utf-8"), answers, name="s", source="t"
    )
    assert gs.grades[0].key == "GA-03:1" and gs.grades[0].ref == "S-01"  # the sheet's "GA-03 sentence 2"
    assert gs == load_grade_set(FN / "grades" / "sheet-1.yaml").model_copy(
        update={"source": "t", "name": "s"}
    )


def test_footnote_grade_set_refuses_blank_or_unknown() -> None:
    answers = json.loads(ANSWERS_1646.read_text(encoding="utf-8"))
    text = (FN / "grades" / "grades.md").read_text(encoding="utf-8")
    blank = text.replace("grade: partial — Claude draft, Shane approved: 'not limited'", "grade: ", 1)
    with pytest.raises(ValueError, match="S-01: not graded"):
        footnote_grade_set(blank, answers, name="s", source="t")
    with pytest.raises(ValueError, match="not in the answers file"):
        footnote_grade_set(text, {"rows": []}, name="s", source="t")
