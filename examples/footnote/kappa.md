# Footnote kappa reproduction (Yardstick Phase 3 gate)

Source: shanelabountyai/footnote @ 3c9b0c7. Inputs: `eval/grades.md`, `eval/grades-2.md`, and the Opus verdicts committed in the answers file of run `answers:hybrid:claude-sonnet-5-5:theta-on:2026-10-23T1646`, replayed by Yardstick's `llm-judge` scorer (judge claude-opus-5-5, prompt hash `071689f33855`, 55 replayed calls, spend $0.000000 under a $0.000000 cap). Reference: the figures `npm run eval:kappa` printed, as recorded in Footnote's committed docs (`fixtures/footnote/kappa-sources.md`).

**19 match, 0 differ, 5 not reproducible.**

Each row is one figure as one quoted line of Footnote's docs records it (column Quote; the quotes
are listed under the table). A figure recorded by two docs is checked against each, which is why
the pooled Opus n, raw agreement and kappa appear twice, once per quote.

| Quote | Set | Judge | Figure | Footnote (doc) | Yardstick | Status | Note |
|---|---|---|---|---|---|---|---|
| Q1 | sheet-1 | opus | n | n 20 | 20 | match |  |
| Q1 | sheet-1 | opus | raw | raw agreement 90% | 90% | match |  |
| Q1 | sheet-1 | opus | p_e | p_e 0.820 | 0.820 | match |  |
| Q1 | sheet-1 | opus | kappa | κ 0.44 | 0.44 | match |  |
| Q1 | sheet-1 | opus | disagree | S-01, S-14 | S-01, S-14 | match |  |
| Q2 | sheet-1 | opus | human_counts | 18 supported, 2 partial (S-01, S-11), 0 unsupported | 18 supported, 2 partial, 0 unsupported | match |  |
| Q3 | sheet-2 | opus | n | n 20 | 20 | match |  |
| Q3 | sheet-2 | opus | raw | raw 75% | 75% | match |  |
| Q3 | sheet-2 | opus | p_e | p_e 0.750 | 0.750 | match |  |
| Q3 | sheet-2 | opus | kappa | κ 0.00 | 0.00 | match |  |
| Q4 | sheet-2 | opus | misses | 5 of 20 | 5 | match |  |
| Q4 | sheet-2 | opus | disagree | S-22, S-23, S-31, S-33, S-39 | S-22, S-23, S-31, S-33, S-39 | match |  |
| Q5 | pooled | opus | n | n 40 | 40 | match |  |
| Q5 | pooled | opus | raw | raw 83% | 83% | match |  |
| Q5 | pooled | opus | p_e | p_e 0.790 | 0.790 | match |  |
| Q5 | pooled | opus | kappa | κ 0.17 | 0.17 | match |  |
| Q6 | pooled | opus | kappa | κ 0.17 | 0.17 | match |  |
| Q6 | pooled | opus | n | n 40 | 40 | match |  |
| Q6 | pooled | opus | raw | raw agreement 83% | 83% | match |  |
| Q7 | sheet-1 | sonnet | n | n 15 | — | not reproducible | [a] |
| Q7 | sheet-1 | sonnet | raw | raw 87% | — | not reproducible | [a] |
| Q7 | sheet-1 | sonnet | p_e | p_e 0.876 | — | not reproducible | [a] |
| Q7 | sheet-1 | sonnet | kappa | κ −0.07 | — | not reproducible | [a] |
| Q7 | sheet-1 | sonnet | disagree | S-11, S-14 | — | not reproducible | [a] |

[a] needs the Sonnet re-judge verdicts (SentenceJudgment rows of run `rejudge:claude-sonnet-5-5:2026-10-23T1646`); they live only in Footnote's database and no committed file holds them

Quotes (verbatim in `fixtures/footnote/kappa-sources.md`):

- Q1: **Opus: κ 0.44, n 20, raw agreement 90%, p_e 0.820.** It disagrees on S-01 (Shane partial, judge supported) and S-14 (Shane supported, judge partial).
- Q2: **18 supported, 2 partial (S-01, S-11), 0 unsupported**
- Q3: **Sheet 2 (unassisted, Opus): n 20, raw 75%, p_e 0.750, κ 0.00.**
- Q4: **miss rate: 5 of 20 judge-`supported` sentences Shane would not support** (S-23, S-31 unsupported; S-22, S-33, S-39 partial)
- Q5: **Pooled (Opus): n 40, raw 83%, p_e 0.790, κ 0.17**
- Q6: κ 0.17 n 40, raw agreement 83%
- Q7: **Sonnet: κ −0.07, n 15, raw 87%, p_e 0.876.** It disagrees on S-11 (Shane partial, judge supported: it missed the wages condition) and S-14.

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
