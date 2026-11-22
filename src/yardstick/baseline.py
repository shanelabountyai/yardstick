"""Baselines live in the target repo under ``.yardstick/baselines/`` (DECISIONS D-04).

File name: ``<suite>__<target>.json``. Characters other than Unicode word characters, ``.`` and ``-`` become
``-``; when that changed a name, or a name contains ``__`` (the separator), a short hash of the raw names is
appended so two different suite/target pairs never share a file (D-82). Names that were already safe keep
the file name they always had.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from yardstick.models import Run
from yardstick.suite_io import LoadError, load_run, save_run

DEFAULT_DIR = Path(".yardstick/baselines")
_SAFE = re.compile(r"[^\w.-]+")


def baseline_path(suite_name: str, target_name: str, directory: Path = DEFAULT_DIR) -> Path:
    s, t = _SAFE.sub("-", suite_name), _SAFE.sub("-", target_name)
    name = f"{s}__{t}"
    if s != suite_name or t != target_name or "__" in suite_name or "__" in target_name:
        digest = hashlib.sha256(f"{suite_name}\0{target_name}".encode()).hexdigest()[:8]
        name = f"{name}-{digest}"
    return directory / f"{name}.json"


def pin(run: Run, directory: Path = DEFAULT_DIR) -> tuple[Path, str | None]:
    """Write ``run`` as the baseline. Returns the path and the run id it replaced (None if there was none;
    ``"unreadable"`` if the old file could not be read)."""
    path = baseline_path(run.suite_name, run.target.name, directory)
    old: str | None = None
    if path.exists():
        try:
            old = load_run(path).run_id
        except (LoadError, ValueError):
            old = "unreadable"
    save_run(run, path)
    return path, old


def find(run: Run, directory: Path = DEFAULT_DIR) -> Run | None:
    path = baseline_path(run.suite_name, run.target.name, directory)
    if not path.exists():
        return None
    base = load_run(path)
    if (base.suite_name, base.target.name) != (run.suite_name, run.target.name):
        raise LoadError(
            f"{path} is for suite {base.suite_name!r}, target {base.target.name!r}, not suite "
            f"{run.suite_name!r}, target {run.target.name!r}"
        )
    return base
