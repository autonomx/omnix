"""Tests for the repo-wide Ruff debt ratchet."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/check_ruff_baseline.py"
SPEC = importlib.util.spec_from_file_location("omnix_ruff_baseline", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ruff_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ruff_baseline)


def test_summarize_counts_rule_codes() -> None:
    assert ruff_baseline.summarize(
        [{"code": "F401"}, {"code": "UP006"}, {"code": "F401"}]
    ) == {"F401": 2, "UP006": 1}


def test_exact_baseline_counts_pass() -> None:
    assert ruff_baseline.compare({"F401": 2, "F821": 0}, {"F401": 2, "F821": 0}) == []


def test_increased_or_stale_counts_fail_until_baseline_is_reviewed() -> None:
    errors = ruff_baseline.compare({"F401": 3, "UP006": 1}, {"F401": 2, "UP006": 2})
    assert any(error.startswith("F401: increased") for error in errors)
    assert any(error.startswith("UP006: baseline is stale") for error in errors)


def test_f821_is_a_hard_zero_even_if_baseline_contains_it() -> None:
    errors = ruff_baseline.compare({"F821": 1}, {"F821": 1})
    assert "F821: undefined names must be zero, found 1" in errors
