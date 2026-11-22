"""Load suites (YAML/JSON) and load/save runs as canonical JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from yardstick.hashing import canonical_json
from yardstick.models import GateConfig, Run, Suite


class LoadError(ValueError):
    pass


#: Top-level keys that identify each kind of file, for "it looks like a suite file" hints (PRD-E).
_KINDS: tuple[tuple[str, frozenset[str]], ...] = (
    ("run", frozenset({"run_id", "suite_hash", "items"})),
    ("suite", frozenset({"scorers", "items"})),
    ("gate", frozenset({"rules"})),
    ("calibration", frozenset({"judge_model", "pooled"})),
    ("verdict", frozenset({"verdicts", "prompt_hash"})),
)
_MAX_PROBLEMS = 3


def describe_validation(exc: ValidationError, kind: str, data: Any) -> str:
    """One short line for a pydantic error: what was expected, what it looks like, the first few problems.
    No input values and no URL (they can be long, and a value can hold a secret)."""
    looks = ""
    if isinstance(data, dict):
        for other, keys in _KINDS:
            if other != kind and keys <= set(data):
                looks = f" (it looks like a {other} file)"
                break
    errs = exc.errors(include_url=False, include_input=False, include_context=False)
    problems = []
    for e in errs[:_MAX_PROBLEMS]:
        loc = ".".join(str(x) for x in e["loc"]) or "top level"
        msg = str(e["msg"]).removeprefix("Value error, ")
        problems.append(f"{loc}: {msg}")
    more = f" (+{len(errs) - _MAX_PROBLEMS} more)" if len(errs) > _MAX_PROBLEMS else ""
    return f"not a {kind} file{looks}: {'; '.join(problems)}{more}"


def _validate[M: BaseModel](model: type[M], kind: str, data: Any) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise LoadError(describe_validation(exc, kind, data)) from exc


def _read_structured(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise LoadError(f"cannot read {path}: not UTF-8 text") from None
    except OSError as exc:
        raise LoadError(f"cannot read {path}: {exc.strerror}") from exc
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise LoadError(f"cannot parse {path}: {exc}") from exc


def load_suite(path: Path) -> Suite:
    return _validate(Suite, "suite", _read_structured(path))


def load_gate(path: Path) -> GateConfig:
    """A gate file. Unlike a ``GateConfig`` built in code (which fails closed when empty, D-11), a gate
    *file* with no rules is a mistake and is refused (exit 2, D-86)."""
    cfg = _validate(GateConfig, "gate", _read_structured(path))
    if not cfg.rules:
        raise LoadError("gate file has no rules; add at least one under `rules:`")
    return cfg


def load_run(path: Path) -> Run:
    return _validate(Run, "run", _read_structured(path))


def run_to_json(run: Run) -> str:
    """Canonical, byte-stable serialisation of a run (trailing newline)."""
    return canonical_json(run.model_dump(mode="json")) + "\n"


def save_run(run: Run, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run_to_json(run), encoding="utf-8")
