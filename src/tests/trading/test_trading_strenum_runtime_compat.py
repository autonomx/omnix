from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_trading_package_installs_strenum_compat_before_submodule_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["OMNIX_PERSISTENCE_MODE"] = "legacy_test"
    env["OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE"] = "1"
    code = r'''
import enum
if hasattr(enum, "StrEnum"):
    delattr(enum, "StrEnum")
import app.trading
from enum import StrEnum
from app.trading.strategy_dynamic_discovery import DiscoveryTriggerType
assert issubclass(StrEnum, str)
assert str(DiscoveryTriggerType.MARKET_ANOMALY) == "market_anomaly"
print("STR_ENUM_COMPAT_OK")
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "STR_ENUM_COMPAT_OK" in result.stdout
