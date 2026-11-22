from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from yardstick.models import Item, Output, TargetInfo


class AdapterError(RuntimeError):
    """The target could not be run at all (as opposed to failing on individual items)."""


class Adapter(Protocol):
    info: TargetInfo

    def produce(self, items: Sequence[Item]) -> dict[str, Output]: ...


@dataclass(frozen=True)
class RunMeta:
    """Run-level facts a target reported (e.g. a results file's model and total spend)."""

    model: str | None = None
    cost_usd: float | None = None
    #: The judge behind judge-derived label fields, if the target reports it (D-79).
    judge_model: str | None = None
    judge_prompt_hash: str | None = None


@runtime_checkable
class ReportsRunMeta(Protocol):
    def run_meta(self) -> RunMeta: ...
