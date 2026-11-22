# NEXT: Yardstick

## 2026-11-22: review fixes PRD-A to PRD-I (unattended run, branch `review-fixes/2026-11-21`)

Shane accepted all ten review decisions on 2026-11-21. This run wrote the nine PRDs (`docs/prds/`) and built
them in the order A, B, C, D, E, G, H, F, I, one concern per commit, on one branch cut from `main` at
`3bf6912`. One draft pull request, "Yardstick: review fixes PRD-A to I". Nothing merged, nothing deployed, no
live model call, no API key.

### Built, per PRD

| PRD | What changed | Evidence |
|---|---|---|
| A | Rate `n_items` counts only items that contributed (YS-02). `label-rate` can be `judge: true`, so YS-05 applies; `rate:support` in `fixtures/gates/footnote.yaml` is report-only (κ 0.17 < 0.6). `judge.min_graded`, default 30 | `tests/invariants/test_ys02_rates.py`, `test_ys05_label_rate.py`; D-79, D-80 |
| B | Gate checks read value first: `58.3% (floor 85.0%); dropped 41.7 pt (max 2.0 pt)`, one formatter for terminal and reports. Item-change bullets split; no mid-word breaks | `tests/test_gate_text.py`; D-81 |
| C | `report --gate` finds the pinned baseline; missing baseline names the path and `baseline pin` (still exit 1); pin says what it replaced; no name collisions | `tests/test_baseline.py`; D-82, D-83 |
| D | MIT `LICENSE`; README mechanical fixes; exit codes in `--help` | D-84, D-85 |
| E | Bad input is exit 2 with one line; gate-file thresholds validated; http input hardening | `tests/test_bad_input.py`, `test_http_bad_input.py`; D-86 |
| G | Markdown escaping of free text and identifiers; scorer keys must be gateable | `tests/test_markdown_escaping.py`; D-87 |
| H | Items with only report-only scorers are "not scored" and left out of pass rate; no committed number moved | `tests/test_not_scored.py`; D-88 |
| F | Why-first reports, a Key for scorers and slices, `kappa.md`/`reproduction.md` de-duplicated (19/0/5 and 74/0/49 unchanged) | `tests/test_first_reader.py`; D-89 |
| I | HTML charts as HTML/CSS rows; named focusable table regions; print and focus styles | `tests/test_html_report.py` (updated); D-90 |

### Gate results (sandbox, 2026-11-22, uv 0.11.32, CPython 3.12.3)

| Step | Exit | Result |
|---|---|---|
| `uv sync --locked` | 0 | ok |
| `uv run ruff check .` | 0 | `All checks passed!` |
| `uv run ruff format --check .` | 0 | `121 files already formatted` |
| `uv run mypy` | 0 | `Success: no issues found in 82 source files` |
| `uv run pytest` | 0 | `403 passed` (332 on `main`; 400 before the PR #8 review fixes, D-91) |
| `bash examples/make-example.sh && git diff --exit-code examples/` | 0, 0 | no difference after the committed regeneration |

CI on the pull request decides; its conclusions are in the pull request body.

README commands: the 14 commands of the quick start, Footnote and judge blocks were run from a fresh clone of
the branch; every exit code matched the README (11 exit 0, 3 exit 1 as annotated) and the tree stayed clean.

### D-rows added

D-79 to D-91 in `docs/DECISIONS.md` (and D-30's wording updated for decision 8).

### Not verified

- Anything on Shane's Mac; the HTML report in a desktop browser, Firefox or Safari (headless Chromium only:
  axe-core 4.10.2, 0 violations at 320 and 1280 px, light and dark).
- Markdown as GitHub renders it (the `<br>` in gate cells, `<details>` around "Rates by slice", escaped text).
- Footnote's own workflow against this branch (outside this run's access).
- The live judge and the `http` target against a real service (unchanged: never run).

### You

- You: review the draft pull request and merge it or ask for changes. Claude does not merge.
- You: in Footnote, re-pin the two baselines (D-46) when its workflow moves to a Yardstick ref with this
  change: the `footnote-golden` and `footnote-golden-judged` suite hashes moved (D-79), so the gate will exit 2
  with "suite hash differs" until then.
