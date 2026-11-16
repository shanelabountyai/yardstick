# Yardstick report — footnote-golden-judged

**Gate: FAILED**

| | |
|---|---|
| Run | `sha256:64fa2324dc9fde69` |
| Suite | `footnote-golden-judged` (`sha256:0da245413c97`) |
| Target | `footnote-hybrid-sonnet-theta-on` (results-file) |
| Model | claude-sonnet-5-5 |
| Prompt hash | not reported |
| Git SHA | not reported |
| Started | 2026-11-16T00:00:00Z |
| Items | 41 (0 target errors) |

## Summary

| Metric | Value |
|---|---|
| Pass rate | 68.3% |
| Mean score | 68.3% |
| Latency p50 | not reported |
| Latency p95 | not reported |
| Cost total | $0.633310 (run total reported by target) |
| Cost per item | $0.015447 (run total reported by target) |

## Rates

Per scorer: hits / total over the items it applied to. Report-only scorers never decide an item's pass.

| Scorer | Items | Rate |
|---|---|---|
| `judge (report-only)` | 19 | 96.4% (53/55) |
| `out-of-scope` | 1 | 0.0% (0/1) |
| `pre-call (report-only)` | 41 | 43.9% (18/41) |
| `refusal` | 40 | 70.0% (28/40) |
| `refusal-code (report-only)` | 7 | 71.4% (5/7) |
| `support (report-only)` | 16 | 96.1% (49/51) |

## Judges

LLM-judge scores are report-only per item; a gate rule on a judge rate gates only if the judge's kappa clears the floor (YS-05).

| Scorer | Judge | Prompt hash | Units judged | No valid label | Not judged (budget) | Calls | Spend / cap (run) |
|---|---|---|---|---|---|---|---|
| `judge` | claude-opus-5-5 (replay verdicts-opus-1646.json (shanelabountyai/footnote @ 3c9b0c7: eval/results/answers-hybrid-claude-sonnet-5-5-theta-on-cd1252c6a407-2026-10-23T1646.json)) | `071689f33855` | 55 | 0 | 0 | 55 | $0.000000 / $0.000000 |

## Slices

| Slice | Items | Pass rate | Mean score |
|---|---|---|---|
| A | 14 | 71.4% | 71.4% |
| A+M | 22 | 63.6% | 63.6% |
| A+M+V | 28 | 57.1% | 57.1% |
| M | 8 | 50.0% | 50.0% |
| P | 5 | 100.0% | 100.0% |
| U | 8 | 87.5% | 87.5% |
| V | 6 | 33.3% | 33.3% |

### Rates by slice

| Slice | Scorer | Items | Rate |
|---|---|---|---|
| A | `judge (report-only)` | 10 | 96.9% (31/32) |
| A | `pre-call (report-only)` | 14 | 21.4% (3/14) |
| A | `refusal` | 14 | 71.4% (10/14) |
| A | `support (report-only)` | 10 | 96.9% (31/32) |
| A+M | `judge (report-only)` | 14 | 95.7% (45/47) |
| A+M | `pre-call (report-only)` | 22 | 27.3% (6/22) |
| A+M | `refusal` | 22 | 63.6% (14/22) |
| A+M | `support (report-only)` | 14 | 95.7% (45/47) |
| A+M+V | `judge (report-only)` | 16 | 96.1% (49/51) |
| A+M+V | `pre-call (report-only)` | 28 | 35.7% (10/28) |
| A+M+V | `refusal` | 28 | 57.1% (16/28) |
| A+M+V | `support (report-only)` | 16 | 96.1% (49/51) |
| M | `judge (report-only)` | 4 | 93.3% (14/15) |
| M | `pre-call (report-only)` | 8 | 37.5% (3/8) |
| M | `refusal` | 8 | 50.0% (4/8) |
| M | `support (report-only)` | 4 | 93.3% (14/15) |
| P | `judge (report-only)` | 3 | 100.0% (4/4) |
| P | `pre-call (report-only)` | 5 | 40.0% (2/5) |
| P | `refusal` | 5 | 100.0% (5/5) |
| U | `out-of-scope` | 1 | 0.0% (0/1) |
| U | `pre-call (report-only)` | 8 | 75.0% (6/8) |
| U | `refusal` | 7 | 100.0% (7/7) |
| U | `refusal-code (report-only)` | 7 | 71.4% (5/7) |
| V | `judge (report-only)` | 2 | 100.0% (4/4) |
| V | `pre-call (report-only)` | 6 | 66.7% (4/6) |
| V | `refusal` | 6 | 33.3% (2/6) |
| V | `support (report-only)` | 2 | 100.0% (4/4) |

## Gate

| Rule | Current | Baseline | Items | Checks | Result |
|---|---|---|---|---|---|
| `rate:refusal[A+M]` | 63.6% | no baseline | 22 / min 8 | min_items: 22 item(s), need >= 8 (ok); floor: 63.6% >= 90.0% (FAIL) | **FAIL** |
| `pass_rate[U]` | 87.5% | no baseline | 8 / min 8 | min_items: 8 item(s), need >= 8 (ok); floor: 87.5% >= 90.0% (FAIL) | **FAIL** |
| `rate:judge[A+M+V]` | 96.1% | no baseline | 16 / min 8 | min_items: 16 item(s), need >= 8 (ok); floor: 96.1% >= 90.0% (ok); report-only (YS-05): judge kappa 0.17 (n 40) < floor 0.6 | report-only: pass |

## Failing items

| Item | Slices | Failed checks |
|---|---|---|
| `GA-02` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GA-06` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GA-09` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GA-11` | A, A+M, A+M+V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GM-02` | A+M, A+M+V, M | refusal: expected refusal=False, got refusal=True (via flag) |
| `GM-05` | A+M, A+M+V, M | refusal: expected refusal=False, got refusal=True (via flag) |
| `GM-06` | A+M, A+M+V, M | refusal: expected refusal=False, got refusal=True (via flag) |
| `GM-08` | A+M, A+M+V, M | refusal: expected refusal=False, got refusal=True (via flag) |
| `GU-03` | U | out-of-scope: refusal_code: expected "OUT_OF_SCOPE", got "NO_RELEVANT_PASSAGE" |
| `GV-02` | A+M+V, V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GV-03` | A+M+V, V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GV-05` | A+M+V, V | refusal: expected refusal=False, got refusal=True (via flag) |
| `GV-06` | A+M+V, V | refusal: expected refusal=False, got refusal=True (via flag) |

<sub>Generated by Yardstick 0.1.0. Cost in USD; latency in integer ms; "not reported" means the target did not report it.</sub>
