# Yardstick — Phase 4 plan

Scope, exactly as PRD §8 row 4 and §4 last bullet: a **GitHub composite action** (`action.yml`) that runs
`yardstick gate` and posts the markdown report; a **branch in Footnote** adding a Yardstick gate step (PR left
unmerged); a **README case study**. Branch `phase-4`, one PR against `main`, never merged by Claude.

**Gate (PRD §8):** the action runs green on the Footnote branch. Plus the standing gates: ruff (lint + format),
mypy `--strict`, pytest (unit, property, YS-01..YS-05), examples regenerate byte-identically, and the action's own
self-test, all green in Yardstick's GitHub CI.

Not in Phase 4: the `http` adapter, new scorers, a hosted dashboard, anything past PRD §8.

**Owner rule (2026-11-15): no live LLM API calls and no API keys**, in this run or in any workflow added. The
Footnote gate runs on Footnote's committed outputs and the replayed (recorded) judge, under a $0 judge budget. Any
`llm-judge` rule stays report-only (YS-05): Footnote's judge has pooled κ 0.17 < 0.6, and a live judge is never
configured. Adding `ANTHROPIC_API_KEY` as a repo secret and running the gate live is an owner hand step.

## What Footnote has (read from `shanelabountyai/footnote` @ `3c9b0c7`, unchanged since Phases 2-3)

- `.github/workflows/ci.yml`: `ci` (Postgres service, lint, typecheck, vitest, PT-1, Playwright) and
  `modules-removed`, on push to main, tags and every PR. No secrets used.
- Committed eval outputs: `eval/golden.json`, six `eval/results/answers-*.json` cells, `eval/grades.md`,
  `eval/grades-2.md`, the scorecard. Footnote's product default is **dense + Sonnet, θ 0.52** (its D-46), which
  Yardstick replays from the dense+Sonnet θ-off cell with `--theta-prime 0.52` (D-29 there, Phase 2 here).
- The committed cells miss Footnote's own absolute targets (A+M answered-or-partial ≥ 90%, U refusal ≥ 90%);
  Yardstick's Phase 2 example gate fails for that reason. A gate that is "green on the Footnote branch" therefore
  has to be a **regression gate** against a pinned baseline, which is the PRD's own purpose ("fails CI on a
  regression"). Footnote's targets stay visible in its scorecard. Recorded as a DECISIONS row.

## Tasks

1. **Comment poster** `src/yardstick/github_comment.py` (stdlib `urllib`, no new dependency): find the PR number
   from `$GITHUB_EVENT_PATH`, look for an existing issue comment carrying a hidden marker
   `<!-- yardstick:<tag> -->`, PATCH it or POST a new one; truncate a body over GitHub's 65 536-character limit with
   a note; no PR (push event) → skip; HTTP 403/404 (fork PR, read-only token) → warning, not a failure. Runnable as
   `python -m yardstick.github_comment`. Transport injectable for tests.
2. **`action.yml`** (composite, repo root). Inputs: `suite`, `gate-config` (thresholds), `report-path`, target
   (`results` + `mapping`, or `command`), `target-name`, `run-args`, `baseline`, `calibration`, `comment`,
   `comment-tag`, `fail-on-gate`, `install-only`, `github-token` (default `github.token`). Steps: install a pinned
   `uv` from PyPI into a temp venv (no third-party actions, so nothing to pin by SHA), `uv sync --locked` the
   action's own checkout (`github.action_path`, i.e. the ref the caller named), put its venv on `PATH`, run
   `yardstick run` then `yardstick gate --report`, append the report to `$GITHUB_STEP_SUMMARY`, post or update one
   PR comment with the token, then exit with the gate's code (unless `fail-on-gate: false`). Outputs: `passed`,
   `exit-code`, `report`, `run`. Inputs reach shell only through `env:`, never interpolated into scripts.
3. **Self-test in Yardstick CI** (`.github/workflows/ci.yml`, new job `action`): `uses: ./` against the
   `support-bot` fixture suite and fake target, (a) a healthy run against a healthy baseline must pass, (b) a degraded
   run with `fail-on-gate: false` must report `passed=false` and exit code 1, (c) the summary and report file exist.
   Checkout pinned by full commit SHA.
4. **Footnote branch `yardstick-gate`**: `.github/workflows/yardstick.yml` (PRs and pushes to main, no secrets,
   `permissions: contents: read, pull-requests: write`), `.yardstick/` with two gate configs and two pinned baselines
   built from Footnote's committed files: (a) **product default** (dense + Sonnet θ′ 0.52) — no drop vs baseline on
   A+M answered-or-partial, U refusal, overall pass rate; (b) **judged cell** (hybrid + Sonnet θ on, Opus verdicts
   replayed, $0 cap) — the same regression rules plus the judge's sentence-support rule, which is report-only
   (κ 0.17 < 0.6, YS-05). Suite, verdicts and calibration are regenerated in CI from Footnote's committed golden
   set, answers file and grade sheets, so nothing is hand-copied. One PR, titled "Add Yardstick eval gate (demo, do
   not merge yet)", unmerged; the PR notes the `@phase-4` ref must become a tag or SHA after Yardstick's PR merges.
   Footnote `docs/decisions.md` and `NEXT.md` get a line each (its definition of done).
5. **README case study**: what the gate checks on Footnote, an excerpt of the real report from the Footnote PR run,
   the Phase 3 kappa result (19 match / 0 differ / 5 not reproducible, issue #4). Only numbers produced by runs in
   this session or committed outputs.
6. **Docs**: DECISIONS rows from D-42; README status.

## Tests that prove each acceptance item

| Acceptance item | Test |
|---|---|
| Comment poster | `tests/test_github_comment.py`: creates when none exists, updates the one with the marker (ignores other comments and other tags), paginates, skips without a PR, warns on 403, truncates long bodies, marker is in the body, token sent as a header, never printed |
| `action.yml` well-formed | `tests/test_action.py`: composite, every `uses:` pinned to a 40-hex SHA or a local path, no `${{ inputs.* }}` inside a `run:` script (inputs only via `env:`), required inputs documented, outputs declared |
| Action works end to end | CI job `action` (a)-(c) above |
| Footnote gate green | the `yardstick` workflow's check runs on the Footnote PR head commit conclude `success` |
| No regressions | YS-01..YS-05 and every Phase 1-3 test unchanged; examples regenerate byte-identically |

## Risks

- **Ref `@phase-4` is a moving branch.** Fine for an unmerged demo; after merge it must be a tag or SHA.
- **Fork PRs get a read-only token**, so the comment step only warns there; the job summary still has the report.
- **The baseline is the committed output itself**, so today's run shows Δ 0. The gate bites when Footnote commits a
  new answers file for the same cell (the workflow gates the newest one by file name) or changes `golden.json`
  (suite hash differs → YS-03 fails the gate).
