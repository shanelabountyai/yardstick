"""Phase 3 gate: kappa on Footnote's graded sentences, reproduced through Yardstick, against ``eval:kappa``.

Pipeline (all offline, zero model calls):

1. Footnote's two grade sheets -> grade sets keyed ``<golden id>:<sentence index>`` (:mod:`yardstick.grades`).
2. Its committed Opus verdicts (answers file of run 1646) -> a replayable verdict file.
3. A Yardstick run of suite ``footnote-golden-judged`` over that answers file, with the ``llm-judge`` scorer
   replaying the verdicts under a $0 budget cap.
4. Kappa per sheet and pooled from the run's stored judge labels (:mod:`yardstick.kappa`), each figure
   formatted as ``scripts/kappa.ts`` prints it (JS ``toFixed``), compared with the reference figures
   Footnote's docs record.

The Sonnet re-judge (run ``rejudge:claude-sonnet-5-5:2026-10-23T1646``) is not reproducible: its verdicts
exist only as SentenceJudgment rows in Footnote's database, and no committed file holds them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from yardstick.adapters.footnote import JUDGE_KEY, FootnoteAdapter, suite_from_golden, verdicts_from_answers
from yardstick.clock import Clock
from yardstick.grades import GradeSet, footnote_grade_set
from yardstick.judge.budget import Budget
from yardstick.judge.recorded import RecordedJudge
from yardstick.kappa import Calibration, KappaStat, calibrate, js_fixed, verdicts_from_run
from yardstick.models import Run
from yardstick.runner import run_suite
from yardstick.scorers.llm_judge import JudgeSession

Status = Literal["match", "differs", "not reproducible"]

OPUS_RUN = "answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646"
SONNET_RUN = "rejudge:claude-sonnet-5-5:2026-10-23T1646"
SONNET_MISSING = (
    f"needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `{SONNET_RUN}`); they live only in "
    "Footnote's database and no committed file holds them"
)
#: kappa.ts sheet labels, by grade set name.
SHEET_LABELS = {
    "sheet-1": "sheet 1 (enriched, Claude-assisted, D-39)",
    "sheet-2": "sheet 2 (unassisted, D-41)",
    "pooled": "pooled",
}
KAPPA_TARGET = 0.7  # Footnote's KAPPA_TARGET, printed by kappa.ts


@dataclass(frozen=True)
class KappaCheck:
    set: str
    judge: str
    figure: str
    reference: str
    yardstick: str
    status: Status
    note: str = ""
    #: 1-based index of the reference entry (one quoted line of Footnote's docs) the figure comes from.
    quote: int = 0


@dataclass(frozen=True)
class Reproduction:
    run: Run
    calibration: Calibration
    checks: list[KappaCheck]
    console: list[str]
    #: The reference quotes, in order (``KappaCheck.quote`` indexes them from 1).
    quotes: tuple[str, ...] = ()


def grade_sets(sheets: Sequence[Path], answers: dict[str, Any], source: str) -> list[GradeSet]:
    out = []
    for n, path in enumerate(sheets, start=1):
        out.append(
            footnote_grade_set(
                path.read_text(encoding="utf-8"),
                answers,
                name=f"sheet-{n}",
                source=f"{source}: eval/{path.name}",
            )
        )
    return out


def judged_run(golden: Path, answers_path: Path, verdicts: RecordedJudge, clock: Clock) -> Run:
    suite = suite_from_golden(json.loads(golden.read_text(encoding="utf-8")), judged=True)
    session = JudgeSession(verdicts, Budget(0.0))
    adapter = FootnoteAdapter("footnote-hybrid-sonnet-theta-on", answers_path)
    return run_suite(suite, adapter, clock=clock, judge=session)


def _counts(c: dict[str, int]) -> str:
    return "/".join(f"{lab[0]}{n}" for lab, n in c.items())


def console_lines(stat: KappaStat, judge_name: str, run_id: str) -> list[str]:
    """What ``scripts/kappa.ts`` prints for one (set, judge)."""
    if stat.n == 0:
        return []
    assert stat.observed is not None and stat.expected is not None
    kappa = "null (p_e = 1)" if stat.kappa is None else js_fixed(stat.kappa, 2)
    lines = [
        f"{SHEET_LABELS.get(stat.name, stat.name)} \u00b7 {judge_name} \u00b7 {run_id}",
        f"  n {stat.n} ({stat.missing} without a usable verdict)  raw agreement "
        f"{js_fixed(stat.observed * 100, 0)}%  p_e {js_fixed(stat.expected, 3)}  \u03ba {kappa}  "
        f"target \u2265 {KAPPA_TARGET}",
        f"  Shane {_counts(stat.human_counts)}  judge {_counts(stat.judge_counts)}",
    ]
    lines += [f"  disagree {d.ref}: Shane {d.human}, judge {d.judge}" for d in stat.disagreements]
    return [*lines, ""]


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(text: str) -> str:
    m = _NUM.search(text.replace("\u2212", "-"))
    if m is None:
        raise ValueError(f"no number in reference value {text!r}")
    return m.group(0)


def _figures(stat: KappaStat) -> dict[str, str]:
    assert stat.observed is not None and stat.expected is not None
    return {
        "n": str(stat.n),
        "raw": js_fixed(stat.observed * 100, 0) + "%",
        "p_e": js_fixed(stat.expected, 3),
        "kappa": "null" if stat.kappa is None else js_fixed(stat.kappa, 2),
        "misses": str(len(stat.disagreements)),
        "human_counts": ", ".join(f"{v} {k}" for k, v in stat.human_counts.items()),
    }


def _ref_figure(field: str, value: str) -> str:
    if field == "human_counts":
        counts = re.findall(r"(\d+) (supported|partial|unsupported)", value)
        return ", ".join(f"{n} {lab}" for n, lab in counts)
    return _num(value) + ("%" if field == "raw" else "")


def compare(calibration: Calibration, reference: dict[str, Any]) -> list[KappaCheck]:
    stats = {s.name: s for s in calibration.sets} | {"pooled": calibration.pooled}
    checks: list[KappaCheck] = []
    for quote, ref in enumerate(reference["checks"], start=1):
        set_name, judge = str(ref["set"]), str(ref["judge"])
        fields: list[tuple[str, str]] = [(k, str(v)) for k, v in ref.get("values", {}).items()]
        if "disagree" in ref:
            fields.append(("disagree", ", ".join(sorted(ref["disagree"]))))
        for field, value in fields:
            if judge != "opus":
                checks.append(
                    KappaCheck(
                        set_name, judge, field, value, "\u2014", "not reproducible", SONNET_MISSING, quote
                    )
                )
                continue
            stat = stats.get(set_name)
            if stat is None or stat.n == 0:
                checks.append(KappaCheck(set_name, judge, field, value, "not computed", "differs", "", quote))
                continue
            if field == "disagree":
                ys = ", ".join(sorted(d.ref for d in stat.disagreements))
                ok = ys == value
                ref_shown = value
            else:
                ys = _figures(stat)[field]
                ref_shown = _ref_figure(field, value)
                ok = ys == ref_shown
            checks.append(
                KappaCheck(
                    set_name,
                    judge,
                    field,
                    value,
                    ys,
                    "match" if ok else "differs",
                    f"reference {ref_shown}",
                    quote,
                )
            )
    return checks


def reproduce(
    golden: Path,
    answers_path: Path,
    sheets: Sequence[Path],
    reference_path: Path,
    clock: Clock,
    source: str = "shanelabountyai/footnote @ 3c9b0c7",
) -> Reproduction:
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    if answers.get("runId") != OPUS_RUN:
        raise ValueError(f"{answers_path}: expected run {OPUS_RUN}, got {answers.get('runId')}")
    judge = RecordedJudge(verdicts_from_answers(answers, f"{source}: {answers_path.name}"), answers_path.name)
    run = judged_run(golden, answers_path, judge, clock)
    identity, verdicts = verdicts_from_run(run, JUDGE_KEY)
    sets = grade_sets(sheets, answers, source)
    cal = calibrate(sets, verdicts, identity)
    reference = yaml.safe_load(reference_path.read_text(encoding="utf-8"))
    console: list[str] = []
    stats = [*cal.sets, cal.pooled] if len(cal.sets) > 1 else cal.sets
    for stat in stats:
        console += console_lines(stat, "opus", OPUS_RUN)
    quotes = tuple(str(ref.get("quote", "")) for ref in reference["checks"])
    return Reproduction(run, cal, compare(cal, reference), console, quotes)


def render(rep: Reproduction, *, source: str) -> str:
    rows = rep.checks
    n_match = sum(1 for c in rows if c.status == "match")
    n_diff = sum(1 for c in rows if c.status == "differs")
    n_nr = sum(1 for c in rows if c.status == "not reproducible")
    j = rep.run.judges[JUDGE_KEY]
    lines = [
        "# Footnote kappa reproduction (Yardstick Phase 3 gate)",
        "",
        f"Source: {source}. Inputs: `eval/grades.md`, `eval/grades-2.md`, and the Opus verdicts committed "
        f"in the answers file of run `{OPUS_RUN}`, replayed by Yardstick's `llm-judge` scorer "
        f"(judge {j.model}, prompt hash `{j.prompt_hash}`, {j.calls} replayed calls, spend "
        f"${j.spent_usd:.6f} under a ${j.cap_usd:.6f} cap). Reference: the figures `npm run eval:kappa` "
        "printed, as recorded in Footnote's committed docs (`fixtures/footnote/kappa-sources.md`).",
        "",
        f"**{n_match} match, {n_diff} differ, {n_nr} not reproducible.**",
        "",
        "Each row is one figure as one quoted line of Footnote's docs records it (column Quote; the quotes",
        "are listed under the table). A figure recorded by two docs is checked against each, which is why",
        "the pooled Opus n, raw agreement and kappa appear twice, once per quote.",
        "",
        "| Quote | Set | Judge | Figure | Footnote (doc) | Yardstick | Status | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    # Repeated reasons become markers defined once under the table (PRD-F, D-89).
    reasons: dict[str, str] = {}
    for c in rows:
        note = ""
        if c.status == "not reproducible":
            note = reasons.setdefault(c.note, f"[{chr(ord('a') + len(reasons))}]")
        elif c.status == "differs":
            note = _md(c.note)
        q = f"Q{c.quote}" if c.quote else ""
        lines.append(
            f"| {q} | {c.set} | {c.judge} | {c.figure} | {_md(c.reference)} | {_md(c.yardstick)} "
            f"| {c.status} | {note} |"
        )
    lines.append("")
    for reason, marker in reasons.items():
        lines.append(f"{marker} {_md(reason)}")
        lines.append("")
    used = sorted({c.quote for c in rows if c.quote})
    if used and rep.quotes:
        lines.append("Quotes (verbatim in `fixtures/footnote/kappa-sources.md`):")
        lines.append("")
        lines += [f"- Q{n}: {rep.quotes[n - 1]}" for n in used]
    lines += [
        "",
        "## As `eval:kappa` prints it (Opus), recomputed by Yardstick",
        "",
        "```text",
        *[x for x in rep.console],
        "```",
        "",
        f"Replayed support rate on A+M+V: {_support(rep.run)} (Phase 2's `label-rate` gives the same 49/51).",
        "",
    ]
    return "\n".join(lines)


def _support(run: Run) -> str:
    hits = total = 0
    for item in run.items:
        if "A+M+V" not in item.slices:
            continue
        for s in item.scores:
            if s.key == JUDGE_KEY:
                h, t = s.counts()
                hits, total = hits + h, total + t
    return f"{hits}/{total}"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
