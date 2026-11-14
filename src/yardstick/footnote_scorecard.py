"""Phase 2 gate: Footnote's committed answers files, run through Yardstick, against Footnote's scorecard.

For every number the scorecard prints that can be derived from ``answers-*.json`` rows, Yardstick computes it
from its own runs (metrics and item results, not the raw file) and formats it the way Footnote's
``scorecard.ts`` does; the scorecard's own string is parsed out of the committed markdown. Each check is
"match", "differs" or "not reproducible" with the reason (the scorecard reads database rows and other result
files for those).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from yardstick import metrics as metrics_mod
from yardstick.adapters.footnote import FootnoteAdapter, suite_from_golden
from yardstick.clock import Clock
from yardstick.models import ItemResult, MetricSet, Run, Suite
from yardstick.runner import run_suite

Status = Literal["match", "differs", "not reproducible"]

THETA_AXIS: tuple[float | None, ...] = (None, 0.52, 0.559, 0.58)  # Footnote's THETA_AXIS (D-29 there)
ORDER = ("fts", "dense", "hybrid")

NO_CITATIONS = "citations are not in the answers files (the scorecard re-reads stored Answer rows)"
NO_CAUSE = "schema_invalid vs model refusals come from ModelCall rows, not in the answers files"


@dataclass(frozen=True)
class Check:
    section: str
    metric: str
    cell: str
    scorecard: str
    yardstick: str
    status: Status
    note: str = ""


@dataclass(frozen=True)
class Cell:
    path: Path
    retriever: str
    model: str
    judge: str | None
    theta: str

    @property
    def name(self) -> str:
        """Footnote's ``cellName``: ``dense+haiku θ off``."""
        model = re.sub(r"-\d+-\d+$", "", self.model.replace("claude-", ""))
        return f"{self.retriever}+{model} \u03b8 {self.theta}"

    @property
    def target_name(self) -> str:
        return f"footnote-{self.retriever}-{self.model}-theta-{self.theta}"


