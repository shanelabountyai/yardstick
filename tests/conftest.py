"""Shared pytest setup.

Hypothesis' default 200 ms per-example deadline made the property tests fail on slow machines and busy CI
runners (DECISIONS D-22). The pass/fail result must depend only on the code, so the deadline is off.
"""

from __future__ import annotations

from hypothesis import settings

settings.register_profile("yardstick", deadline=None)
settings.load_profile("yardstick")
