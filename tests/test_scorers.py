from __future__ import annotations

from typing import Any

import pytest

from yardstick.models import Output
from yardstick.scorers import ScorerConfigError, get_scorer, scorer_names
from yardstick.scorers.base import Outcome


def s(name: str, expected: Any, text: str = "", options: dict[str, Any] | None = None, **out: Any) -> Outcome:
    return get_scorer(name)(expected, Output(text=text, **out), options or {})


def test_registry_has_all_phase1_scorers() -> None:
    assert scorer_names() == sorted(
        [
            "exact",
            "regex",
            "json-schema",
            "numeric-tolerance",
            "contains-all",
            "refusal-expected",
            "citation-grounded",
        ]
    )
    with pytest.raises(ScorerConfigError):
        get_scorer("llm-judge")


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