def load_cells(results_dir: Path) -> list[Cell]:
    """The answers files, fts -> dense -> hybrid, then by model (Footnote's ``loadCells`` order)."""
    cells = []
    for p in sorted(results_dir.glob("answers-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        cells.append(
            Cell(path=p, retriever=d["retriever"], model=d["model"], judge=d.get("judge"), theta=d["theta"])
        )
    return sorted(cells, key=lambda c: (ORDER.index(c.retriever), c.model))


def run_cell(suite: Suite, cell: Cell, clock: Clock, theta_prime: float | None = None) -> Run:
    name = cell.target_name if theta_prime is None else f"{cell.target_name}-at-{theta_prime:g}"
    return run_suite(suite, FootnoteAdapter(name, cell.path, theta_prime), clock=clock)


# --------------------------------------------------------------------------- formatting like scorecard.ts


def frac(k: int, n: int) -> str:
    """``k/n (p%)`` with JS ``Math.round`` (half up), as in Footnote's ``frac``."""
    if not n:
        return "n 0"
    pct = (200 * k + n) // (2 * n)
    return f"{k}/{n} ({pct}%)"


def ids(xs: Sequence[str]) -> str:
    return f" \u2014 {', '.join(xs)}" if xs else ""


def _field(r: ItemResult, name: str) -> Any:
    return r.output.fields.get(name)


def _in(run: Run, slice_name: str) -> list[ItemResult]:
    return [r for r in run.items if slice_name in r.slices]


def _score(r: ItemResult, key: str) -> bool | None:
    for s in r.scores:
        if s.key == key:
            return s.passed
    return None


def _rate_frac(m: MetricSet, key: str, slice_name: str) -> str:
    rm = m.rate(key, slice_name)
    return frac(rm.hits, rm.total) if rm else "n 0"


def answered_am(m: MetricSet) -> str:
    return _rate_frac(m, "refusal", "A+M")


def pre_call_am(m: MetricSet) -> str:
    rm = m.rate("pre-call", "A+M")
    return f"pre-call {rm.hits if rm else 0}"


def u_refusal(run: Run, m: MetricSet) -> str:
    u = _in(run, "U")
    sm = m.slices.get("U")
    passed = sum(1 for r in u if r.passed)
    false_answers = [r.item_id for r in u if not r.passed]
    mismatch = [
        f"{r.item_id} {_field(r, 'refusal_code')}"
        for r in u
        if r.passed and _score(r, "refusal-code") is False
    ]
    assert sm is None or sm.n_items == len(u)
    return (
        f"{frac(passed, len(u))}; false answers{ids(false_answers) or ' none'}; "
        f"code mismatch{ids(mismatch) or ' none'}"
    )


def u_pre_call(m: MetricSet) -> str:
    return _rate_frac(m, "pre-call", "U")


def p_outcome(run: Run) -> str:
    p = _in(run, "P")
    misses = []
    for r in p:
        if r.passed:
            continue
        status = _field(r, "status")
        if status == "refused":
            cause = "pre-call" if _field(r, "pre_call") else "model or schema_invalid"
            misses.append(f"{r.item_id} refused ({cause})")
        else:
            misses.append(f"{r.item_id} {status}")
    return f"{frac(len(p) - len(misses), len(p))}{ids(misses)}"


def split(run: Run) -> str:
    counts = {
        s: sum(1 for r in run.items if _field(r, "status") == s) for s in ("answered", "partial", "refused")
    }
    return " / ".join(f"{s} {n}" for s, n in counts.items()) + f" of {len(run.items)}"


def v_answered(run: Run) -> int:
    return sum(1 for r in _in(run, "V") if _field(r, "status") != "refused")


def support(run: Run, m: MetricSet) -> tuple[str, str]:
    rm = m.rate("support", "A+M+V")
    excluded = sum(
        1 for r in _in(run, "A+M+V") for v in (_field(r, "verdicts") or []) if v == "schema_invalid"
    )
    return (frac(rm.hits, rm.total) if rm else "n 0"), f"schema_invalid {excluded}"


# --------------------------------------------------------------------------- scorecard parsing


def parse_tables(md: str) -> dict[str, list[list[str]]]:
    """``## heading`` -> table rows (header first, separator dropped), cells stripped."""
    tables: dict[str, list[list[str]]] = {}
    heading = ""
    for line in md.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            continue
        if line.startswith("|") and heading:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue
            tables.setdefault(heading, []).append(cells)
    return tables


def _section(tables: dict[str, list[list[str]]], prefix: str) -> list[list[str]]:
    for k, v in tables.items():
        if k.startswith(prefix):
            return v
    raise KeyError(f"scorecard has no section starting {prefix!r}")


def _cmp(section: str, metric: str, cell: str, sc: str, ys: str, note: str = "") -> Check:
    return Check(section, metric, cell, sc, ys, "match" if sc == ys else "differs", note)


def _nr(section: str, metric: str, cell: str, sc: str, note: str, ys: str = "\u2014") -> Check:
    return Check(section, metric, cell, sc, ys, "not reproducible", note)


_FRAC = re.compile(r"^(\d+/\d+ \(\d+%\)|n 0)")


def _head(text: str) -> str:
    m = _FRAC.match(text)
    return m.group(1) if m else text


# --------------------------------------------------------------------------- the reproduction


def reproduce(results_dir: Path, golden: Path, scorecard: Path, clock: Clock) -> list[Check]:
    suite = suite_from_golden(json.loads(golden.read_text(encoding="utf-8")))
    tables = parse_tables(scorecard.read_text(encoding="utf-8"))
    cells = load_cells(results_dir)
    runs = {c.name: run_cell(suite, c, clock) for c in cells}
    mets = {name: metrics_mod.compute(r) for name, r in runs.items()}
    checks: list[Check] = []

    # Per cell -------------------------------------------------------------------------------------------
    per_cell = _section(tables, "Per cell")
    header = per_cell[0]
    col = {name: i for i, name in enumerate(header)}
    missing = [c.name for c in cells if c.name not in col]
    if missing:
        raise KeyError(f"scorecard has no column for {missing}")
    rows = {r[0]: r for r in per_cell[1:]}
    sec = "Per cell"
    for c in cells:
        run, m, i = runs[c.name], mets[c.name], col[c.name]

        def sc(label: str, i: int = i) -> str:
            return rows[label][i]

        checks.append(_nr(sec, "Citation verbatim", c.name, sc("Citation verbatim"), NO_CITATIONS))
        exp = "Expected passage cited (doc + page \u00b1 tol)"
        checks.append(_nr(sec, "Expected passage cited (A, M)", c.name, sc(exp), NO_CITATIONS))
        ans = sc("Answered or partial")
        checks.append(_cmp(sec, "Answered or partial (A, M)", c.name, _head(ans), answered_am(m)))
        pre = re.search(r"pre-call \d+", ans)
        checks.append(
            _cmp(
                sec,
                "Refused before the model, by cause (A, M)",
                c.name,
                pre.group(0) if pre else ans,
                pre_call_am(m),
            )
        )
        cause = re.search(r"schema_invalid \d+, model \d+", ans)
        checks.append(
            _nr(
                sec,
                "Refused schema_invalid / by model (A, M)",
                c.name,
                cause.group(0) if cause else ans,
                NO_CAUSE,
            )
        )
        checks.append(
            _cmp(sec, "Refusal on unanswerable (U)", c.name, sc("Refusal on unanswerable"), u_refusal(run, m))
        )
        checks.append(
            _cmp(
                sec,
                "Refused before any model call (U)",
                c.name,
                sc("Refused before any model call"),
                u_pre_call(m),
            )
        )
        ed = sc("Edition labeled (citation edition + superseded label)")
        checks.append(
            _nr(
                sec,
                "Edition labeled (V answered)",
                c.name,
                ed,
                NO_CITATIONS + "; Yardstick shows the denominator (V answered) only",
                f"?/{v_answered(run)}",
            )
        )
        checks.append(
            _cmp(
                sec,
                "Outcome as expected (P)",
                c.name,
                sc("Outcome as expected (answer vs refusal)"),
                p_outcome(run),
            )
        )
        sp = sc("Split (O-9)")
        checks.append(_cmp(sec, "Split (all)", c.name, sp.split(";")[0], split(run)))
        si = re.search(r"schema_invalid \d+", sp)
        checks.append(
            _nr(sec, "Split: schema_invalid answer calls", c.name, si.group(0) if si else sp, NO_CAUSE)
        )

    # Whole build ----------------------------------------------------------------------------------------
    sec = "Whole build"
    whole = {r[0].split(" **")[0]: r for r in _section(tables, "Whole build")[1:]}
    judged = [c for c in cells if c.judge]
    sup_row = whole["Sentence support (judge)"][3]
    for c in judged:
        rate, excluded = support(runs[c.name], mets[c.name])
        checks.append(_cmp(sec, "Sentence support (judge), A, M, V", c.name, _head(sup_row), rate))
        si = re.search(r"schema_invalid \d+", sup_row)
        checks.append(
            _cmp(
                sec,
                "Sentence support: schema_invalid verdicts",
                c.name,
                si.group(0) if si else sup_row,
                excluded,
            )
        )
        vs = re.search(r"V edition stated by judge [^|]*$", sup_row)
        checks.append(
            _nr(
                sec,
                "V edition stated by judge",
                c.name,
                vs.group(0) if vs else sup_row,
                "editionStated is in SentenceJudgment rows, not in the answers files",
            )
        )
    reasons = {
        "Tier leaks": "re-reads cited chunks from the database and the pt-injection result file",
        "Planted fabrication caught": "judge-gate result file, not an answers run",
        "Judge-vs-human \u03ba (Opus, pooled sheets)": (
            "Phase 3 (kappa from grade sheets and SentenceJudgment rows)"
        ),
        "Injection fixtures passed": "pt-injection result file, not an answers run",
        "Build spend": (
            "sums every ModelCall row in the database; the answers files carry per-run spentUsd only"
        ),
    }
    for label, reason in reasons.items():
        checks.append(_nr(sec, label, "whole build", whole[label][3], reason))

    # Theta' axis ----------------------------------------------------------------------------------------
    sec = "\u03b8\u2032 axis"
    axis = _section(tables, "\u03b8\u2032 axis")
    axis_rows = {(r[0], r[1]): r for r in axis[1:]}
    for c in cells:
        if c.theta != "off":
            continue
        for t in THETA_AXIS:
            key = (c.name, "off" if t is None else f"{t:g}")
            row = axis_rows[key]
            run = runs[c.name] if t is None else run_cell(suite, c, clock, t)
            m = mets[c.name] if t is None else metrics_mod.compute(run)
            label = f"{c.name} @ {key[1]}"
            checks.append(_cmp(sec, "U refused", label, row[2], _head(u_refusal(run, m))))
            checks.append(_cmp(sec, "U pre-call", label, row[3], u_pre_call(m)))
            checks.append(_cmp(sec, "A, M answered or partial", label, row[4], answered_am(m)))
            checks.append(_nr(sec, "A, M expected cited", label, row[5], NO_CITATIONS))

    # Retrieval -------------------------------------------------------------------------------------------
    retr = _section(tables, "Retrieval")
    checks.append(
        _nr(
            "Retrieval",
            "recall@k / MRR table",
            "retrievers",
            f"{len(retr) - 1} rows",
            "retrieval result file, not an answers run (outside the PRD's answers mapping)",
        )
    )
    return checks


def render(checks: Sequence[Check], *, source: str) -> str:
    counts = {s: sum(1 for c in checks if c.status == s) for s in ("match", "differs", "not reproducible")}
    lines = [
        "# Footnote scorecard, reproduced by Yardstick",
        "",
        f"Source: {source}. Yardstick read Footnote's six committed `answers-*.json` files through the "
        "`footnote` results-file mapping and recomputed every scorecard number those files can support "
        "from its own runs. "
        "Generated by `yardstick footnote reproduce`; zero model calls.",
        "",
        f"**{counts['match']} match, {counts['differs']} differ, "
        f"{counts['not reproducible']} not reproducible** (each with the reason).",
        "",
    ]
    for section in dict.fromkeys(c.section for c in checks):
        lines += [
            f"## {section}",
            "",
            "| Metric | Cell | Scorecard | Yardstick | Result |",
            "|---|---|---|---|---|",
        ]
        for c in (x for x in checks if x.section == section):
            labels = {"match": "match", "differs": "**DIFFERS**"}
            result = labels.get(c.status, f"not reproducible: {c.note}")
            if c.status != "not reproducible" and c.note:
                result += f" ({c.note})"
            cells = (c.metric, c.cell, c.scorecard, c.yardstick, result)
            lines.append("| " + " | ".join(_md(x) for x in cells) + " |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