- Done 2026-11-22: `LICENSE` holder is Lab Intelligence, LLC (Shane, D-92).
- You: decide on the proposed README status line and jargon wording in the pull request body (README lines 3
  and 5 were not changed).
- You: open `examples/footnote/report.html` in your browser in light and dark mode, and on a phone.
- You: items 16 to 21 of the review stay "Later"; item 22 stays "Do not do" (D-43 confirmed).

## Earlier: closeout (2026-11-20)

Last updated 2026-11-20 by the unattended closeout run (the one retry of the run scheduled for 2026-11-19; it
found no earlier branch or pull request and did the whole run). Branch `closeout/2026-11-19`, docs only.

## Status

Phases 1 to 5 are merged to `main` (head `94949eb`). Yardstick is a command-line tool: nothing is hosted and
nothing is deployed. The closeout pack and a five-lens review are on the closeout branch in one draft pull
request, waiting for Shane's review. No source, test, fixture, action or example was changed.

## What is done

| When | What | Where |
|---|---|---|
| 2026-11-14 | Phase 1 merged: core, `command` target | PR #1, `cb0f511` |
| 2026-11-14 | Phase 2 merged: `results-file` target, Footnote mapping, HTML report | PR #2, `93738b2` |
| 2026-11-16 | Phase 3 merged: `llm-judge`, grades, kappa, YS-05 | PR #3, `01fe73f` |
| 2026-11-16 | Phase 4 merged: composite action, README case study | PR #5, `df298b7` |
| 2026-11-19 | Phase 5 merged: `http` target | PR #6, `94949eb` |
| 2026-11-20 | Closeout: README commands verified from a fresh clone | `docs/RELEASE_NOTES.md` |
| 2026-11-20 | Demo script | `docs/DEMO.md` |
| 2026-11-20 | Exec brief published (private Claude Docs document) | link in `docs/RELEASE_NOTES.md` |
| 2026-11-20 | Two LinkedIn drafts | `docs/LINKEDIN_DRAFTS.md` |
| 2026-11-20 | Cost review | `docs/RELEASE_NOTES.md`, `docs/DECISIONS.md` D-73 |
| 2026-11-20 | Five-lens review, report only: 71 findings, 22 work items | `docs/reviews/FIVE-LENS-2026-11-19.md` |

Merge dates are the merge commits' dates in Central time.

## What was verified, and how

- **README commands:** 18 of 19 ran as documented from a fresh clone of `94949eb` in a cloud sandbox (10 of 11
  in the quick start and Footnote sections). The one that did not is the placeholder line
  `uv run yardstick run ... --theta-prime 0.52`. Full table in `docs/RELEASE_NOTES.md`.
- **Demo script:** every command in `docs/DEMO.md` was run in order in a second fresh clone. Two steps are only
  partly verified (the HTML report in a desktop browser; the GitHub Actions page in a browser).
- **Reproduction counts:** `74 match, 0 differ, 49 not reproducible` and `19 match, 0 differ, 5 not
  reproducible` were printed again by the commands in this session and match the committed examples.
- **CI on `main`:** run 32 on `94949eb` is `success` for both jobs (`check`, `action`), read from the GitHub API
  on 2026-11-20.
- **Gate on the closeout branch (sandbox, 2026-11-20):** see "Gate results" below.

Not verified: anything on Shane's Mac; the look of the HTML report in a desktop browser; the rendered job summary
and PR comment; footnote#5 and the Footnote repo (outside this run's access); a live LLM judge; the `http` target
against a real service.

## Gate results

Run in the sandbox on the closeout branch on 2026-11-20 (uv 0.11.32, CPython 3.12.3), after the last docs
change. CI on the pull request is
the gate that decides.

