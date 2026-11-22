# Yardstick report: footnote-golden

**Gate: FAILED**

- `rate:refusal[A+M]`: 86.4% (floor 90.0%)
- `pass_rate[U]`: 87.5% (floor 90.0%)

> Compared against a different target: `footnote-hybrid-sonnet-theta-on`. Each change is this target against that one, not a before and after.

## Summary

| Metric | Value | Baseline | Change |
|---|---|---|---|
| Pass rate | 90.2% | 68.3% | +22.0 pt |
| Mean score | 90.2% | 68.3% | +22.0 pt |
| Latency p50 | not reported | not reported | n/a |
| Latency p95 | not reported | not reported | n/a |
| Cost total | $0.451399 (run total reported by target) | $0.633310 | −$0.181911 |
| Cost per item | $0.011010 (run total reported by target) | $0.015447 | −$0.004437 |

## Key

- `out-of-scope`: hit = refused with code OUT\_OF\_SCOPE, on the item that expects it.
- `pre-call`: report-only. hit = refused before any model call (NO\_RELEVANT\_PASSAGE, D-28).
- `refusal`: hit = the expected outcome: answered or partial where the golden set expects an answer, refused where it expects a refusal. On A+M a hit means answered or partial; it is not a refusal rate.
- `refusal-code`: report-only. hit = refused with the refusal code the golden set expects (U items).
- `support`: report-only, judge-derived. Share of answer sentences Footnote's judge labelled supported (schema\_invalid left out); it gates only when that judge is calibrated (YS-05).

Slices:

- `A`: answerable (golden slice A): the expected outcome is an answer.
- `A+M`: A and M together: Footnote's scorecard row "Answered or partial (A, M)".
- `A+M+V`: A, M and V together: the slices the sentence-support rate is reported on.
- `M`: answerable (golden slice M): the expected outcome is an answer.
- `P`: golden slice P: answer-or-refusal cases asked under different caller roles (callerRole in the input).
- `U`: unanswerable (golden slice U): the expected outcome is a refusal.
- `V`: edition questions (golden slice V): the answer must label the edition it cites.

## Gate

| Rule | Result | Current | Baseline | Items | Checks |
|---|---|---|---|---|---|
| `rate:refusal[A+M]` | **FAIL** | 86.4% | 63.6% | 22 / min 8 | 86.4% (floor 90.0%) (FAIL)<br>rose 22.7 pt (max drop 2.0 pt) (ok) |
| `pass_rate[U]` | **FAIL** | 87.5% | 87.5% | 8 / min 8 | 87.5% (floor 90.0%) (FAIL) |
| `rate:support[A+M+V]` | report-only: fail | not reported | 96.1% | 0 / min 8 | 0 items (min 8) (FAIL)<br>not reported (FAIL)<br>report-only (YS-05): judge behind 'support' not reported by the target, kappa unknown |

## Slices

| Slice | Items | Pass rate | Mean score | Pass rate change |
|---|---|---|---|---|
| A | 14 | 85.7% | 85.7% | +14.3 pt |
| A+M | 22 | 86.4% | 86.4% | +22.7 pt |
| A+M+V | 28 | 89.3% | 89.3% | +32.1 pt |
| M | 8 | 87.5% | 87.5% | +37.5 pt |
| P | 5 | 100.0% | 100.0% | ±0.0 pt |
| U | 8 | 87.5% | 87.5% | ±0.0 pt |
| V | 6 | 100.0% | 100.0% | +66.7 pt |

## Rates

Per scorer: hits / total over the items it applied to. Report-only scorers never decide an item's pass.

| Scorer | Items | Rate | Baseline | Change |
|---|---|---|---|---|
| `out-of-scope` | 1 | 0.0% (0/1) | 0.0% | ±0.0 pt |
| `pre-call (report-only)` | 41 | 0.0% (0/41) | 43.9% | −43.9 pt |
| `refusal` | 40 | 92.5% (37/40) | 70.0% | +22.5 pt |
| `refusal-code (report-only)` | 7 | 0.0% (0/7) | 71.4% | −71.4 pt |
| `support (report-only)` | 0 | not reported | 96.1% | n/a |

<details><summary>Rates by slice (21 rows)</summary>

| Slice | Scorer | Items | Rate | Change |
|---|---|---|---|---|
| A | `pre-call (report-only)` | 14 | 0.0% (0/14) | −21.4 pt |
| A | `refusal` | 14 | 85.7% (12/14) | +14.3 pt |
| A | `support (report-only)` | 0 | not reported | n/a |
| A+M | `pre-call (report-only)` | 22 | 0.0% (0/22) | −27.3 pt |
| A+M | `refusal` | 22 | 86.4% (19/22) | +22.7 pt |
| A+M | `support (report-only)` | 0 | not reported | n/a |
| A+M+V | `pre-call (report-only)` | 28 | 0.0% (0/28) | −35.7 pt |
| A+M+V | `refusal` | 28 | 89.3% (25/28) | +32.1 pt |
| A+M+V | `support (report-only)` | 0 | not reported | n/a |
| M | `pre-call (report-only)` | 8 | 0.0% (0/8) | −37.5 pt |
| M | `refusal` | 8 | 87.5% (7/8) | +37.5 pt |
| M | `support (report-only)` | 0 | not reported | n/a |
| P | `pre-call (report-only)` | 5 | 0.0% (0/5) | −40.0 pt |
| P | `refusal` | 5 | 100.0% (5/5) | ±0.0 pt |
| U | `out-of-scope` | 1 | 0.0% (0/1) | ±0.0 pt |
| U | `pre-call (report-only)` | 8 | 0.0% (0/8) | −75.0 pt |
| U | `refusal` | 7 | 100.0% (7/7) | ±0.0 pt |
| U | `refusal-code (report-only)` | 7 | 0.0% (0/7) | −71.4 pt |
| V | `pre-call (report-only)` | 6 | 0.0% (0/6) | −66.7 pt |
| V | `refusal` | 6 | 100.0% (6/6) | +66.7 pt |
| V | `support (report-only)` | 0 | not reported | n/a |

</details>

## Run

| Field | Value |
|---|---|
| Run | `sha256:1cde8bbdfa25947b` |
| Suite | `footnote-golden` (`sha256:76beaa0f0f1d`) |
| Target | `footnote-dense-sonnet-theta-off` (results-file) |
| Model | claude-sonnet-5-5 |
| Prompt hash | not reported |
| Git SHA | not reported |
| Started | 2026-11-14T00:00:00Z |
| Items | 41 (0 target errors) |
| Baseline | `sha256:fb3406ee2e01bde2` (`footnote-hybrid-sonnet-theta-on`) |

## Item changes vs baseline

- Newly failing (1): `GA-12`
- Newly passing (10): `GA-02`, `GA-06`, `GA-09`, `GM-02`, `GM-05`, `GM-06`, `GV-02`, `GV-03`, `GV-05`, `GV-06`

## Failing items

| Item | Slices | Failed checks |
|---|---|---|
| `GA-11` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GA-12` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GM-08` | A+M, A+M+V, M | refusal: expected refusal=False, got refusal=True (via flag) |
| `GU-03` | U | out-of-scope: refusal\_code: expected "OUT\_OF\_SCOPE", got "INSUFFICIENT\_SUPPORT" |

<sub>Generated by Yardstick 0.1.0. Cost in USD; latency in integer ms; "not reported" means the target did not report it.</sub>
