from __future__ import annotations

from typing import Any

import pytest

from yardstick.models import Output
from yardstick.scorers import ScorerConfigError, get_scorer, scorer_names
from yardstick.scorers.base import Outcome
from yardstick.scorers.numeric import first_number


def s(name: str, expected: Any, text: str = "", options: dict[str, Any] | None = None, **out: Any) -> Outcome:
    return get_scorer(name)(expected, Output(text=text, **out), options or {})


def test_registry_has_all_phase1_scorers() -> None:
    # Phase 1 scorers, the two Phase 2 field scorers (field-equals, label-rate) and Phase 3's llm-judge.
    # Still an exact list (D-33).
    assert scorer_names() == sorted(
        [
            "exact",
            "regex",
            "json-schema",
            "numeric-tolerance",
            "contains-all",
            "refusal-expected",
            "citation-grounded",
            "field-equals",
            "label-rate",
            "llm-judge",
        ]
    )
    with pytest.raises(ScorerConfigError):
        get_scorer("no-such-scorer")
    # llm-judge is registered, but scoring needs a judge session; called directly it refuses (D-34).
    with pytest.raises(ScorerConfigError, match="needs a judge"):
        get_scorer("llm-judge")(1.0, Output(text="x"), {})


def test_exact() -> None:
    assert s("exact", "Paris", "Paris").passed
    assert not s("exact", "Paris", " paris ").passed
    assert s("exact", "Paris", "  PARIS ", {"normalize": True}).passed
    with pytest.raises(ScorerConfigError):
        s("exact", 3, "3")
    with pytest.raises(ScorerConfigError):
        s("exact", "a", "a", {"bogus": 1})


def test_regex() -> None:
    assert s("regex", r"\d{3}", "abc 123").passed
    assert not s("regex", r"\d{3}", "abc 123", {"fullmatch": True}).passed
    assert s("regex", "hello", "HELLO", {"ignore_case": True}).passed
    with pytest.raises(ScorerConfigError):
        s("regex", "(", "x")


SCHEMA = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}


def test_json_schema() -> None:
    assert s("json-schema", SCHEMA, '{"a": 1}').passed
    bad = s("json-schema", SCHEMA, '{"a": "x"}')
    assert not bad.passed and "a" in bad.detail
    assert "not JSON" in s("json-schema", SCHEMA, "nope").detail
    with pytest.raises(ScorerConfigError):
        s("json-schema", {"type": 12}, "{}")


def test_numeric_tolerance() -> None:
    assert s("numeric-tolerance", 10, "total is 10.0").passed
    assert not s("numeric-tolerance", 10, "total is 10.5").passed
    assert s("numeric-tolerance", 10, "total is 10.5", {"abs_tol": 0.5}).passed
    assert s("numeric-tolerance", 100, "101", {"rel_tol": 0.02}).passed
    assert s("numeric-tolerance", 1250, "1,250.00 USD").passed
    assert s("numeric-tolerance", 3.5, '{"total": 3.5, "n": 9}', {"field": "total"}).passed
    assert not s("numeric-tolerance", 3.5, '{"n": 3.5}', {"field": "total"}).passed
    assert not s("numeric-tolerance", 1, "none here").passed
    with pytest.raises(ScorerConfigError):
        s("numeric-tolerance", True, "1")
    with pytest.raises(ScorerConfigError):
        s("numeric-tolerance", 1, "1", {"abs_tol": -1})


@pytest.mark.parametrize(
    ("text", "want"),
    [
        # A hyphen inside an identifier is not a minus sign, and the identifier is not a number.
        ("INV-2026", None),
        ("Invoice INV-2026: total 150", 150.0),
        ("INV2026 total 150", 150.0),
        # Dates are skipped, not read as their first part.
        ("2026-11-14", None),
        ("Paid on 2026-11-14: 42", 42.0),
        ("Paid on 11/14/2026: 42", 42.0),
        ("Paid on 14.11.2026: 42", 42.0),
        # A leading decimal point is kept.
        (".5", 0.5),
        ("ratio .5", 0.5),
        ("-.5", -0.5),
        # Existing behaviour is unchanged.
        ("total is -3", -3.0),
        ("(-4)", -4.0),
        ("x=-3", -3.0),
        ("1,250.00 USD", 1250.0),
        ("$12", 12.0),
        ("10kg", 10.0),
        ("1e-3", 0.001),
        ("is 5.", 5.0),
        ("none here", None),
    ],
)
def test_first_number_free_text(text: str, want: float | None) -> None:
    assert first_number(text) == want


