"""Load suites (YAML/JSON) and load/save runs as canonical JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from yardstick.hashing import canonical_json
from yardstick.models import GateConfig, Run, Suite


class LoadError(ValueError):
    pass


def _read_structured(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LoadError(f"cannot read {path}: {exc.strerror}") from exc
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise LoadError(f"cannot parse {path}: {exc}") from exc


def load_suite(path: Path) -> Suite:
    return Suite.model_validate(_read_structured(path))


def load_gate(path: Path) -> GateConfig:
    return GateConfig.model_validate(_read_structured(path))


def load_run(path: Path) -> Run:
    return Run.model_validate(_read_structured(path))


def run_to_json(run: Run) -> str:
    """Canonical, byte-stable serialisation of a run (trailing newline)."""
    return canonical_json(run.model_dump(mode="json")) + "\n"


def save_run(run: Run, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run_to_json(run), encoding="utf-8")
