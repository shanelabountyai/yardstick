# Yardstick — Claude Code kickoff

`main` holds this kit. Phase 1 builds on `kickoff` (PR #1, never merged by Claude); later phases on `phase-N`.

## Session prompt — Phase 1

```text
You are building Yardstick (build-log #26), an eval harness that sits on top of other projects' AI evals:
common run format, baselines, compare, CI regression gates, reports. Repo shanelabountyai/yardstick; `main` holds
docs/PRD.md, docs/DECISIONS.md, docs/KICKOFF.md. Read all three first. DECISIONS.md rows are in force; when you hit
a new decision, pick the option you'd recommend, append a row (problem, options, decision, how to change it) and
keep going. Never stop to ask.

Phase 1 only — core, no network, no LLM (branch `kickoff` off main):
  1. Scaffold: Python 3.12, src layout, pyproject.toml with pinned versions (pydantic, typer, jinja2, pytest,
     hypothesis, ruff, mypy --strict), uv. GitHub Actions CI: ruff, mypy, pytest.
  2. Write docs/PHASE1_PLAN.md first (module list, scorer list, synthetic suites, gate semantics with examples,
     risks). Commit it, open PR #1 "Yardstick Phase 1: core" against main. Keep it unmerged.
  3. Build per PRD §3, §4 and §6: models.py; scorers exact, regex, json-schema, numeric-tolerance, contains-all,
     refusal-expected, citation-grounded; metrics.py (pass rate, mean, per-slice, p50/p95 latency as integers,
     cost per item); gate.py (floor, max drop vs baseline, min_items); compare; markdown report;
     `command` adapter; CLI commands run / compare / gate / report / baseline pin.
  4. fixtures/: two synthetic suites (a support-bot Q&A with refusals, an extraction task with JSON outputs) and a
     fake target script whose outputs you can degrade by a flag, to prove a gate trips.
  5. Tests: YS-01..YS-04 in tests/invariants/; hypothesis tests for the aggregators; an end-to-end test where the
     degraded fake target fails the gate and the healthy one passes.
  6. Commit examples/report-example.md produced by the CLI.
  7. Gate: ruff, mypy, pytest green. PR body: what was built, gate results, new DECISIONS rows, anything you could
     not verify. Then stop. Do not start Phase 2.

Rules: no network calls or LLM calls in Phase 1; never print a secret; if a gate fails, stop and report rather
than loosen the gate.
```

## Later phases

| Session | Scope | Stop condition |
|---|---|---|
| Phase 2 | results-file adapter + Footnote mapping, HTML report | PRD §8 Phase 2 gate |
| Phase 3 | llm-judge, human grades, kappa | Phase 3 gate |
| Phase 4 | composite action, Footnote branch PR, README case study | Phase 4 gate |
