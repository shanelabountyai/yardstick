"""Core data models (PRD §3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yardstick.hashing import content_hash

RUN_SCHEMA_VERSION = 1

MetricName = Literal[
    "pass_rate",
    "mean_score",
    "latency_p50_ms",
    "latency_p95_ms",
    "cost_total_usd",
    "cost_per_item_usd",
]

#: Metrics where a higher value is better. The others (latency, cost) are lower-is-better.
HIGHER_IS_BETTER: frozenset[str] = frozenset({"pass_rate", "mean_score"})

#: Metrics that exist per slice. Latency and cost are run-level only in Phase 1.
SLICE_METRICS: frozenset[str] = frozenset({"pass_rate", "mean_score"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- suites


class ScorerSpec(_Strict):
    """A scorer used by a suite.

    ``key`` is the name under which items carry the expected value for this scorer (defaults to ``name``),
    so a suite can use the same scorer twice with different options.
    """

    name: str
    key: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @property
    def expected_key(self) -> str:
        return self.key or self.name


class Item(_Strict):
    """One suite item. ``expected`` maps a scorer key to that scorer's expected value.

    A scorer applies to an item only if the item has an entry for the scorer's key.
    """

    id: str
    input: Any
    expected: dict[str, Any]
    slices: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("item id must not be blank")
        return v


class Suite(_Strict):
    name: str
    description: str = ""
    scorers: list[ScorerSpec]
    items: list[Item]

    @model_validator(mode="after")
    def _check(self) -> Suite:
        ids = [i.id for i in self.items]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate item ids: {dupes}")
        keys = [s.expected_key for s in self.scorers]
        if len(keys) != len(set(keys)):
            raise ValueError("scorer keys must be unique; set `key` when a scorer is used twice")
        known = set(keys)
        for item in self.items:
            unknown = set(item.expected) - known
            if unknown:
                raise ValueError(
                    f"item {item.id!r} has expected values for unknown scorers: {sorted(unknown)}"
                )
            if not item.expected:
                raise ValueError(f"item {item.id!r} has no expected values, so nothing would score it")
        return self

    @property
    def content_hash(self) -> str:
        """Hash of everything that affects scoring (name, scorers, items). Description is excluded."""
        return content_hash(
            {
                "name": self.name,
                "scorers": [s.model_dump(mode="json") for s in self.scorers],
                "items": [i.model_dump(mode="json") for i in self.items],
            }
        )


# --------------------------------------------------------------------------- runs


class Output(_Strict):
    """What a target produced for one item. ``None`` telemetry means the target did not report it."""

    text: str = ""
    refused: bool | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    error: str | None = None

    @field_validator("latency_ms")
    @classmethod
    def _latency_nonneg(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("latency_ms must be >= 0")
        return v

    @field_validator("cost_usd")
    @classmethod
    def _cost(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("cost_usd must be >= 0")
        return round(v, 6)


class Score(_Strict):
    key: str
    scorer: str
    score: float
    passed: bool
    detail: str = ""

    @field_validator("score")
    @classmethod
    def _in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be in [0, 1]")
        return round(v, 6)


class ItemResult(_Strict):
    item_id: str
    slices: list[str]
    output: Output
    scores: list[Score]
    passed: bool
    score: float


class TargetInfo(_Strict):
    name: str
    kind: Literal["command", "results-file", "http"]
    #: Human-readable description, e.g. the command line. Never contains secrets: adapters redact env vars.
    detail: str = ""


class Run(_Strict):
    schema_version: int = RUN_SCHEMA_VERSION
    run_id: str
    suite_name: str
    suite_hash: str
    target: TargetInfo
    model: str | None = None
    prompt_hash: str | None = None
    git_sha: str | None = None
    started_at: str
    items: list[ItemResult]

    @staticmethod
    def compute_id(payload: dict[str, Any]) -> str:
        """Run id = hash of the run's content excluding ``run_id`` and ``started_at``."""
        body = {k: v for k, v in payload.items() if k not in {"run_id", "started_at"}}
        return content_hash(body)[: len("sha256:") + 16]


# --------------------------------------------------------------------------- metrics


class SliceMetrics(_Strict):
    n_items: int
    pass_rate: float | None
    mean_score: float | None


class MetricSet(_Strict):
    n_items: int
    n_errors: int
    pass_rate: float | None
    mean_score: float | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    latency_reported: int
    cost_total_usd: float | None
    cost_per_item_usd: float | None
    cost_reported: int
    slices: dict[str, SliceMetrics]

    def value(self, metric: str, slice_name: str | None = None) -> float | int | None:
        if slice_name is not None:
            if metric not in SLICE_METRICS:
                raise KeyError(f"metric {metric!r} is not available per slice")
            sm = self.slices.get(slice_name)
            if sm is None:
                return None
            v: float | int | None = getattr(sm, metric)
            return v
        if metric not in MetricSet.model_fields or metric in {"slices", "n_errors"}:
            raise KeyError(f"unknown metric {metric!r}")
        out: float | int | None = getattr(self, metric)
        return out

    def count(self, slice_name: str | None = None) -> int:
        if slice_name is None:
            return self.n_items
        sm = self.slices.get(slice_name)
        return 0 if sm is None else sm.n_items


# --------------------------------------------------------------------------- gates


class GateRule(_Strict):
    metric: MetricName
    slice: str | None = None
    floor: float | None = None
    max: float | None = None
    max_drop: float | None = None
    max_rise: float | None = None
    min_items: int | None = None

    @model_validator(mode="after")
    def _check(self) -> GateRule:
        if all(x is None for x in (self.floor, self.max, self.max_drop, self.max_rise)):
            raise ValueError(f"rule for {self.metric!r} sets none of floor / max / max_drop / max_rise")
        if self.slice is not None and self.metric not in SLICE_METRICS:
            raise ValueError(f"metric {self.metric!r} is not available per slice")
        if self.min_items is not None and self.min_items < 1:
            raise ValueError("min_items must be >= 1")
        for name in ("max_drop", "max_rise"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise ValueError(f"{name} must be >= 0")
        return self

    @property
    def label(self) -> str:
        return self.metric if self.slice is None else f"{self.metric}[{self.slice}]"


class GateConfig(_Strict):
    #: Applies to every rule that does not set its own ``min_items``.
    min_items: int = 1
    rules: list[GateRule]

    @field_validator("min_items")
    @classmethod
    def _min(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_items must be >= 1")
        return v


class CheckResult(_Strict):
    check: str
    passed: bool
    detail: str


class RuleResult(_Strict):
    rule: GateRule
    current: float | int | None
    baseline: float | int | None
    n_items: int
    min_items: int
    passed: bool
    checks: list[CheckResult]


class GateResult(_Strict):
    passed: bool
    rules: list[RuleResult]
    baseline_run_id: str | None
    suite_changed: bool
    warnings: list[str]


# --------------------------------------------------------------------------- compare


class MetricDelta(_Strict):
    metric: str
    slice: str | None
    a: float | int | None
    b: float | int | None
    delta: float | None
    #: "better", "worse", "same" or "n/a" (one side not reported)
    direction: Literal["better", "worse", "same", "n/a"]


class Comparison(_Strict):
    run_a: str
    run_b: str
    suite_changed: bool
    deltas: list[MetricDelta]
    newly_failing: list[str]
    newly_passing: list[str]
    only_in_a: list[str]
    only_in_b: list[str]
    warnings: list[str]
