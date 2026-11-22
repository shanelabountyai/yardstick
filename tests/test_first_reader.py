"""PRD-F: the report says why first, carries a Key, and the Footnote evidence files read cleanly
(review items 8, 10, 11; decision 5 (b))."""

from __future__ import annotations

import json
import re
from collections import Counter

from tests.helpers import ROOT
from yardstick.adapters.footnote import suite_from_golden
from yardstick.models import Descriptions

EX = ROOT / "examples" / "footnote"


def _before_summary(text: str, marker: str) -> str:
    return text.split(marker, 1)[0]


def test_failing_rules_and_cross_target_note_come_before_summary() -> None:
    md = _before_summary((EX / "report.md").read_text(encoding="utf-8"), "## Summary")
    assert "- `rate:refusal[A+M]`: 86.4% (floor 90.0%)" in md
    assert "Compared against a different target: `footnote-hybrid-sonnet-theta-on`" in md
    html = _before_summary((EX / "report.html").read_text(encoding="utf-8"), "<h2>Summary</h2>")
    assert "<code>rate:refusal[A+M]</code>: 86.4% (floor 90.0%)" in html
    assert "Compared against a different target" in html


def test_key_explains_refusal_and_every_slice() -> None:
    md = (EX / "report.md").read_text(encoding="utf-8")
    key = md.split("## Key", 1)[1].split("## Run", 1)[0]
    assert "`refusal`: hit = the expected outcome" in key and "not a refusal rate" in key
    for s in ("A", "A+M", "A+M+V", "M", "P", "U", "V"):
        assert f"- `{s}`:" in key


def test_descriptions_do_not_move_the_suite_hash() -> None:
    golden = json.loads((ROOT / "fixtures" / "footnote" / "golden.json").read_text(encoding="utf-8"))
    suite = suite_from_golden(golden)
    plain = suite.model_copy(update={"descriptions": None})
    other = suite.model_copy(update={"descriptions": Descriptions(scorers={"refusal": "x"})})
    assert suite.content_hash == plain.content_hash == other.content_hash


def test_markdown_rates_by_slice_is_collapsed() -> None:
    md = (EX / "report.md").read_text(encoding="utf-8")
    assert re.search(r"<details><summary>Rates by slice \(\d+ rows\)</summary>", md)


def test_kappa_md_has_no_duplicate_rows_and_the_same_headline() -> None:
    md = (EX / "kappa.md").read_text(encoding="utf-8")
    assert "**19 match, 0 differ, 5 not reproducible.**" in md
    rows = [line for line in md.splitlines() if re.match(r"\| Q\d", line)]
    assert len(rows) == 24 and not [r for r, n in Counter(rows).items() if n > 1]
    assert md.count("they live only in Footnote's database") == 1


def test_reproduction_md_defines_each_reason_once() -> None:
    md = (EX / "reproduction.md").read_text(encoding="utf-8")
    assert "**74 match, 0 differ, 49 not reproducible**" in md
    assert md.count("citations are not in the answers files") == 2  # two distinct reasons start this way
    assert len(re.findall(r"not reproducible \[\d+\]", md)) == 49
    assert "## Why not reproducible" in md
