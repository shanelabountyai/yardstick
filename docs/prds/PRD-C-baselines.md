# PRD-C: Baseline lookup and messages

Review item 5. Decision 4 (a).

## Problem

1. `yardstick report --gate` never looks up the pinned baseline, so the same run and gate file print
   `gate PASSED` from `gate` and `**Gate: FAILED**` (`max_drop: no baseline`) from `report`.
2. A missing baseline prints `max_drop: no baseline` with no path and no next step.
3. `baseline pin` overwrites an existing baseline silently.
4. Baseline names collide: `日本`/`中文` both become `-__t.json`, `a b`/`a-b` share a file, and
   `a`+`b__c` equals `a__b`+`c`.
5. The README quick start leaves an untracked `.yardstick/` in the clone.

## Decision applied

**4 (a):** a missing baseline stays exit 1 (D-11, fail closed). Print the path searched and the
`baseline pin` command, and record in DECISIONS that it is intentional.

## Scope

- `report` gains `--baselines-dir` and uses the same lookup as `gate` (`_resolve_baseline`) when a gate is
  given and no `--baseline` is passed. Without `--gate`, `report` still compares only with an explicit
  `--baseline` (a report without a gate never needed one).
- When no baseline was found, `gate` and `report --gate` print to stderr:
  `note: no baseline at <path>; pin one with: yardstick baseline pin <run>`. The gate's `no baseline` check
  detail stays the same text (it is the verdict's reason, PRD-B).
- `baseline pin` prints `replaced <old run id>` when it overwrites a different run, `unchanged` when the run
  id is the same.
- Baseline file names: keep Unicode word characters, `.` and `-`; replace anything else with `-`; when the
  sanitised name differs from the raw name, or a name contains `__`, append `-` and the first 8 hex digits of
  `sha256(raw)`. Names that were already safe (the committed fixtures, the README and CI names) keep their
  current file name, so existing pins still resolve.
- `find` checks that the loaded run's `suite_name` and `target.name` match; otherwise exit 2 naming both.
- `.gitignore` ignores `/.yardstick/` in this repo only (D-04 still has target repos commit theirs).

## Out of scope

Any change to the fail-closed verdict (D-11 stays).

## Acceptance

- C1. After the quick start, `yardstick report runs/healthy.json --gate fixtures/gates/support-bot.yaml`
  prints `**Gate: PASSED**`, as `gate` does (test).
- C2. A never-pinned baseline prints the path and the `baseline pin` command and exits 1 (test).
- C3. Pinning over a different run prints `replaced <id>` (test).
- C4. The review's collision pairs give different paths; `support-bot`/`fake` keeps
  `support-bot__fake.json` (test).
- C5. A D-row records that a missing baseline is intentionally exit 1.
