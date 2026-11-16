# Footnote kappa reproduction (Yardstick Phase 3 gate)

Source: shanelabountyai/footnote @ 3c9b0c7. Inputs: `eval/grades.md`, `eval/grades-2.md`, and the Opus verdicts committed in the answers file of run `answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646`, replayed by Yardstick's `llm-judge` scorer (judge claude-opus-5-5, prompt hash `071689f33855`, 55 replayed calls, spend $0.000000 under a $0.000000 cap). Reference: the figures `npm run eval:kappa` printed, as recorded in Footnote's committed docs (`fixtures/footnote/kappa-sources.md`).

**19 match, 0 differ, 5 not reproducible.**

| Set | Judge | Figure | Footnote (doc) | Yardstick | Status | Note |
|---|---|---|---|---|---|---|
| sheet-1 | opus | n | n 20 | 20 | match | reference 20 |
| sheet-1 | opus | raw | raw agreement 90% | 90% | match | reference 90% |
| sheet-1 | opus | p_e | p_e 0.820 | 0.820 | match | reference 0.820 |
| sheet-1 | opus | kappa | κ 0.44 | 0.44 | match | reference 0.44 |
| sheet-1 | opus | disagree | S-01, S-14 | S-01, S-14 | match | reference S-01, S-14 |
| sheet-1 | opus | human_counts | 18 supported, 2 partial (S-01, S-11), 0 unsupported | 18 supported, 2 partial, 0 unsupported | match | reference 18 supported, 2 partial, 0 unsupported |
| sheet-2 | opus | n | n 20 | 20 | match | reference 20 |
| sheet-2 | opus | raw | raw 75% | 75% | match | reference 75% |
| sheet-2 | opus | p_e | p_e 0.750 | 0.750 | match | reference 0.750 |
| sheet-2 | opus | kappa | κ 0.00 | 0.00 | match | reference 0.00 |
| sheet-2 | opus | misses | 5 of 20 | 5 | match | reference 5 |
| sheet-2 | opus | disagree | S-22, S-23, S-31, S-33, S-39 | S-22, S-23, S-31, S-33, S-39 | match | reference S-22, S-23, S-31, S-33, S-39 |
| pooled | opus | n | n 40 | 40 | match | reference 40 |
| pooled | opus | raw | raw 83% | 83% | match | reference 83% |
| pooled | opus | p_e | p_e 0.790 | 0.790 | match | reference 0.790 |
| pooled | opus | kappa | κ 0.17 | 0.17 | match | reference 0.17 |
| pooled | opus | kappa | κ 0.17 | 0.17 | match | reference 0.17 |
| pooled | opus | n | n 40 | 40 | match | reference 40 |
| pooled | opus | raw | raw agreement 83% | 83% | match | reference 83% |
| sheet-1 | sonnet | n | n 15 | — | not reproducible | needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them |
| sheet-1 | sonnet | raw | raw 87% | — | not reproducible | needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them |
| sheet-1 | sonnet | p_e | p_e 0.876 | — | not reproducible | needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them |
| sheet-1 | sonnet | kappa | κ −0.07 | — | not reproducible | needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them |
| sheet-1 | sonnet | disagree | S-11, S-14 | — | not reproducible | needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them |

## As `eval:kappa` prints it (Opus), recomputed by Yardstick

```text
sheet 1 (enriched, Claude-assisted, D-39) · opus · answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646
  n 20 (0 without a usable verdict)  raw agreement 90%  p_e 0.820  κ 0.44  target ≥ 0.7
  Shane s18/p2/u0  judge s18/p2/u0
  disagree S-01: Shane partial, judge supported
  disagree S-14: Shane supported, judge partial

sheet 2 (unassisted, D-41) · opus · answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646
  n 20 (0 without a usable verdict)  raw agreement 75%  p_e 0.750  κ 0.00  target ≥ 0.7
  Shane s15/p3/u2  judge s20/p0/u0
  disagree S-22: Shane partial, judge supported
  disagree S-23: Shane unsupported, judge supported
  disagree S-31: Shane unsupported, judge supported
  disagree S-33: Shane partial, judge supported
  disagree S-39: Shane partial, judge supported

pooled · opus · answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646
  n 40 (0 without a usable verdict)  raw agreement 83%  p_e 0.790  κ 0.17  target ≥ 0.7
  Shane s33/p5/u2  judge s38/p2/u0
  disagree S-01: Shane partial, judge supported
  disagree S-14: Shane supported, judge partial
  disagree S-22: Shane partial, judge supported
  disagree S-23: Shane unsupported, judge supported
  disagree S-31: Shane unsupported, judge supported
  disagree S-33: Shane partial, judge supported
  disagree S-39: Shane partial, judge supported

```

Replayed support rate on A+M+V: 49/51 (Phase 2's `label-rate` gives the same 49/51).
