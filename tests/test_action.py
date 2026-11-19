"""action.yml is a composite action whose inputs never reach a shell script by interpolation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")


def _action() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _workflow_uses() -> list[str]:
    uses: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        wf = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in wf["jobs"].values():
            uses += [s["uses"] for s in job.get("steps", []) if "uses" in s]
    return uses


def test_is_a_composite_action() -> None:
    action = _action()
    assert action["runs"]["using"] == "composite"
    for step in action["runs"]["steps"]:
        assert "uses" in step or step.get("shell") == "bash"


def test_action_uses_no_unpinned_actions() -> None:
    for step in _action()["runs"]["steps"]:
        if "uses" in step:
            assert SHA_PIN.match(step["uses"]), step["uses"]


def test_new_ci_jobs_pin_third_party_actions_by_sha() -> None:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    for step in wf["jobs"]["action"]["steps"]:
        uses = step.get("uses")
        if uses is not None and not uses.startswith("./"):
            assert SHA_PIN.match(uses), uses
    assert "./" in _workflow_uses()


def test_inputs_reach_scripts_only_through_env() -> None:
    for step in _action()["runs"]["steps"]:
        script = step.get("run", "")
        assert "${{" not in script, f"expression inside a run script: {step.get('name')}"


def test_inputs_and_outputs_are_documented() -> None:
    action = _action()
    for name, spec in action["inputs"].items():
        assert spec.get("description"), name
        assert spec.get("required") is False, f"{name}: required inputs break install-only use"
    for name in ("suite", "gate-config", "report-path", "results", "command", "baseline", "github-token"):
        assert name in action["inputs"]
    assert set(action["outputs"]) == {"passed", "exit-code", "report", "run"}


def test_installs_from_the_action_checkout_against_the_lock() -> None:
    install = _action()["runs"]["steps"][0]["run"]
    assert "--locked" in install
    assert '--project "$GITHUB_ACTION_PATH"' in install
    assert re.search(r"uv==\$UV_VERSION", install)
    assert re.fullmatch(r"\d+\.\d+\.\d+", _action()["runs"]["steps"][0]["env"]["UV_VERSION"])


def test_token_is_only_used_for_the_comment_step() -> None:
    steps = _action()["runs"]["steps"]
    holders = [s["name"] for s in steps if "inputs.github-token" in str(s.get("env", {}))]
    assert holders == ["Comment on the pull request"]


def test_http_target_inputs_are_additive() -> None:
    """Phase 5: `http` and `http-url` are new optional inputs; the Phase 4 inputs are all still there."""
    action = _action()
    for name in ("http", "http-url"):
        assert action["inputs"][name]["required"] is False and action["inputs"][name]["default"] == ""
    phase4 = {
        "suite",
        "gate-config",
        "results",
        "mapping",
        "command",
        "target-name",
        "run-args",
        "baseline",
        "calibration",
        "report-path",
        "html-report-path",
        "run-path",
        "comment",
        "comment-tag",
        "fail-on-gate",
        "install-only",
        "github-token",
    }
    assert set(action["inputs"]) == phase4 | {"http", "http-url"}
    gate = next(s for s in action["runs"]["steps"] if s.get("id") == "gate")
    assert gate["env"]["YS_HTTP"] == "${{ inputs.http }}"
    assert gate["env"]["YS_HTTP_URL"] == "${{ inputs.http-url }}"
    assert '--http "$YS_HTTP"' in gate["run"] and '--http-url "$YS_HTTP_URL"' in gate["run"]


def test_ci_exercises_the_http_target_on_loopback_only() -> None:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["action"]["steps"]
    http_steps = [s for s in steps if "http" in s.get("with", {})]
    assert len(http_steps) == 2
    for step in http_steps:
        assert "env" not in step, "the self-test needs no secret"
        url = step["with"].get("http-url", "http://127.0.0.1:8808/answer")
        assert url.startswith("http://127.0.0.1:")
