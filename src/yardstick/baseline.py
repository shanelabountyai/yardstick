"""Baselines live in the target repo under ``.yardstick/baselines/`` (DECISIONS D-04)."""

from __future__ import annotations

import re
from pathlib import Path

from yardstick.models import Run
from yardstick.suite_io import load_run, save_run

DEFAULT_DIR = Path(".yardstick/baselines")
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def baseline_path(suite_name: str, target_name: str, directory: Path = DEFAULT_DIR) -> Path:
    return directory / f"{_SAFE.sub('-', suite_name)}__{_SAFE.sub('-', target_name)}.json"


def pin(run: Run, directory: Path = DEFAULT_DIR) -> Path:
    path = baseline_path(run.suite_name, run.target.name, directory)
    save_run(run, path)
    return path


def find(run: Run, directory: Path = DEFAULT_DIR) -> Run | None:
    path = baseline_path(run.suite_name, run.target.name, directory)
    return load_run(path) if path.exists() else None
