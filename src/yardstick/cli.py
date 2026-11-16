"""Typer CLI: run / compare / gate / report / kappa / baseline pin, plus the ``footnote`` commands (suite,
reproduce, verdicts, grades, kappa).

Exit codes: 0 ok (or gate passed), 1 gate failed, 2 usage or input error.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import ValidationError

from yardstick import baseline as baseline_mod
from yardstick import footnote_kappa, footnote_scorecard
from yardstick import gate as gate_mod
from yardstick.adapters.base import Adapter, AdapterError
from yardstick.adapters.command import CommandAdapter
from yardstick.adapters.footnote import FootnoteAdapter, suite_from_golden, suite_yaml, verdicts_from_answers
from yardstick.adapters.results_file import ResultsFileAdapter, load_mapping
from yardstick.clock import Clock, SystemClock, parse_fixed
from yardstick.compare import compare as compare_runs
from yardstick.grades import footnote_grade_set, grade_set_yaml, load_grade_set
from yardstick.judge.anthropic import AnthropicJudge
from yardstick.judge.base import Judge, JudgeError
from yardstick.judge.budget import Budget
from yardstick.judge.recorded import RecordedJudge, load_verdicts, verdict_file_json
from yardstick.kappa import (
    Calibration,
    calibrate,
    calibration_json,
    fmt_stat,
    load_calibration,
    verdicts_from_run,
)
from yardstick.models import LLM_JUDGE, GateConfig, Run, Suite
from yardstick.report import markdown
from yardstick.report.format import fmt_delta, fmt_metric
from yardstick.report.html import render_html
from yardstick.runner import run_suite
from yardstick.scorers import ScorerConfigError
from yardstick.scorers.llm_judge import JudgeSession
from yardstick.suite_check import SuiteChangedError
from yardstick.suite_io import LoadError, load_gate, load_run, load_suite, save_run

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Yardstick: baselines, compare and CI regression gates over AI eval runs.",
)
baseline_app = typer.Typer(no_args_is_help=True, help="Manage pinned baselines.")
app.add_typer(baseline_app, name="baseline")
footnote_app = typer.Typer(
    no_args_is_help=True, help="Footnote mapping: build its suite, reproduce its scorecard."
)
app.add_typer(footnote_app, name="footnote")

EXIT_GATE_FAILED = 1
EXIT_USAGE = 2

AllowSuiteChange = Annotated[
    bool,
    typer.Option("--allow-suite-change", help="Compare even if the suite content hash differs (YS-03)."),
]
BaselinesDir = Annotated[Path, typer.Option("--baselines-dir", help="Where pinned baselines live.")]


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(EXIT_USAGE)


def _load_run(path: Path) -> Run:
    try:
        return load_run(path)
    except (LoadError, ValidationError) as exc:
        raise _fail(f"{path}: {exc}") from exc


def _detect_git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def _write_or_echo(text: str, out: Path | None) -> None:
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}", err=True)


def _resolve_baseline(run: Run, explicit: Path | None, directory: Path) -> Run | None:
    if explicit is not None:
        return _load_run(explicit)
    try:
        return baseline_mod.find(run, directory)
    except (LoadError, ValidationError) as exc:
        raise _fail(f"baseline in {directory}: {exc}") from exc


def _make_adapter(
    target_name: str,
    cmd: str | None,
    results: Path | None,
    mapping: str | None,
    theta_prime: float | None,
    timeout: float,
) -> Adapter:
    if (cmd is None) == (results is None):
        raise _fail("give exactly one target: --cmd PROGRAM or --results FILE")
    if cmd is not None:
        if mapping is not None or theta_prime is not None:
            raise _fail("--mapping and --theta-prime apply to --results only")
        return CommandAdapter.from_string(target_name, cmd, timeout_s=timeout)
    assert results is not None
    if mapping is None:
        raise _fail("--results needs --mapping (footnote, or a mapping YAML file)")
    if mapping == "footnote":
        return FootnoteAdapter(target_name, results, theta_prime)
    if theta_prime is not None:
        raise _fail("--theta-prime applies to the footnote mapping only")
    return ResultsFileAdapter(target_name, results, load_mapping(Path(mapping)), Path(mapping).name)


def _make_judge(
    spec: str | None,
    budget_usd: float | None,
    price_in: float | None,
    price_out: float | None,
    max_tokens: int,
    suite: Suite,
) -> JudgeSession | None:
    uses_judge = any(sc.name == LLM_JUDGE for sc in suite.scorers)
    if spec is None:
        if budget_usd is not None:
            raise _fail("--judge-budget-usd needs --judge")
        if uses_judge:
            raise _fail("the suite has an llm-judge scorer: pass --judge and --judge-budget-usd (D-34)")
        return None
    if not uses_judge:
        raise _fail("--judge given, but the suite has no llm-judge scorer")
    if budget_usd is None:
        raise _fail("--judge needs --judge-budget-usd (the cap on judge spend for this run, D-37)")
    kind, _, arg = spec.partition(":")
    judge: Judge
    try:
        if kind == "replay" and arg:
            judge = RecordedJudge.from_path(Path(arg))
        elif kind == "anthropic" and arg:
            if price_in is None or price_out is None:
                raise _fail(
                    "--judge anthropic:MODEL needs --judge-price-in and --judge-price-out (USD per MTok)"
                )
            judge = AnthropicJudge(
                arg, price_in_per_mtok=price_in, price_out_per_mtok=price_out, max_tokens=max_tokens
            )
        else:
            raise _fail("--judge must be replay:VERDICTS.json or anthropic:MODEL")
        return JudgeSession(judge, Budget(budget_usd))
    except (JudgeError, ValueError) as exc:
        raise _fail(str(exc)) from exc


@app.command()
def run(
    suite: Annotated[Path, typer.Option("--suite", "-s", help="Suite file (YAML or JSON).")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the run JSON.")],
    cmd: Annotated[
        str | None, typer.Option("--cmd", help="Command target: program printing JSONL outputs.")
    ] = None,
    results: Annotated[
        Path | None, typer.Option("--results", help="Results-file target: a project's result JSON.")
    ] = None,
    mapping: Annotated[
        str | None, typer.Option("--mapping", help="For --results: 'footnote' or a mapping YAML file.")
    ] = None,
    theta_prime: Annotated[
        float | None,
        typer.Option("--theta-prime", help="Footnote mapping: replay the theta gate at this value."),
    ] = None,
    target_name: Annotated[str, typer.Option("--target-name", help="Name used for baselines.")] = "command",
    model: Annotated[str | None, typer.Option(help="Model identifier to record.")] = None,
    prompt_hash: Annotated[str | None, typer.Option("--prompt-hash", help="Prompt hash to record.")] = None,
    git_sha: Annotated[
        str | None, typer.Option("--git-sha", help="Git SHA to record (default: detect).")
    ] = None,
    no_git: Annotated[bool, typer.Option("--no-git", help="Do not detect or record a git SHA.")] = False,
    fixed_clock: Annotated[
        str | None, typer.Option("--fixed-clock", help="ISO timestamp to record instead of now.")
    ] = None,
    timeout: Annotated[float, typer.Option(help="Target timeout in seconds.")] = 300.0,
    judge: Annotated[
        str | None,
        typer.Option(
            "--judge",
            help="For llm-judge scorers: replay:VERDICTS.json (no calls) or anthropic:MODEL (live).",
        ),
    ] = None,
    judge_budget_usd: Annotated[
        float | None, typer.Option("--judge-budget-usd", help="Cap on judge spend for the whole run (USD).")
    ] = None,
    judge_price_in: Annotated[
        float | None, typer.Option("--judge-price-in", help="Live judge: USD per million input tokens.")
    ] = None,
    judge_price_out: Annotated[
        float | None, typer.Option("--judge-price-out", help="Live judge: USD per million output tokens.")
    ] = None,
    judge_max_tokens: Annotated[
        int, typer.Option("--judge-max-tokens", help="Live judge: max output tokens per call.")
    ] = 256,
) -> None:
    """Run a suite against a command or results-file target and write the run JSON."""
    try:
        s = load_suite(suite)
    except (LoadError, ValidationError) as exc:
        raise _fail(f"{suite}: {exc}") from exc
    clock: Clock = parse_fixed(fixed_clock) if fixed_clock else SystemClock()
    sha = None if no_git else (git_sha or _detect_git_sha())
    session = _make_judge(judge, judge_budget_usd, judge_price_in, judge_price_out, judge_max_tokens, s)
    try:
        adapter = _make_adapter(target_name, cmd, results, mapping, theta_prime, timeout)
        r = run_suite(
            s, adapter, clock=clock, model=model, prompt_hash=prompt_hash, git_sha=sha, judge=session
        )
    except (AdapterError, ScorerConfigError) as exc:
        raise _fail(str(exc)) from exc
    save_run(r, out)
    passed = sum(1 for i in r.items if i.passed)
    typer.echo(f"{r.run_id}  {s.name}  {passed}/{len(r.items)} passed  -> {out}")
    for key, rec in r.judges.items():
        typer.echo(
            f"judge {key}: {rec.model} ({rec.source}), {rec.calls} calls, {rec.units_judged} units judged, "
            f"{rec.units_invalid} invalid, {rec.units_skipped_budget} not judged (budget), "
            f"spent ${rec.spent_usd:.6f} of ${rec.cap_usd:.6f}{' OVER ESTIMATE' if rec.overrun else ''}"
        )


@app.command()
def compare(
    run_a: Annotated[Path, typer.Argument(help="Run A (e.g. baseline).")],
    run_b: Annotated[Path, typer.Argument(help="Run B (e.g. candidate).")],
    allow_suite_change: AllowSuiteChange = False,
) -> None:
    """Show metric deltas and item flips from run A to run B."""
    a, b = _load_run(run_a), _load_run(run_b)
    try:
        c = compare_runs(a, b, allow_suite_change=allow_suite_change)
    except SuiteChangedError as exc:
        raise _fail(str(exc)) from exc
    for w in c.warnings:
        typer.echo(f"warning: {w}")
    typer.echo(f"{'metric':<28} {'A':>16} {'B':>16} {'change':>14}")
    for d in c.deltas:
        label = d.metric if d.slice is None else f"{d.metric}[{d.slice}]"
        typer.echo(
            f"{label:<28} {fmt_metric(d.metric, d.a):>16} {fmt_metric(d.metric, d.b):>16} "
            f"{fmt_delta(d.metric, d.delta):>14}"
        )
    typer.echo(f"newly failing: {', '.join(c.newly_failing) or '-'}")
    typer.echo(f"newly passing: {', '.join(c.newly_passing) or '-'}")
    if c.only_in_a or c.only_in_b:
        typer.echo(f"only in A: {', '.join(c.only_in_a) or '-'}; only in B: {', '.join(c.only_in_b) or '-'}")


Calibrations = Annotated[
    list[Path] | None,
    typer.Option("--calibration", help="Judge calibration JSON from `yardstick kappa` (repeatable; YS-05)."),
]


def _calibrations(cfg: GateConfig, config_path: Path | None, extra: list[Path] | None) -> list[Calibration]:
    paths = list(extra or [])
    if cfg.judge is not None and config_path is not None:
        paths += [config_path.parent / p for p in cfg.judge.calibrations]
    try:
        return [load_calibration(p) for p in paths]
    except (OSError, ValueError, ValidationError) as exc:
        raise _fail(f"calibration: {exc}") from exc


@app.command()
def gate(
    run_path: Annotated[Path, typer.Argument(help="Run JSON to gate.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="Gate config (YAML or JSON).")],
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline run (default: pinned one).")
    ] = None,
    baselines_dir: BaselinesDir = baseline_mod.DEFAULT_DIR,
    allow_suite_change: AllowSuiteChange = False,
    report_out: Annotated[
        Path | None, typer.Option("--report", help="Also write the markdown report here.")
    ] = None,
    html_out: Annotated[
        Path | None, typer.Option("--html-report", help="Also write the HTML report here.")
    ] = None,
    calibration: Calibrations = None,
) -> None:
    """Evaluate a gate. Exit 0 if it passes, 1 if it fails."""
    r = _load_run(run_path)
    try:
        cfg = load_gate(config)
    except (LoadError, ValidationError) as exc:
        raise _fail(f"{config}: {exc}") from exc
    cals = _calibrations(cfg, config, calibration)
    base = _resolve_baseline(r, baseline, baselines_dir)
    try:
        result = gate_mod.evaluate(cfg, r, base, allow_suite_change=allow_suite_change, calibrations=cals)
    except SuiteChangedError as exc:
        raise _fail(str(exc)) from exc
    text = markdown.render(r, baseline=base, gate=result, allow_suite_change=allow_suite_change)
    if report_out is not None:
        _write_or_echo(text, report_out)
    if html_out is not None:
        html = render_html(r, baseline=base, gate=result, allow_suite_change=allow_suite_change)
        _write_or_echo(html, html_out)
    for w in result.warnings:
        typer.echo(f"warning: {w}")
    for rr in result.rules:
        status = "PASS" if rr.passed else "FAIL"
        if rr.report_only:
            status = f"({status.lower()})"
        detail = "; ".join(f"{c.check}: {c.detail}" for c in rr.checks if not c.passed) or "ok"
        if rr.note:
            detail += f"; {rr.note}"
        typer.echo(f"{status:<6}  {rr.rule.label:<28} {detail}")
    typer.echo("gate PASSED" if result.passed else "gate FAILED")
    if not result.passed:
        raise typer.Exit(EXIT_GATE_FAILED)


@app.command()
def report(
    run_path: Annotated[Path, typer.Argument(help="Run JSON to report on.")],
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline run to compare.")
    ] = None,
    gate_config: Annotated[Path | None, typer.Option("--gate", "-g", help="Gate config to evaluate.")] = None,
    allow_suite_change: AllowSuiteChange = False,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
    fmt: Annotated[
        Literal["md", "html"], typer.Option("--format", "-f", help="md (default) or html.")
    ] = "md",
    calibration: Calibrations = None,
) -> None:
    """Render a markdown or HTML report for a run (optionally vs a baseline and with a gate)."""
    r = _load_run(run_path)
    base = _load_run(baseline) if baseline else None
    try:
        result = None
        if gate_config is not None:
            cfg = load_gate(gate_config)
            cals = _calibrations(cfg, gate_config, calibration)
            result = gate_mod.evaluate(cfg, r, base, allow_suite_change=allow_suite_change, calibrations=cals)
        render = render_html if fmt == "html" else markdown.render
        text = render(r, baseline=base, gate=result, allow_suite_change=allow_suite_change)
    except (LoadError, ValidationError, SuiteChangedError) as exc:
        raise _fail(str(exc)) from exc
    _write_or_echo(text, out)


@app.command()
def kappa(
    grades: Annotated[list[Path], typer.Option("--grades", help="Human grade set file (repeatable).")],
    run_path: Annotated[
        Path | None, typer.Option("--run", help="Run whose llm-judge labels to use (with --key).")
    ] = None,
    key: Annotated[str | None, typer.Option("--key", help="The llm-judge scorer key in --run.")] = None,
    verdicts: Annotated[
        Path | None, typer.Option("--verdicts", help="Or: a recorded verdict file instead of a run.")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write the calibration JSON here (for gates).")
    ] = None,
) -> None:
    """Cohen's kappa of a judge against human grades, per grade set and pooled (calibration for YS-05)."""
    try:
        sets = [load_grade_set(p) for p in grades]
        if (run_path is None) == (verdicts is None):
            raise _fail("give exactly one judge source: --run RUN --key KEY, or --verdicts FILE")
        if run_path is not None:
            if key is None:
                raise _fail("--run needs --key (the llm-judge scorer key)")
            identity, labels = verdicts_from_run(_load_run(run_path), key)
        else:
            assert verdicts is not None
            vf = load_verdicts(verdicts)
            judge = RecordedJudge(vf, verdicts.name)
            identity = judge.identity("", vf.labels)
            labels = dict(vf.verdicts)
        cal = calibrate(sets, labels, identity)
    except (OSError, ValueError, ValidationError, JudgeError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"judge {cal.judge_model} prompt {cal.prompt_hash} ({cal.judge_source})")
    for st in [*cal.sets, cal.pooled] if len(cal.sets) > 1 else cal.sets:
        typer.echo(f"  {fmt_stat(st)}")
        for d in st.disagreements:
            typer.echo(f"    disagree {d.ref or d.key}: human {d.human}, judge {d.judge}")
    if out is not None:
        _write_or_echo(calibration_json(cal), out)


