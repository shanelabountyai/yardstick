"""Judges that make no model call: replay of committed verdicts, and a scripted judge for tests."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from yardstick.judge.base import JudgeError, JudgeIdentity, JudgeReply, JudgeRequest


class VerdictFile(BaseModel):
    """Recorded verdicts: ``verdicts`` maps a unit key ``<item id>:<index>`` to a label, or ``null`` when the
    judge gave no valid label (Footnote's ``schema_invalid``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    prompt_hash: str
    source: str
    labels: list[str]
    verdicts: dict[str, str | None]

    @field_validator("verdicts")
    @classmethod
    def _keys(cls, v: dict[str, str | None]) -> dict[str, str | None]:
        for key in v:
            item, sep, idx = key.rpartition(":")
            if not sep or not item or not idx.isdigit():
                raise ValueError(f"verdict key {key!r} is not '<item id>:<unit index>'")
        return v


def load_verdicts(path: Path) -> VerdictFile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        vf = VerdictFile.model_validate(data)
    except (OSError, ValueError, ValidationError) as exc:
        raise JudgeError(f"{path}: {exc}") from exc
    bad = sorted({v for v in vf.verdicts.values() if v is not None and v not in vf.labels})
    if bad:
        raise JudgeError(f"{path}: verdicts use labels not in 'labels': {bad}")
    return vf


def verdict_file_json(vf: VerdictFile) -> str:
    return json.dumps(vf.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


class RecordedJudge:
    """Replays a verdict file. No call is made, so each unit costs $0 and the estimate is $0 (D-34)."""

    def __init__(self, verdicts: VerdictFile, path_label: str) -> None:
        self.file = verdicts
        self.path_label = path_label

    @classmethod
    def from_path(cls, path: Path) -> RecordedJudge:
        return cls(load_verdicts(path), path.name)

    def identity(self, rubric: str, labels: Sequence[str]) -> JudgeIdentity:
        unknown = sorted(set(self.file.labels) - set(labels))
        if unknown:
            raise JudgeError(f"recorded verdicts use labels the scorer does not declare: {unknown}")
        return JudgeIdentity(
            model=self.file.model,
            prompt_hash=self.file.prompt_hash,
            source=f"replay {self.path_label} ({self.file.source})",
        )

    def estimate_usd(self, request: JudgeRequest) -> float:
        return 0.0

    def judge(self, request: JudgeRequest) -> JudgeReply:
        if request.key not in self.file.verdicts:
            return JudgeReply(None, 0.0, "no recorded verdict")
        label = self.file.verdicts[request.key]
        return JudgeReply(label, 0.0, "" if label is not None else "recorded verdict invalid")


class ScriptedJudge:
    """Test judge: labels from a mapping or function, a fixed estimate and cost per call; counts calls."""

    def __init__(
        self,
        labels: Mapping[str, str | None] | Callable[[JudgeRequest], str | None],
        *,
        estimate_usd: float = 0.0,
        cost_usd: float | None = 0.0,
        model: str = "scripted",
        prompt_hash: str = "scripted0000",
    ) -> None:
        self._labels = labels
        self._estimate = estimate_usd
        self._cost = cost_usd
        self._model = model
        self._prompt_hash = prompt_hash
        self.calls: list[str] = []

    def identity(self, rubric: str, labels: Sequence[str]) -> JudgeIdentity:
        return JudgeIdentity(model=self._model, prompt_hash=self._prompt_hash, source="scripted")

    def estimate_usd(self, request: JudgeRequest) -> float:
        return self._estimate

    def judge(self, request: JudgeRequest) -> JudgeReply:
        self.calls.append(request.key)
        label = self._labels(request) if callable(self._labels) else self._labels.get(request.key)
        return JudgeReply(label, self._cost)