| Step | Exit | Result |
|---|---|---|
| `uv sync --locked` | 0 | ok |
| `uv run ruff check .` | 0 | `All checks passed!` |
| `uv run ruff format --check .` | 0 | `102 files already formatted` (92 on `main`; the 10 more are this branch's markdown files) |
| `uv run mypy` | 0 | `Success: no issues found in 73 source files` |
| `uv run pytest` | 0 | `332 passed` |
| `bash examples/make-example.sh` | 0 | ran to the end (its last line is `gate FAILED`, which the script expects) |
| `git diff --exit-code examples/` | 0 | no difference |

## What is open

1. Shane's review of the closeout pull request (draft, not merged).
2. The five-lens review (`docs/reviews/FIVE-LENS-2026-11-19.md`). Verdict: **ship after the top items**. 71
   findings as the lenses returned them (1 Blocker, 24 Major, 46 Minor), grouped into 22 work items: 6 Do now,
   9 Do next, 6 Later, 1 Do not do. None was fixed. PRDs are written only after Shane approves the list. The
   six Do now items:
   1. Rate gates count items that contributed nothing, so `min_items` can pass on a sample of one (YS-02). The
      one Blocker. Reproduced at library level only; it is not on the README or demo path.
   2. Gate check wording: `floor: 0.583333 >= 0.85` under `FAIL` reads as a false statement, in the terminal and
      in the report's "Checks" cell.
   3. README first read: the placeholder command, gate commands that exit 1 without saying so, no
      prerequisites, no `LICENSE` file, small docs drift.
   4. Judge verdicts gate with no kappa check when they arrive through `label-rate` (`rate:support` in
      `fixtures/gates/footnote.yaml`), which goes around YS-05; and a 3-unit calibration is enough to gate.
   5. Baselines: `report --gate` ignores the pinned baseline and prints "Gate: FAILED" where `gate` passes; a
      missing baseline gives no hint; `baseline pin` overwrites silently.
   6. Two visible defects in the committed example reports: two bullets joined on one line in
      `examples/footnote/report.md`, and rule names broken mid-word in the HTML report.
3. README gaps recorded in `docs/RELEASE_NOTES.md` ("Known gaps"): the placeholder command, no link to the demo
   script, no `LICENSE` file although `pyproject.toml` says MIT.
4. Issue #4 (open): the last 5 Footnote kappa figures need the Sonnet re-judge verdicts committed in Footnote.
5. A live LLM judge has never been run (README, D-34, D-45).
6. The `http` target has only been run against the local fixture server (README, D-68).
7. footnote#5 (the gate branch in Footnote) is described in the README as unmerged. Its current state was not
   read in this run.

## Shane's hand steps

- You: read the draft pull request "Yardstick: closeout, demo pack and five-lens review (docs only)" and merge
  it or ask for changes. Claude does not merge.
- You: run `docs/DEMO.md` once on your Mac from a clean clone, with a second terminal for the fixture server.
  Change any step marked "verified in this run" that behaves differently there.
- You: open `examples/footnote/report.html` and the generated `runs/report.html` in your browser, in light and
  dark mode, and check they look the way you want a hiring manager to see them.
- You: open the exec brief (link in `docs/RELEASE_NOTES.md`), edit the wording, and share it only when you are
  ready. It is private until you do.
- You: read the two drafts in `docs/LINKEDIN_DRAFTS.md` out loud, confirm or cut the two lines flagged as your
  own experience, and add the ones you keep to the Lab Intelligence Ledger. Claude did not touch the Ledger.
- You: work through the 10 "Decisions needed from Shane" in `docs/reviews/FIVE-LENS-2026-11-19.md`, one at a
  time, then say which work items should become PRDs. Start with the six Do now items.
- You: before a demo, know the answer to "why does `rate:support` gate when the judge is not calibrated?"
  (Do now item 4). Until it is fixed, the honest answer is that it is a known gap, written up in the review.
- You: decide on a license. If MIT is right, add a `LICENSE` file so GitHub shows it.
- You: decide whether the README should link to `docs/DEMO.md` and whether the placeholder `--theta-prime` line
  should be written out in full. The README's wording is yours; it was not edited.
- You: if you want the live judge demonstrated, add `ANTHROPIC_API_KEY` yourself and run it with prices and a
  budget (README, "Live judge"). No key was used or requested in this run.
- You: check the GitHub Actions usage page for the account if you want a billed figure; it was not readable
  from this run.

## Test data and leftovers

Nothing was created in any external system except the branch, the draft pull request (#7) and the exec brief
document. The fresh clones and their `runs/` and `.yardstick/` folders lived only in the sandbox. Network use
by the review beyond GitHub and package installs is listed in `docs/DECISIONS.md` D-78.
