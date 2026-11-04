"""Trading research reads the web only when the research feature is on (trading's feature declaration).

A trading-only install ships without research's code. The monitors that start trading research run only at certain
hours and with certain strategies stored, so the fresh-process boot test catches an import here only sometimes; these
tests build the adapter directly and do not depend on the clock.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROBE = """
import json, sys
from types import SimpleNamespace
from app.apps.trading.research.adapters.generic_web import GenericWebAdapter
adapter = GenericWebAdapter()
loaded = sorted(name for name in sys.modules if name.startswith("app.platform.research"))
report = {"loaded": loaded, "search": adapter.search_service is not None, "extract": adapter.extractor_factory is not None}
if not report["search"]:
    identity = SimpleNamespace(symbol="TEST", legal_name=None, instrument_id="equity:TEST")
    found, page = adapter.find(identity), adapter.extract(identity, locator="https://example.com")
    report["results"] = [[len(found.evidence), list(found.warnings)], [len(page.evidence), list(page.warnings)]]
print(json.dumps(report))
"""


def _probe(**settings: str) -> dict:
    source_root = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if key not in {"OMNIX_FEATURES", "OMNIX_FEATURES_DISABLED"}}
    env.update(settings, PYTHONPATH=os.pathsep.join([str(source_root), os.environ.get("PYTHONPATH", "")]))
    result = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize(
    "settings",
    [{"OMNIX_FEATURES": "trading"}, {"OMNIX_FEATURES_DISABLED": "research"}],
    ids=["trading-only", "research-disabled"],
)
def test_without_research_trading_imports_none_of_it_and_finds_nothing(settings: dict[str, str]) -> None:
    report = _probe(**settings)

    assert report["loaded"] == []
    assert report["search"] is False and report["extract"] is False
    unavailable = ["web_unavailable:research_feature_disabled"]
    assert report["results"] == [[0, unavailable], [0, unavailable]]


@pytest.mark.parametrize("settings", [{"OMNIX_FEATURES": "trading,chat,research"}, {}], ids=["both", "default"])
def test_with_research_trading_reads_the_web_through_it(settings: dict[str, str]) -> None:
    report = _probe(**settings)

    assert "app.platform.research.contracts" in report["loaded"]
    assert report["search"] is True and report["extract"] is True
