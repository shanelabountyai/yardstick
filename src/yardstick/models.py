"""Core data models (PRD §3)."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from yardstick.hashing import content_hash

RUN_SCHEMA_VERSION = 1

#: Registry name of the LLM-judge scorer (Phase 3).
LLM_JUDGE = "llm-judge"

MetricName = Literal[
    "pass_rate",
    "mean_score",
    "latency_p50_ms",
    "latency_p95_ms",
    "cost_total_usd",
    "cost_per_item_usd",
]

#: Metrics where a higher value is better. The others (latency, cost) are lower-is-better.
#: Every ``rate:<scorer key>`` metric is higher-is-better too (see :func:`higher_is_better`).
HIGHER_IS_BETTER: frozenset[str] = frozenset({"pass_rate", "mean_score"})

#: Metrics that exist per slice (``rate:<key>`` metrics do too). Latency and cost are run-level only.
SLICE_METRICS: frozenset[str] = frozenset({"pass_rate", "mean_score"})

#: Prefix of rate metrics: ``rate:<scorer key>`` = hits / total over the items where that scorer applied.
RATE_PREFIX = "rate:"
_RATE_METRIC = re.compile(r"^rate:[A-Za-z0-9_.+-]+$")
_FIXED_METRICS: frozenset[str] = frozenset(
    {"pass_rate", "mean_score", "latency_p50_ms", "latency_p95_ms", "cost_total_usd", "cost_per_item_usd"}
)


def is_rate_metric(metric: str) -> bool:
    return bool(_RATE_METRIC.match(metric))


def rate_key(metric: str) -> str:
    return metric[len(RATE_PREFIX) :]


def is_known_metric(metric: str) -> bool:
    return metric in _FIXED_METRICS or is_rate_metric(metric)


def higher_is_better(metric: str) -> bool:
    return metric in HIGHER_IS_BETTER or is_rate_metric(metric)


def has_slices(metric: str) -> bool:
    return metric in SLICE_METRICS or is_rate_metric(metric)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _is_empty_default(value: Any) -> bool:
    return value is None or value is False or (isinstance(value, dict) and not value)


class _Additive(_Strict):
    """Fields added after Phase 1 are left out of the serialised form while they hold their empty default
    (``None``, ``False`` or ``{}``), so Phase 1 runs, suite hashes and run ids stay byte-identical (D-24)."""

    _omit_if_empty: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _omit_empty_additions(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for name in self._omit_if_empty:
            if name in data and _is_empty_default(data[name]):
                del data[name]
        return data


# --------------------------------------------------------------------------- suites


class ScorerSpec(_Additive):
    """A scorer used by a suite.

    ``key`` is the name under which items carry the expected value for this scorer (defaults to ``name``),
    so a suite can use the same scorer twice with different options.

    ``report_only`` scores are recorded and feed ``rate:<key>`` metrics but never decide an item's pass or
    mean score (D-25).
    """

    _omit_if_empty: ClassVar[tuple[str, ...]] = ("report_only",)

    name: str
    key: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    report_only: bool = False

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
        for spec in self.scorers:
            if spec.name == LLM_JUDGE and not spec.report_only:
                raise ValueError(
                    f"scorer {spec.expected_key!r}: llm-judge scores must be report_only: true; a judge reaches a "
                    "gate only through a rate:<key> rule, which YS-05 governs (D-36)"
                )
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


class Output(_Additive):
    """What a target produced for one item. ``None`` telemetry means the target did not report it.

    ``fields`` holds structured values the target reported beside the text (e.g. a status or refusal code),
    for scorers such as ``field-equals`` and ``label-rate``.
    """

    _omit_if_empty: ClassVar[tuple[str, ...]] = ("fields",)

    text: str = ""
    refused: bool | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)

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


class Score(_Additive):
    """One scorer's verdict on one item.

    ``hits``/``total`` are set only by counting scorers (``label-rate`` counts sentence labels); otherwise
    a score counts as 1/1 when passed and 0/1 when not (see :meth:`counts`).
    """

    _omit_if_empty: ClassVar[tuple[str, ...]] = ("hits", "total", "report_only", "labels")

    key: str
    scorer: str
    score: float
    passed: bool
    detail: str = ""
    hits: int | None = None
    total: int | None = None
    report_only: bool = False
    #: Per-unit labels from an ``llm-judge`` scorer (``None`` = no valid label for that unit), so kappa can be
    #: computed from a run (Phase 3).
    labels: list[str | None] | None = None

    @field_validator("score")
    @classmethod
    def _in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be in [0, 1]")
        return round(v, 6)

    @model_validator(mode="after")
    def _check_counts(self) -> Score:
        if (self.hits is None) != (self.total is None):
            raise ValueError("hits and total must be set together")
        if self.hits is not None and self.total is not None and not 0 <= self.hits <= self.total:
            raise ValueError("need 0 <= hits <= total")
        return self

    def counts(self) -> tuple[int, int]:
        if self.hits is not None and self.total is not None:
            return self.hits, self.total
        return (1 if self.passed else 0), 1


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


class JudgeRecord(_Strict):
    """What an ``llm-judge`` scorer key did in one run: which judge (model + prompt hash, the identity kappa
    is computed for), what it cost against the cap, and how many units it could not judge (D-37)."""

    model: str
    prompt_hash: str
    source: str
    cap_usd: float
    spent_usd: float
    calls: int
    units_judged: int
    units_invalid: int
    units_skipped_budget: int
    overrun: bool = False


class Run(_Additive):
    """One execution. ``reported_cost_usd`` is a run-level cost the target reported (e.g. Footnote's
    ``spentUsd``); it is used only when items do not all report their own cost (D-27). ``judges`` records each
    ``llm-judge`` scorer key's judge identity and spend (Phase 3)."""

    _omit_if_empty: ClassVar[tuple[str, ...]] = ("reported_cost_usd", "judges")

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
    reported_cost_usd: float | None = None
    judges: dict[str, JudgeRecord] = Field(default_factory=dict)

    @field_validator("reported_cost_usd")
    @classmethod
    def _run_cost(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("reported_cost_usd must be >= 0")
        return round(v, 6)

    @staticmethod
    def compute_id(payload: dict[str, Any]) -> str:
        """Run id = hash of the run's content excluding ``run_id`` and ``started_at``."""
        body = {k: v for k, v in payload.items() if k not in {"run_id", "started_at"}}
        return content_hash(body)[: len("sha256:") + 16]


# --------------------------------------------------------------------------- metrics


class RateMetric(_Strict):
    """``hits / total`` pooled over the items where one scorer applied; ``value`` is None when total is 0."""

    hits: int
    total: int
    n_items: int
    value: float | None


class SliceMetrics(_Strict):
    n_items: int
    pass_rate: float | None
    mean_score: float | None
    rates: dict[str, RateMetric] = Field(default_factory=dict)


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
    rates: dict[str, RateMetric] = Field(default_factory=dict)
    #: Where the cost metrics came from: every item ("items"), the run-level total ("run"), or nowhere (None).
    cost_source: Literal["items", "run"] | None = None

    def rate(self, key: str, slice_name: str | None = None) -> RateMetric | None:
        if slice_name is None:
            return self.rates.get(key)
        sm = self.slices.get(slice_name)
        return None if sm is None else sm.rates.get(key)

    def value(self, metric: str, slice_name: str | None = None) -> float | int | None:
        if is_rate_metric(metric):
            rm = self.rate(rate_key(metric), slice_name)
            return None if rm is None else rm.value
        if slice_name is not None:
            if metric not in SLICE_METRICS:
                raise KeyError(f"metric {metric!r} is not available per slice")
            sm = self.slices.get(slice_name)
            if sm is None:
                return None
            v: float | int | None = getattr(sm, metric)
            return v
        if metric not in _FIXED_METRICS:
            raise KeyError(f"unknown metric {metric!r}")
        out: float | int | None = getattr(self, metric)
        return out

    def count(self, slice_name: str | None = None, metric: str | None = None) -> int:
        """Items behind a metric: for ``rate:<key>``, only the items where that scorer applied."""
        if metric is not None and is_rate_metric(metric):
            rm = self.rate(rate_key(metric), slice_name)
            return 0 if rm is None else rm.n_items
        if slice_name is None:
            return self.n_items
        sm = self.slices.get(slice_name)
        return 0 if sm is None else sm.n_items


# --------------------------------------------------------------------------- gates


class GateRule(_Strict):
    #: A :data:`MetricName` or ``rate:<scorer key>``.
    metric: str
    slice: str | None = None
    floor: float | None = None
    max: float | None = None
    max_drop: float | None = None
    max_rise: float | None = None
    min_items: int | None = None

    @model_validator(mode="after")
    def _check(self) -> GateRule:
        if not is_known_metric(self.metric):
            raise ValueError(
                f"unknown metric {self.metric!r}; use one of {sorted(_FIXED_METRICS)} or rate:<scorer key>"
            )
        if all(x is None for x in (self.floor, self.max, self.max_drop, self.max_rise)):
            raise ValueError(f"rule for {self.metric!r} sets none of floor / max / max_drop / max_rise")
        if self.slice is not None and not has_slices(self.metric):
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


class JudgePolicy(_Strict):
    """YS-05: a ``rate:<key>`` rule over an ``llm-judge`` score gates only when that judge's pooled kappa
    (from a calibration file matching its model and prompt hash) is at least ``kappa_floor`` (D-06, D-40).
    ``calibrations`` are paths relative to the gate file."""

    kappa_floor: float = 0.6
    calibrations: list[str] = Field(default_factory=list)

    @field_validator("kappa_floor")
    @classmethod
    def _floor(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError("kappa_floor must be in [-1, 1]")
        return v


class GateConfig(_Additive):
    _omit_if_empty: ClassVar[tuple[str, ...]] = ("judge",)

    #: Applies to every rule that does not set its own ``min_items``.
    min_items: int = 1
    rules: list[GateRule]
    judge: JudgePolicy | None = None

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
    #: YS-05: the rule is shown but cannot affect the gate; ``note`` says why (e.g. judge kappa below floor).
    report_only: bool = False
    note: str = ""


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
