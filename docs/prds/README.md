# Review-fix PRDs (2026-11-21)

Nine PRDs for the Do now and Do next work items of the five-lens review
(`docs/reviews/FIVE-LENS-2026-11-19.md`, §3), with Shane's answers to the ten decisions in §4 (2026-11-21:
all ten recommendations accepted). Written and built by the unattended run of 2026-11-22 on branch
`review-fixes/2026-11-21`.

| PRD | Title | Review items | Shane's decisions applied | Build order |
|---|---|---|---|---|
| [A](PRD-A-invariants.md) | Invariants hold (YS-02, YS-05) | 1, 4 | 2 (a), 3 (a) | 1 |
| [B](PRD-B-gate-output.md) | Gate output a stranger can read | 2, 6 | 1 (a) | 2 |
| [C](PRD-C-baselines.md) | Baseline lookup and messages | 5 | 4 (a) | 3 |
| [D](PRD-D-readme-license.md) | README first read, LICENSE and docs drift | 3 | 6 (a), 7 (b) | 4 |
| [E](PRD-E-errors-gate-validation.md) | Errors, exit codes and gate file validation | 7, 13 | (none) | 5 |
| [F](PRD-F-reports-first-reader.md) | Reports for a first reader | 8, 10, 11 | 5 (b) | 8 |
| [G](PRD-G-markdown-escaping.md) | Markdown escaping and name constraints | 9 | (none) | 6 |
| [H](PRD-H-not-scored-items.md) | Items with no gating scorer | 12 | 9 (b) | 7 |
| [I](PRD-I-html-layout.md) | HTML report layout | 14, 15, 20 | 8 (b) | 9 |

Build order is the run brief's: correctness and security before presentation (A, B, C, D, E, G, H, F, I).
Decision 10 (a) confirms D-43; review item 22 stays "Do not do", and items 16 to 21 ("Later") are out of
scope for every PRD here.

Every judgment call the run made while writing or building these is a numbered row in `docs/DECISIONS.md`
(D-79 onward).
