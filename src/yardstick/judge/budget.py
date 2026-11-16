"""Run-level judge budget cap (PRD §3 "llm-judge (rubric, Phase 3)" with budget cap; D-37).

- A call is made only if ``spent + estimate <= cap``; the estimate is the judge's upper bound for that call.
- After the call, the actual cost is charged, or the estimate when the judge reports none.
- The first refused call stops judging for the rest of the run, so the judged units are a prefix in suite order
  and the run says how many were skipped.
- A call that costs more than its estimate breaks the bound the cap relies on: it is charged, flagged as an
  overrun, and no further call is made.
"""

from __future__ import annotations

import math

#: Comparisons round to this many decimals so float noise cannot refuse an affordable call.
PRECISION = 9


class Budget:
    def __init__(self, cap_usd: float) -> None:
        if isinstance(cap_usd, bool) or not isinstance(cap_usd, int | float) or not math.isfinite(cap_usd):
            raise ValueError("judge budget cap must be a finite number of USD")
        if cap_usd < 0:
            raise ValueError("judge budget cap must be >= 0")
        self.cap_usd = float(cap_usd)
        self.spent_usd = 0.0
        self.calls = 0
        self.overrun = False
        self.exhausted = False

    def allows(self, estimate_usd: float) -> bool:
        """Whether a call with this upper-bound cost may be made. A refusal stops all later calls."""
        if estimate_usd < 0 or not math.isfinite(estimate_usd):
            raise ValueError("a judge estimate must be a finite number >= 0")
        if self.exhausted or self.overrun:
            return False
        if round(self.spent_usd + estimate_usd, PRECISION) > round(self.cap_usd, PRECISION):
            self.exhausted = True
            return False
        return True

    def charge(self, estimate_usd: float, actual_usd: float | None) -> None:
        cost = estimate_usd if actual_usd is None else actual_usd
        if cost < 0 or not math.isfinite(cost):
            raise ValueError("a judge call cost must be a finite number >= 0")
        self.spent_usd = round(self.spent_usd + cost, PRECISION)
        self.calls += 1
        if actual_usd is not None and round(actual_usd, PRECISION) > round(estimate_usd, PRECISION):
            self.overrun = True

    @property
    def stopped(self) -> bool:
        return self.exhausted or self.overrun
