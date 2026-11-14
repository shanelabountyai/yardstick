"""YS-03: runs over different suite content cannot be compared silently."""

from __future__ import annotations

from yardstick.models import Run


class SuiteChangedError(ValueError):
    pass


def suite_change_warning(a: Run, b: Run) -> str:
    return (
        f"Suite content changed between runs ({a.suite_hash[:19]} -> {b.suite_hash[:19]}); "
        "compared anyway because --allow-suite-change was given. Deltas may not be like-for-like."
    )


def check_same_suite(a: Run, b: Run, allow_suite_change: bool) -> list[str]:
    """Return warnings to surface in reports; raise if the suites differ and that was not allowed."""
    if a.suite_hash == b.suite_hash:
        return []
    if not allow_suite_change:
        raise SuiteChangedError(
            f"suite hash differs ({a.suite_hash[:19]} vs {b.suite_hash[:19]}): "
            "re-pin the baseline, or pass --allow-suite-change to compare anyway"
        )
    return [suite_change_warning(a, b)]
