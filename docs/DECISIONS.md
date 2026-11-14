# Yardstick — decisions

Made by Claude on 2026-11-13 while Shane was away. Each is a default he can change.

| ID | Problem | Options | Decision | Change it |
|---|---|---|---|---|
| D-01 | Footnote already has its own eval system (golden set, judge, kappa, scorecard) | (a) Yardstick replaces it, (b) Yardstick adapts to it and adds baselines/gates/compare across projects | **(b)** — no duplicate work, and "plugs into existing evals" is the more realistic enterprise story | none recommended |
| D-02 | Language | (a) Python CLI, (b) TypeScript CLI | **(a)** — eval tooling norm; target-language agnostic since adapters read JSON | (b) if you want one stack across the log |
| D-03 | First real target | (a) Footnote (public, committed result files), (b) opsagent, (c) Use-Case Studio | **(a)** — the only one this session could read; opsagent and Use-Case Studio were not reachable from here | add adapters in Phase 4+ |
| D-04 | Where baselines live | (a) in each target repo under `.yardstick/`, (b) central in yardstick | **(a)** — baseline changes get reviewed in the same PR as the code that moved them | — |
| D-05 | Footnote fixtures in the Yardstick repo | (a) copy a few result files with attribution (both repos public), (b) fetch at test time | **(a)** — tests stay offline | (b) if you'd rather not copy |
| D-06 | LLM judge in v1 | (a) Phase 3, report-only until kappa clears a floor, (b) skip | **(a)**, floor κ ≥ 0.6 (a common "substantial agreement" cut-off; tune in config) | change `judge.kappa_floor` |
| D-07 | How far the first unattended run goes | (a) stop after plan, (b) build Phase 1, stop at the Phase 2 gate | **(b)** — Phase 1 is offline and cheap to redo | tell next session to redo |

Phase 1 decisions, made by Claude on 2026-11-14 during the unattended Phase 1 run.

| ID | Problem | Options | Decision | Change it |
|---|---|---|---|---|
| D-08 | `json-schema` scorer and YAML suites need libraries beyond the KICKOFF list | (a) add pinned `jsonschema` + `PyYAML`, (b) hand-roll a schema subset and JSON-only suites | **(a)** — standard, typed (`types-*` stubs), offline | drop YAML by making suites JSON-only |
| D-09 | Some items report latency/cost and others don't | (a) compute over the reporting subset, (b) zero-fill, (c) whole metric "not reported", with coverage shown | **(c)** — strictest reading of YS-04; the report says "not reported (7/12 items)" | change `metrics.compute` to (a) and keep the coverage count |
| D-10 | Percentile method for p50/p95 latency | (a) nearest-rank, (b) linear interpolation | **(a)** — always an observed value, so integer ms stay integers | swap `metrics.nearest_rank` |
| D-11 | What a gate does with missing inputs | (a) fail closed, (b) skip the check | **(a)** — `max_drop`/`max_rise` with no baseline fails ("no baseline"), a not-reported metric fails, an empty rule list fails | per-rule: remove the drop check when no baseline exists |
| D-12 | Units and float noise in gate comparisons | (a) absolute drop in the metric's own units, compared after rounding to 6 dp, (b) relative drop | **(a)** — `max_drop: 0.02` means 2 points of pass rate; 0.92 → 0.90 passes a 0.02 gate | change `gate.PRECISION` or add a `relative: true` rule flag |
| D-13 | How several scorers combine on one item | (a) item passes only if every applicable scorer passes, score = mean, (b) weighted | **(a)**; an item's `expected` is keyed by scorer key, and a scorer applies only where the item has that key | add `weight` to `ScorerSpec` |
| D-14 | `command` target protocol | (a) one process per suite, JSONL on stdin/stdout, no shell, (b) one process per item | **(a)** — cheap and simple; a per-item `error` fails that item only, a crashed/timeout process aborts the run (exit 2) | add a `per_item: true` mode |
| D-15 | Detecting refusals | (a) prefer the target's explicit `refused` flag, fall back to marker phrases, (b) phrases only | **(a)** — phrases are heuristic; real targets should emit the flag | override phrases with the scorer's `markers` option |
| D-16 | Citation syntax for `citation-grounded` | (a) `[[source-id: "quote"]]` inline, (b) a separate structured field | **(a)** for Phase 1 synthetic data; Footnote's own format gets mapped in the Phase 2 adapter | add a structured-citations path in Phase 2 |
| D-17 | Run identity and suite hash | (a) run id = content hash excluding `started_at`; suite hash covers name, scorers, items but not description | **(a)** — reruns with identical outputs share an id; editing a description doesn't break baselines | include description in `Suite.content_hash` |
| D-18 | CLI exit codes and baseline lookup | (a) 0 ok/pass, 1 gate failed, 2 bad input/target failure; `gate` auto-loads `.yardstick/baselines/<suite>__<target>.json` | **(a)** — CI can tell a regression from a broken setup | pass `--baseline` explicitly |
| D-19 | Tooling details | build backend hatchling 1.33.0; mypy `--strict` also covers `tests/` and `fixtures/targets/`; CI checks the example report is regenerated byte-identically | as stated | edit `pyproject.toml` / `.github/workflows/ci.yml` |
