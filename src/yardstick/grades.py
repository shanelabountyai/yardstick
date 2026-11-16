"""Human grades (PRD §4 "Judge calibration", Phase 3): one label per judged unit, keyed like the judge
(D-35, D-38).

A grade set file (YAML or JSON)::

    name: sheet-1
    grader: Shane
    source: where the grades came from
    labels: [supported, partial, unsupported]
    grades:
      - {key: "GA-03:1", label: partial, ref: S-01, note: "..."}

``key`` is ``<item id>:<unit index>``, the same key an ``llm-judge`` scorer gives a unit, so grades join a
run's judge labels with no other mapping. ``ref`` is the grader's own id for the unit (e.g. a sheet's
``S-01``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from yardstick.judge.base import unit_key

_KEY = re.compile(r"^.+:\d+$")


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    ref: str = ""
    note: str = ""

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not _KEY.match(v):
            raise ValueError(f"grade key {v!r} is not '<item id>:<unit index>'")
        return v


class GradeSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    grader: str
    source: str
    labels: list[str]
    grades: list[Grade]

    @model_validator(mode="after")
    def _check(self) -> GradeSet:
        if not self.labels or len(set(self.labels)) != len(self.labels):
            raise ValueError("labels must be a non-empty list of distinct labels")
        if not self.grades:
            raise ValueError(f"grade set {self.name!r} has no grades")
        keys = [g.key for g in self.grades]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        if dupes:
            raise ValueError(f"grade set {self.name!r}: duplicate keys {dupes}")
        bad = sorted({g.label for g in self.grades if g.label not in self.labels})
        if bad:
            raise ValueError(f"grade set {self.name!r}: labels not in {self.labels}: {bad}")
        return self


def load_grade_set(path: Path) -> GradeSet:
    text = path.read_text(encoding="utf-8")
    data: Any = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    return GradeSet.model_validate(data)


def grade_set_yaml(gs: GradeSet, header: str = "") -> str:
    body = yaml.safe_dump(gs.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100)
    return header + body


# --------------------------------------------------------------------------- Footnote grade sheets

#: Footnote's ``parseGradeSheet`` regex (``src/lib/eval/kappa.ts``), plus the rest of the grade line (a note).
_SHEET = re.compile(
    r"## (S-\d+)[^\n]*\n\n<!-- key ([0-9a-f-]{36}):(\d+) -->[\s\S]*?\ngrade: (\w*)([^\n]*)",
)
FOOTNOTE_LABELS = ("supported", "partial", "unsupported")


def parse_footnote_sheet(text: str) -> list[tuple[str, str, int, str, str]]:
    """``(sid, answerId, sentence index, grade, note)`` for each graded sentence, in sheet order."""
    out = []
    for m in _SHEET.finditer(text):
        note = m.group(5).strip().lstrip("—-").strip()
        out.append((m.group(1), m.group(2), int(m.group(3)), m.group(4), note))
    return out


def footnote_grade_set(
    sheet_text: str, answers: Mapping[str, Any], *, name: str, source: str, grader: str = "Shane"
) -> GradeSet:
    """A Footnote grade sheet as a grade set, its ``answerId:idx`` keys translated to ``<golden id>:<idx>``
    through the answers file the sheet was drawn from. A blank grade or an unknown answer id is an error."""
    rows = answers.get("rows")
    if not isinstance(rows, list):
        raise ValueError("answers file has no 'rows' list")
    by_answer = {r["answerId"]: r["id"] for r in rows if isinstance(r, dict) and "answerId" in r}
    parsed = parse_footnote_sheet(sheet_text)
    if not parsed:
        raise ValueError("no graded sentences found in the sheet")
    grades = []
    for sid, answer_id, idx, label, note in parsed:
        if not label:
            raise ValueError(f"{sid}: not graded")
        if answer_id not in by_answer:
            raise ValueError(f"{sid}: answer {answer_id} is not in the answers file")
        grades.append(Grade(key=unit_key(by_answer[answer_id], idx), label=label, ref=sid, note=note))
    return GradeSet(name=name, grader=grader, source=source, labels=list(FOOTNOTE_LABELS), grades=grades)


def labels_of(sets: Sequence[GradeSet]) -> list[str]:
    """The shared label set of several grade sets (they must agree)."""
    first = sets[0].labels
    for gs in sets[1:]:
        if gs.labels != first:
            raise ValueError(f"grade sets disagree on labels: {first} vs {gs.labels}")
    return list(first)
