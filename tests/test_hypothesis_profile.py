from __future__ import annotations

import importlib
import pkgutil

from hypothesis import settings

import tests


def test_profile_is_loaded_with_no_deadline() -> None:
    assert settings.get_profile("yardstick").deadline is None
    assert settings().deadline is None


def test_every_property_test_has_no_deadline() -> None:
    # Includes tests with their own @settings(max_examples=...): they must still inherit deadline=None.
    found = []
    for mod in pkgutil.walk_packages(tests.__path__, "tests."):
        module = importlib.import_module(mod.name)
        for name, fn in vars(module).items():
            s = getattr(fn, "_hypothesis_internal_use_settings", None)
            if name.startswith("test_") and s is not None:
                found.append(name)
                assert s.deadline is None, name
    assert "test_build_run_deterministic_for_any_outputs" in found
    assert len(found) >= 8
