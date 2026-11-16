"""Judge interface (Phase 3, D-34). A judge labels one *unit* (a sentence, or a whole output) against a
rubric.

Implementations: :class:`~yardstick.judge.recorded.RecordedJudge` (replays committed verdicts, no call made),
:class:`~yardstick.judge.recorded.ScriptedJudge` (tests), :class:`~yardstick.judge.anthropic.AnthropicJudge`
(Messages API behind an injectable transport; never called live in this repo's tests or CI).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class JudgeError(ValueError):
    """A judge could not be set up (bad verdict file, missing key, bad prices)."""


@dataclass(frozen=True)
class JudgeRequest:
    item_id: str
    unit_index: int
    unit_text: str
    #: The item's input (e.g. the question), shown to a live judge beside the unit.
    context: Any
    rubric: str
    labels: tuple[str, ...]

    @property
    def key(self) -> str:
        """Unit key ``<item id>:<unit index>``, shared with human grade files (D-35)."""
        return unit_key(self.item_id, self.unit_index)


@dataclass(frozen=True)
class JudgeReply:
    #: One of the request's labels, or ``None`` when the judge gave no valid label (excluded from rates and
    #: from kappa).
    label: str | None
    #: What the call cost, if the judge knows; ``None`` makes the budget charge the estimate (D-37).
    cost_usd: float | None
    detail: str = ""


@dataclass(frozen=True)
class JudgeIdentity:
    """What kappa is computed for: the judge model and the hash of its prompt (PRD §4)."""

    model: str
    prompt_hash: str
    source: str


class Judge(Protocol):
    def identity(self, rubric: str, labels: Sequence[str]) -> JudgeIdentity: ...

    def estimate_usd(self, request: JudgeRequest) -> float:
        """An upper bound on what :meth:`judge` will cost for this request (the budget relies on it)."""
        ...

    def judge(self, request: JudgeRequest) -> JudgeReply: ...


def unit_key(item_id: str, unit_index: int) -> str:
    return f"{item_id}:{unit_index}"
