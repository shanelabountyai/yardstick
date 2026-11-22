# PRD-D: README first read, LICENSE and docs drift

Review item 3. Decisions 6 (a) and 7 (b).

## Problem

The README is the first thing a hiring manager reads. It has no prerequisites or clone line, never says what
the quick start should print, contains one placeholder command that fails when pasted
(`uv run yardstick run ... --theta-prime 0.52`), has two gate commands that exit 1 without saying so (one of
them because of a missing baseline), documents exit codes only in passing, and its kappa step writes a
calibration file the next command does not use. `pyproject.toml` says MIT but there is no `LICENSE` file. The
README action inputs omit `run-path` and `github-token`, the "Gates" line omits `slice` and `judge`, and PRD §3
lists 8 scorers against 10.

## Decisions applied

- **6 (a):** MIT; add a `LICENSE` file matching `pyproject.toml`.
- **7 (b):** do the mechanical README fixes. For the status line and the jargon, **propose** wording in the PR
  body only; do not change Shane's voice lines (line 3, the tagline; line 5, the status line).

## Scope (mechanical only)

- `LICENSE`: MIT, copyright holder "Shane LaBounty" (from the GitHub account name; recorded as a D-row so
  Shane can correct it), year 2026.
- README:
  - a "Requirements" note (uv, which fetches Python 3.12; any `python3` for the fake target) and a
    `git clone` + `cd` line;
  - the quick-start gate output pasted under the block, produced by running it here, and one line on exit
    codes (0 ok / passed, 1 gate failed, 2 bad input or target failure);
  - the `--theta-prime` line written out in full with its own `-o`;
  - `# exit 1` comments, with the reason, on the Footnote and judged gate lines;
  - the judged gate line passes `--calibration runs/calibration.json`, so the kappa step's output is used;
  - action inputs list completed (`run-path`, `github-token`); "Gates" line names `slice` and `judge`
    (`kappa_floor`, `min_graded`, `calibrations`);
  - a link to `docs/DEMO.md`;
  - the case-study gate table re-quoted from the regenerated report wording (PRD-B, PRD-A).
- `--help`: an epilog with the exit codes on the top-level app and on `gate`.
- PRD §3: a note pointing at D-23/D-26 for `field-equals` and `label-rate`, and at the real gate keys.

## Out of scope

The `refusal` wording in the README case-study table (decision 5 is handled by a legend in reports, PRD-F),
and any rewrite of Shane's voice lines.

## Acceptance

- D1. `LICENSE` exists and is MIT; `pyproject.toml` still says MIT.
- D2. Every command in the README's quick start, Footnote and judge blocks runs as pasted (checked here by
  running them from a clean clone of the branch), with the documented exit code.
- D3. `yardstick --help` and `yardstick gate --help` show the exit codes.
- D4. README lines 3 and 5 are unchanged; proposed wording is in the PR body.