def test_numeric_tolerance_free_text_review_cases() -> None:
    assert not s("numeric-tolerance", -2026, "INV-2026").passed
    assert s("numeric-tolerance", 150, "Invoice INV-2026: total 150").passed
    assert s("numeric-tolerance", 42, "Paid on 2026-11-14: 42").passed
    assert not s("numeric-tolerance", 2026, "Paid on 2026-11-14: 42").passed
    assert s("numeric-tolerance", 0.5, ".5").passed
    assert not s("numeric-tolerance", 5, ".5").passed
    # The same parser reads a string under `field`.
    assert s("numeric-tolerance", 0.5, '{"r": "ratio .5"}', {"field": "r"}).passed


def test_contains_all_partial_score() -> None:
    o = s("contains-all", ["alpha", "beta", "gamma", "delta"], "Alpha and BETA")
    assert not o.passed and o.score == 0.5
    assert s("contains-all", ["Alpha"], "alpha").passed
    assert not s("contains-all", ["Alpha"], "alpha", {"case_sensitive": True}).passed
    with pytest.raises(ScorerConfigError):
        s("contains-all", [], "x")


def test_refusal_markers_and_flag() -> None:
    assert s("refusal-expected", True, "I can’t help with that.").passed
    assert s("refusal-expected", False, "Sure, here you go.").passed
    assert not s("refusal-expected", True, "Sure, here you go.").passed
    # The explicit flag wins over the text.
    assert s("refusal-expected", True, "Sure, here you go.", refused=True).passed
    assert not s("refusal-expected", False, "I can't help with that.", refused=True).passed
    assert s("refusal-expected", True, "Nope.", {"markers": ["nope"]}).passed
    with pytest.raises(ScorerConfigError):
        s("refusal-expected", "yes", "x")


SOURCES = {"sources": {"kb-1": "The reset link expires after 30 minutes.", "kb-2": "Exports are CSV."}}


def test_citation_grounded() -> None:
    assert s("citation-grounded", SOURCES, 'Yes [[kb-1: "reset link EXPIRES after 30 minutes"]]').passed
    half = s("citation-grounded", SOURCES, '[[kb-1: "expires after 30 minutes"]] [[kb-2: "are XML"]]')
    assert not half.passed and half.score == 0.5
    unknown = s("citation-grounded", SOURCES, '[[kb-9: "anything"]]')
    assert not unknown.passed and "unknown source" in unknown.detail
    assert not s("citation-grounded", SOURCES, "no citations at all").passed
    assert s("citation-grounded", SOURCES, "none", {"min_citations": 0}).passed
    with pytest.raises(ScorerConfigError):
        s("citation-grounded", {"sources": "x"}, "y")


@pytest.mark.parametrize("quote", ["", " ", "   \t ", "\n", "e", " . ", "T"])
def test_citation_grounded_rejects_empty_whitespace_and_one_char_quotes(quote: str) -> None:
    # Each of these is a substring of the normalized source text, so a plain `in` check would ground it.
    out = s("citation-grounded", SOURCES, f'[[kb-1: "{quote}"]]')
    assert not out.passed and out.score == 0.0
    assert "kb-1: quote too short" in out.detail


def test_citation_grounded_short_quote_does_not_hide_behind_a_good_one() -> None:
    out = s("citation-grounded", SOURCES, '[[kb-1: "expires after 30 minutes"]] [[kb-2: ""]]')
    assert not out.passed and out.score == 0.5
    assert out.detail == "kb-2: quote too short"
    # Two characters is the floor (D-20) and still has to be found in the source.
    assert s("citation-grounded", SOURCES, '[[kb-2: "CS"]]').passed
    assert not s("citation-grounded", SOURCES, '[[kb-2: "zz"]]').passed