@baseline_app.command("pin")
def baseline_pin(
    run_path: Annotated[Path, typer.Argument(help="Run JSON to pin as the baseline.")],
    baselines_dir: BaselinesDir = baseline_mod.DEFAULT_DIR,
) -> None:
    """Pin a run as the baseline for its suite + target."""
    r = _load_run(run_path)
    path = baseline_mod.pin(r, baselines_dir)
    typer.echo(f"pinned {r.run_id} -> {path}")


@footnote_app.command("suite")
def footnote_suite(
    golden: Annotated[Path, typer.Argument(help="Footnote's eval/golden.json.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
    judged: Annotated[
        bool, typer.Option("--judged", help="Add the sentence judge as llm-judge (footnote-golden-judged).")
    ] = False,
) -> None:
    """Build the Yardstick suite `footnote-golden` from Footnote's golden set."""
    try:
        data = json.loads(golden.read_text(encoding="utf-8"))
        s = suite_from_golden(data, judged=judged)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise _fail(f"{golden}: {exc}") from exc
    _write_or_echo(suite_yaml(s), out)


@footnote_app.command("reproduce")
def footnote_reproduce(
    results_dir: Annotated[Path, typer.Option("--results-dir", help="Folder with answers-*.json.")],
    golden: Annotated[Path, typer.Option("--golden", help="Footnote's eval/golden.json.")],
    scorecard: Annotated[Path, typer.Option("--scorecard", help="Footnote's committed scorecard markdown.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
    fixed_clock: Annotated[
        str, typer.Option("--fixed-clock", help="ISO timestamp recorded in the runs.")
    ] = "2026-11-14T00:00:00Z",
    source: Annotated[
        str, typer.Option(help="Where the files came from, for the report header.")
    ] = "Footnote result files",
) -> None:
    """Run Footnote's answers files through Yardstick and check them against its scorecard.

    Exit 0 when every reproducible number matches, 1 when any differs.
    """
    try:
        checks = footnote_scorecard.reproduce(results_dir, golden, scorecard, parse_fixed(fixed_clock))
    except (OSError, ValueError, KeyError, AdapterError, ValidationError) as exc:
        raise _fail(str(exc)) from exc
    _write_or_echo(footnote_scorecard.render(checks, source=source), out)
    differs = [c for c in checks if c.status == "differs"]
    for c in differs:
        typer.echo(
            f"DIFFERS  {c.metric} [{c.cell}]: scorecard {c.scorecard!r} vs yardstick {c.yardstick!r}",
            err=True,
        )
    if differs:
        raise typer.Exit(EXIT_GATE_FAILED)


@footnote_app.command("verdicts")
def footnote_verdicts(
    answers: Annotated[Path, typer.Argument(help="A judged Footnote answers-*.json file.")],
    source: Annotated[str, typer.Option(help="Where the file came from, recorded in the output.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
) -> None:
    """Write the judge verdicts committed in a Footnote answers file as a replayable verdict file."""
    try:
        vf = verdicts_from_answers(json.loads(answers.read_text(encoding="utf-8")), source)
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise _fail(f"{answers}: {exc}") from exc
    _write_or_echo(verdict_file_json(vf), out)


@footnote_app.command("grades")
def footnote_grades(
    sheet: Annotated[Path, typer.Argument(help="A graded Footnote sheet (eval/grades*.md).")],
    answers: Annotated[Path, typer.Option("--answers", help="The answers file the sheet was drawn from.")],
    name: Annotated[str, typer.Option(help="Grade set name, e.g. sheet-1.")],
    source: Annotated[str, typer.Option(help="Where the sheet came from, recorded in the output.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
) -> None:
    """Convert a Footnote grade sheet to a grade set keyed <golden id>:<sentence index>."""
    try:
        gs = footnote_grade_set(
            sheet.read_text(encoding="utf-8"),
            json.loads(answers.read_text(encoding="utf-8")),
            name=name,
            source=source,
        )
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise _fail(f"{sheet}: {exc}") from exc
    header = f"# Generated by `yardstick footnote grades` from Footnote's {sheet.name}. Do not edit.\n"
    _write_or_echo(grade_set_yaml(gs, header), out)


@footnote_app.command("kappa")
def footnote_kappa_cmd(
    golden: Annotated[Path, typer.Option("--golden", help="Footnote's eval/golden.json.")],
    answers: Annotated[Path, typer.Option("--answers", help="Answers file of the judged run (1646).")],
    sheet: Annotated[list[Path], typer.Option("--sheet", help="Grade sheet, in order (repeatable).")],
    reference: Annotated[Path, typer.Option("--reference", help="Reference figures (kappa-reference.yaml).")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write here instead of stdout.")] = None,
    calibration_out: Annotated[
        Path | None, typer.Option("--calibration-out", help="Also write the judge calibration JSON here.")
    ] = None,
    fixed_clock: Annotated[
        str, typer.Option("--fixed-clock", help="ISO timestamp recorded in the run.")
    ] = "2026-11-16T00:00:00Z",
    source: Annotated[
        str, typer.Option(help="Where the files came from, for the report header.")
    ] = "Footnote eval files",
) -> None:
    """Phase 3 gate: reproduce Footnote's eval:kappa figures through Yardstick. Exit 1 on any difference."""
    try:
        rep = footnote_kappa.reproduce(golden, answers, sheet, reference, parse_fixed(fixed_clock), source)
    except (OSError, ValueError, KeyError, TypeError, ValidationError, JudgeError, AdapterError) as exc:
        raise _fail(str(exc)) from exc
    _write_or_echo(footnote_kappa.render(rep, source=source), out)
    if calibration_out is not None:
        _write_or_echo(calibration_json(rep.calibration), calibration_out)
    differs = [c for c in rep.checks if c.status == "differs"]
    for c in differs:
        typer.echo(f"DIFFERS  {c.set} {c.judge} {c.figure}: doc {c.reference!r} vs {c.yardstick!r}", err=True)
    if differs:
        raise typer.Exit(EXIT_GATE_FAILED)


if __name__ == "__main__":  # pragma: no cover
    app()
