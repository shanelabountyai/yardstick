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
