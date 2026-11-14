from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from yardstick.models import Item, Output, TargetInfo


class AdapterError(RuntimeError):
    """The target could not be run at all (as opposed to failing on individual items)."""


class Adapter(Protocol):
    info: TargetInfo

    def produce(self, items: Sequence[Item]) -> dict[str, Output]: ...
