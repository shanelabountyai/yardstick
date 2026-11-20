# Yardstick: release notes

## Closeout, 2026-11-19 (written 2026-11-20)

Yardstick (build-log #26) is a Python command-line eval harness. There is nothing hosted and nothing to deploy,
so "released" here means Phases 1 to 5 are merged to `main` (head `94949eb`, merged 2026-11-19). This closeout
changes documentation only.

It was written by the one retry of the unattended closeout run. The retry found no `closeout/2026-11-19` branch
and no open pull request, so it did the whole run.

### What is on main

| Phase | Scope | Pull request | Merge commit (date, Central) |
|---|---|---|---|
| 1 | Core: models, deterministic scorers, metrics, baselines, compare, gate, markdown report, `command` target | #1 | `cb0f511` (2026-11-14) |
| 2 | `results-file` target, Footnote mapping, scorecard reproduction, HTML report | #2 | `93738b2` (2026-11-14) |
| 3 | `llm-judge` with a budget cap, human grades, Cohen's kappa, YS-05 | #3 | `01fe73f` (2026-11-16) |
| 4 | GitHub composite action, Footnote gate branch, README case study | #5 | `df298b7` (2026-11-16) |
| 5 | `http` target | #6 | `94949eb` (2026-11-19) |

### Closeout documents

- **Exec brief** (for a non-technical reader; private Claude Docs document, visible to Shane until he shares
  it): <https://claude.ai/artifact/HZQpiKR4KZrZEQPZzHuq9r>
- **Demo script:** [`docs/DEMO.md`](DEMO.md)
- **LinkedIn drafts (two, not posted, not in the Ledger):** [`docs/LINKEDIN_DRAFTS.md`](LINKEDIN_DRAFTS.md)
- **Five-lens review** (report only; verdict "ship after the top items"; 71 findings: 1 Blocker, 24 Major,
  46 Minor; 22 work items, 6 of them Do now): [`docs/reviews/FIVE-LENS-2026-11-19.md`](reviews/FIVE-LENS-2026-11-19.md)
- **Status and owner steps:** [`NEXT.md`](../NEXT.md)
- **Decisions for this run:** `docs/DECISIONS.md`, D-69 to D-78

### Verification in place of a live check (2026-11-20)

Method: a fresh `git clone` of `main` at `94949eb` in a cloud sandbox (Linux, uv 0.11.32, CPython 3.12.3 picked
by uv), each README command pasted exactly as written, in README order. Nothing was fixed. Every command also
printed one uv warning about a sandbox environment variable (`UV_NATIVE_TLS` is deprecated), which is the
sandbox's, not the repo's.

**Result: 18 of 19 README commands ran as documented.** In the two sections the run brief named (quick start and
Footnote): 10 of 11.

| # | README section | Command (shortened) | Exit | Matches the README? |
|---|---|---|---|---|
| 1 | Quick start | `uv sync` | 0 | yes |
| 2 | Quick start | `yardstick run … fake_target.py … -o runs/healthy.json` | 0 | yes: `12/12 passed` |
| 3 | Quick start | `yardstick baseline pin runs/healthy.json` | 0 | yes: wrote `.yardstick/baselines/support-bot__fake.json`, as the comment says |
| 4 | Quick start | `yardstick run … --degrade … -o runs/degraded.json` | 0 | yes: `7/12 passed` |
| 5 | Quick start | `yardstick gate runs/degraded.json … --report runs/report.md` | 1 | yes: the comment says `# exit 1` |
| 6 | Quick start | `yardstick compare runs/healthy.json runs/degraded.json` | 0 | yes |
| 7 | Footnote | `yardstick footnote suite … -o fixtures/footnote/suite.yaml` | 0 | yes: the regenerated file is byte-identical (`git status` clean) |
| 8 | Footnote | `yardstick run … --mapping footnote … -o runs/dense-sonnet.json` | 0 | yes: `37/41 passed` |
| 9 | Footnote | `yardstick gate runs/dense-sonnet.json -c fixtures/gates/footnote.yaml --html-report runs/report.html` | 1 | yes, with a note: the README does not say this gate fails. It does (D-32), and with no baseline pinned for `dense-sonnet` it also prints `max_drop: no baseline` |
| 10 | Footnote | `yardstick run ... --theta-prime 0.52` | 2 | **no**: the `...` is a placeholder, so the line fails with `Missing option '--suite'`. With the options of command 8 filled in it exits 0 (`32/41 passed`) |
| 11 | Footnote | `yardstick footnote reproduce …` | 0 | yes: `74 match, 0 differ, 49 not reproducible`. The "Source:" line differs from the committed example because `examples/make-example.sh` passes `--source` |
| 12 | Judges | `yardstick run … --judge replay:… --judge-budget-usd 0 -o runs/judged.json` | 0 | yes: 55 calls, `spent $0.000000 of $0.000000` |
| 13 | Judges | `yardstick kappa --grades … --run runs/judged.json --key judge -o runs/calibration.json` | 0 | yes: κ 0.44, 0.00, pooled 0.17 |
| 14 | Judges | `yardstick gate runs/judged.json -c fixtures/gates/footnote-judged.yaml` | 1 | yes: judge rule `report-only (YS-05): judge kappa 0.17 (n 40) < floor 0.6`. The README does not say the gate exits 1 |
| 15 | Judges | `yardstick footnote kappa …` | 0 | yes: `19 match, 0 differ, 5 not reproducible` |
| 16 | HTTP target | `python3 fixtures/targets/fake_http_target.py --port 8808` | running | yes: `listening on http://127.0.0.1:8808/answer` |
| 17 | HTTP target | `yardstick run … --http fixtures/targets/fake-http.yaml … -o runs/http.json` | 0 | yes: `12/12 passed` |
| 18 | HTTP target | `yardstick baseline pin runs/http.json` | 0 | yes |
| 19 | HTTP target | `yardstick gate runs/http.json -c fixtures/gates/support-bot.yaml` | 0 | yes: `gate PASSED` |

Also checked, beyond the README's own commands:

- With the fixture server stopped, the `--http` run exits 2 with
  `error: http target: item 'faq-reset-password': connection failed (ConnectionRefusedError)` and writes no run
  file, as the README's "Failures" paragraph says.
- The README's Development line (`ruff check`, `ruff format --check`, `mypy`, `pytest`) exits 0: see the gate
  results in `NEXT.md`.
- After the quick start, `git status` shows `.yardstick/` as untracked. `runs/` is git-ignored and `.yardstick/`
  is not. Recorded, not changed.
- **CI status of `main`'s head commit** `94949eb`, as the GitHub API showed it on 2026-11-20: workflow `ci`, run
  32, conclusion `success`; job `check` success, job `action` success
  (<https://github.com/shanelabountyai/yardstick/actions/runs/44636574148>).

Not verified in this run: anything on Shane's Mac; how the HTML report looks in a desktop browser (it was loaded
in headless Chromium only); the GitHub job summary and PR comment as rendered; the Footnote pull request
(footnote#5) and anything else in the Footnote repo, which this run could not read; a live LLM judge; the HTTP
target against any real service.

### Cost review (2026-11-20, decision D-73)

Measured figures only. Anything that could not be read says "not read".

| Billable piece | What the files say | Measured | Not read |
|---|---|---|---|
| Hosting | None. A CLI; no server, no database (PRD §5) | nothing to measure | n/a |
| GitHub Actions minutes | `.github/workflows/ci.yml`: two jobs (`check`, `action`) on `ubuntu-latest`, on every push to `main`, `kickoff`, `phase-*` and on every pull request | 32 workflow runs from 2026-11-14 to 2026-11-19, 901 seconds of wall-clock run time in total (14 to 44 s per run), 29 succeeded and 3 failed; the repo is public (GitHub API, read 2026-11-20) | the account's Actions usage and bill; per-job billed minutes |
| LLM judge spend, in this repo | No workflow reads a secret or sets `ANTHROPIC_API_KEY` (`ci.yml`, `action.yml`); the judge in CI and in the examples is a replay | `spent $0.000000 of $0.000000` printed by the replay run in this session | n/a |
| LLM judge spend, if run live | `--judge anthropic:MODEL` needs `ANTHROPIC_API_KEY`, prices given on the command line and a required `--judge-budget-usd` cap (D-34, D-37). Never run live | none: no live call has been made from this repo according to the README and D-34 | the Anthropic account's usage |
| HTTP target | Sends one request per item to a configured URL (D-59). Only run against 127.0.0.1 | none | whatever a real endpoint would charge |
| Footnote's CI using the action | README: one job, no model call, no secret | not measured | the Footnote repo was outside this run's access |
| Claude sessions that built the repo | Not recorded in the repo | none | not read |

New billable pieces added by Phase 5: none measured. The `http` target can reach a paid endpoint if someone
points it at one; nothing in this repo does.

### Known gaps a reader may notice

Recorded here, not fixed (this closeout is docs only). The ranked list is in the five-lens review.

- The README was not edited in this run: it does not yet link to `docs/DEMO.md` or `NEXT.md`.
- README command 10 above is a placeholder line.
- There is no `LICENSE` file. `pyproject.toml` says `license = { text = "MIT" }`, and GitHub reports no license
  for the repo.
- Issue #4 is open: the last 5 Footnote kappa figures cannot be reproduced until Footnote commits its Sonnet
  re-judge verdicts.
