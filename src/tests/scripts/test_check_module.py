"""scripts/check_module.py finds a module's web side and holds it to its conformance baseline (PA-4.4)."""
from __future__ import annotations

from scripts import check_module


def test_a_module_maps_to_the_web_features_that_list_it() -> None:
    assert check_module.web_features("trading") == ["trading"]
    assert check_module.web_features("chat") == ["assistant"]
    assert check_module.web_features("live-speech") == []


def test_conformance_fails_on_a_new_gap_and_on_a_fixed_gap_left_in_the_baseline(monkeypatch) -> None:
    monkeypatch.setattr(check_module.module_conformance, "load_baseline", lambda: {"modules": {"story": ["declarations"]}})

    monkeypatch.setattr(check_module.module_conformance, "static_gaps", lambda: {"story": ["contract", "declarations"]})
    assert check_module.conformance_step("story") == (False, "new conformance gaps: contract")

    monkeypatch.setattr(check_module.module_conformance, "static_gaps", lambda: {"story": []})
    assert check_module.conformance_step("story")[0] is False

    monkeypatch.setattr(check_module.module_conformance, "static_gaps", lambda: {"story": ["declarations"]})
    assert check_module.conformance_step("story") == (True, "gaps: declarations")


def test_files_git_does_not_know_fail_the_check(monkeypatch) -> None:
    listed = type("Result", (), {"stdout": "src/app/story/new.py\n"})()
    monkeypatch.setattr(check_module, "_run", lambda command: listed)
    assert check_module.tracked_step("story", "story")[0] is False

    listed.stdout = ""
    assert check_module.tracked_step("story", "story") == (True, "every file is known to git")
