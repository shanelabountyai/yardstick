# LinkedIn drafts: Yardstick closeout (2026-11-19)

Two drafts for Shane LaBounty, Principal, Lab Intelligence. Written by Claude on 2026-11-20 during the
unattended closeout run. They are drafts: nothing was posted, and they were **not** added to the Lab
Intelligence Ledger (that is an owner step, see `NEXT.md`).

Rules these drafts follow: Yardstick is a sample build with no client and no client result; no employer is
named; nothing signals a job search; every number comes from a file in this repo, named under each draft. No
career figures are used, because the brief for this run allowed only numbers the repo supports.

Read each one out loud before posting. If it does not sound like you, change it.

---

## Draft 1: the judge that agreed 83% of the time

Pillar: AI integration (experience first). Anchor: the kappa rule.

> My AI judge agreed with me 83% of the time.
>
> I still didn't give it a vote.
>
> Anyone who has run an operations review knows the feeling: a number looks great on the slide, and one question later nobody can say what it measures.
>
> So when I built a sample eval harness to test how I'd gate AI output in CI, I added a rule before I added the judge. An LLM judge can only block a release if it agrees with human graders, measured by Cohen's kappa, above a floor.
>
> Then I ran it on a judge from another sample project of mine. I had hand-graded 40 sentences. The judge matched my grade on 83% of them.
>
> Kappa was 0.17. The floor was 0.6.
>
> Why so low? Almost every sentence was "supported." Two graders who both say "supported" nearly every time will agree about 79% of the time by chance. The judge had barely beaten a coin that always lands on yes.
>
> That same judge reported 96% of sentences as supported. On a dashboard, that number would have looked like a pass.
>
> In the harness it shows up as "report-only." You can read it. It cannot change the verdict.
>
> This is a sample build on committed test data, not a client result. But the lesson carries: before an AI grades your AI, check whether it agrees with a person on the hard cases, not just the easy ones.
>
> What do you require before an automated score is allowed to stop a release?
>
> #aievals #marketingops #llm #aigovernance

**Numbers and where each comes from**

| Number | Source file |
|---|---|
| 83% raw agreement, n 40, pooled kappa 0.17 | `examples/footnote/kappa.md` (rows `pooled / opus / raw`, `n`, `kappa`) |
| Chance agreement about 79% (p_e 0.790) | `examples/footnote/kappa.md` (row `pooled / opus / p_e`) |
| Floor 0.6 | `fixtures/gates/footnote-judged.yaml` (`judge.kappa_floor: 0.6`); `docs/DECISIONS.md` D-06 |
| 96% of sentences supported (49/51) | `examples/footnote/reproduction.md` (row "Sentence support (judge), A, M, V") |
| "report-only" | `examples/footnote/judged-report.md`; README "Judges and calibration" |

Guardrail notes: "another sample project of mine" is Footnote; name it or not as you prefer. "I had hand-graded
40 sentences" follows `fixtures/footnote/ATTRIBUTION.md`, which calls the two sheets "Shane's sentence grades";
sheet 1 is described there as "enriched, Claude-assisted", so if "hand-graded" overstates sheet 1, change it to
"graded". "Barely beaten a coin that always lands on yes" is a figure of speech for kappa near zero: cut it if
it reads as a statistic.

---

## Draft 2: 74 matched, 49 it could not check

Pillar: Impact (accountability). Anchor: the scorecard reproduction.

> Before I let a tool grade my work, I make it reproduce numbers it didn't produce.
>
> I built a sample eval harness this month. The job: sit on top of an AI project's own tests and fail the build when quality drops.
>
> A tool like that is only useful if you believe its arithmetic. So the first real test wasn't a demo. It was an audit.
>
> I pointed it at the committed result files from another sample project of mine, one with its own scorecard, and asked it to recompute every number on that scorecard from the raw files.
>
> 74 numbers matched.
> 0 differed.
> 49 it could not reproduce.
>
> The 49 are the part I'd show a CMO.
>
> Each one is listed with the reason: the figure comes from a database row, or from a result file the harness was never given. It didn't guess. It didn't quietly drop them from the total. It said "not reproducible" and why.
>
> Most reporting problems I've seen aren't wrong numbers. They're numbers nobody can trace, sitting next to numbers everybody can, with no way to tell them apart.
>
> Same rule for cost and latency in this build: if the system under test doesn't report them, the report says "not reported." Never zero.
>
> It's a sample build on synthetic and committed test data, so there's no client result here. The habit is the point.
>
> When a report can't verify a number, does yours say so?
>
> #marketingops #aievals #measurement #analytics

**Numbers and where each comes from**

| Number | Source file |
|---|---|
| 74 match, 0 differ, 49 not reproducible | `examples/footnote/reproduction.md` (summary line); regenerated in this run by `yardstick footnote reproduce` with the same counts |
| Reasons listed per number (database rows, other result files) | `examples/footnote/reproduction.md` (the "Result" column) |
| "not reported", never 0 | `docs/PRD.md` invariant YS-04; `docs/DECISIONS.md` D-09 |

Guardrail notes: "this month" assumes posting in November 2026 (commits run 2026-11-13 to 2026-11-19). "Most
reporting problems I've seen" is your own experience to confirm or cut: it is not a fact from this repo.

---

## What was left out on purpose

- No claim that the harness is used by anyone, and no claim about what it saved or caught in production.
- No career figures, no tenure line, no employer names.
- No mention of the HTTP target or a live judge as working features: the first has only run against a local
  test server and the second has never been run (README).
