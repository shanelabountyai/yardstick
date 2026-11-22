"""``results-file`` target: read a project's existing eval result JSON instead of producing outputs.

A :class:`ResultsMapping` says where things are, as dotted paths (``gate.score``, ``rows.0.id``):

    rows: rows                 # the list of per-item rows ("" = the file itself is the list)
    id: id                     # item id inside a row
    text: answer               # optional; non-string values are stored as canonical JSON
    refused: {path: status, values: [refused]}   # optional; refused iff the value is one of ``values``
    latency_ms: ms             # optional integer
    cost_usd: usd              # optional number
    error: error               # optional; a non-null value marks the item as a target error
    fields: {status: status, refusal_code: refusal}   # optional structured values for field scorers
    model: model               # optional, file level
    run_cost_usd: spentUsd     # optional, file level (D-27)
    judge_model: judge         # optional, file level: the judge behind judge-derived label fields (D-79)
    judge_prompt_hash: judgePromptHash   # optional, file level

A path that is absent (or null) leaves the value unreported; it is never defaulted (YS-04). A file that
cannot be read, has no row list, a row without a string id, a duplicate id, or an id the suite does not have
fails the whole run (exit 2), like the ``command`` adapter.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yardstick.adapters.base import AdapterError, RunMeta
from yardstick.hashing import canonical_json
from yardstick.models import Item, Output, TargetInfo

MISSING: Any = object()


class RefusedRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    values: list[Any] = Field(min_length=1)


class ResultsMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: str = "rows"
    id: str = "id"
    text: str | None = None
    refused: RefusedRule | None = None
    latency_ms: str | None = None
    cost_usd: str | None = None
    error: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    run_cost_usd: str | None = None
    judge_model: str | None = None
    judge_prompt_hash: str | None = None


def get_path(doc: Any, path: str) -> Any:
    """Follow a dotted path through dicts (keys) and lists (integer indexes). Absent -> ``MISSING``."""
    if path == "":
        return doc
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return MISSING
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if idx >= len(cur):
                return MISSING
            cur = cur[idx]
        else:
            return MISSING
    return cur


def _opt(row: Any, path: str | None) -> Any:
    """Value at ``path`` or ``None`` when the mapping has no path, or the row lacks it, or it is null."""
    if path is None:
        return None
    v = get_path(row, path)
    return None if v is MISSING else v


class ResultsFileAdapter:
    """Maps one result file to outputs. Subclasses can rewrite rows (:meth:`transform_row`) and derive fields
    (:meth:`derived_fields`), as the Footnote mapping does."""

    def __init__(self, name: str, path: Path, mapping: ResultsMapping, mapping_name: str = "custom") -> None:
        self.path = path
        self.mapping = mapping
        self.info = TargetInfo(name=name, kind="results-file", detail=f"{path} (mapping: {mapping_name})")
        self._doc: Any = MISSING

    # -- hooks -------------------------------------------------------------------------------------------

    def transform_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return row

    def derived_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        return {}

    # -- adapter -----------------------------------------------------------------------------------------

    def document(self) -> Any:
        if self._doc is MISSING:
            try:
                text = self.path.read_text(encoding="utf-8")
            except OSError as exc:
                raise AdapterError(f"cannot read results file {self.path}: {exc.strerror}") from exc
            try:
                self._doc = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AdapterError(f"results file {self.path} is not JSON: {exc.msg}") from exc
        return self._doc

    def run_meta(self) -> RunMeta:
        doc = self.document()
        model = _opt(doc, self.mapping.model)
        cost = _opt(doc, self.mapping.run_cost_usd)
        if model is not None and not isinstance(model, str):
            raise AdapterError(f"{self.mapping.model!r} is not a string")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, int | float) or cost < 0):
            raise AdapterError(f"{self.mapping.run_cost_usd!r} is not a non-negative number")
        judge_meta = {}
        for name in ("judge_model", "judge_prompt_hash"):
            path = getattr(self.mapping, name)
            value = _opt(doc, path)
            if value is not None and not isinstance(value, str):
                raise AdapterError(f"{path!r} is not a string")
            judge_meta[name] = value
        return RunMeta(model=model, cost_usd=None if cost is None else float(cost), **judge_meta)

    def produce(self, items: Sequence[Item]) -> dict[str, Output]:
        rows = get_path(self.document(), self.mapping.rows)
        if not isinstance(rows, list):
            raise AdapterError(f"results file {self.path}: no row list at {self.mapping.rows!r}")
        wanted = {i.id for i in items}
        outputs: dict[str, Output] = {}
        for n, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise AdapterError(f"row {n} is not an object")
            row = self.transform_row(raw)
            item_id = get_path(row, self.mapping.id)
            if not isinstance(item_id, str):
                raise AdapterError(f"row {n} has no string id at {self.mapping.id!r}")
            if item_id not in wanted:
                raise AdapterError(f"row {n}: unknown item id {item_id!r}")
            if item_id in outputs:
                raise AdapterError(f"row {n}: duplicate row for {item_id!r}")
            outputs[item_id] = self._output(row, n)
        return outputs

    def _output(self, row: dict[str, Any], n: int) -> Output:
        m = self.mapping
        text_v = _opt(row, m.text)
        text = "" if text_v is None else (text_v if isinstance(text_v, str) else canonical_json(text_v))
        refused: bool | None = None
        if m.refused is not None:
            rv = get_path(row, m.refused.path)
            refused = None if rv is MISSING else rv in m.refused.values
        latency = _opt(row, m.latency_ms)
        if latency is not None and (isinstance(latency, bool) or not isinstance(latency, int)):
            raise AdapterError(f"row {n}: latency at {m.latency_ms!r} is not an integer")
        cost = _opt(row, m.cost_usd)
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, int | float)):
            raise AdapterError(f"row {n}: cost at {m.cost_usd!r} is not a number")
        err = _opt(row, m.error)
        fields = {name: v for name, path in sorted(m.fields.items()) if (v := _opt(row, path)) is not None}
        fields.update(self.derived_fields(row))
        try:
            return Output(
                text=text,
                refused=refused,
                latency_ms=latency,
                cost_usd=None if cost is None else float(cost),
                error=None if err is None else str(err),
                fields=fields,
            )
        except ValidationError as exc:
            raise AdapterError(f"row {n}: bad output: {exc.errors()[0]['msg']}") from exc


def load_mapping(path: Path) -> ResultsMapping:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AdapterError(f"cannot load mapping {path}: {exc}") from exc
    try:
        return ResultsMapping.model_validate(data)
    except ValidationError as exc:
        raise AdapterError(f"bad mapping {path}: {exc}") from exc
