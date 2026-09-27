from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_APP = ROOT / "src" / "app"
LEGACY_RUNTIME_IMPORTS = (
    "app.runtime_config",
    "app.runtime_capabilities",
    "app.runtime_contracts",
    "app.runtime_paths",
    "app.runtime_logging",
)


def _python_files(root: Path):
    yield from root.rglob("*.py")


def test_trading_and_jobs_do_not_import_gateway() -> None:
    offenders: list[str] = []
    for package in (SRC_APP / "trading", SRC_APP / "jobs"):
        for path in _python_files(package):
            if "app.gateway" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_deleted_root_runtime_modules_have_no_python_importers() -> None:
    offenders: list[str] = []
    for path in _python_files(SRC_APP):
        text = path.read_text(encoding="utf-8")
        if any(legacy in text for legacy in LEGACY_RUNTIME_IMPORTS):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_runtime_primitives_live_under_runtime_package() -> None:
    expected = {
        "background.py",
        "capabilities.py",
        "config.py",
        "contracts.py",
        "logging.py",
        "net.py",
        "paths.py",
    }
    actual = {path.name for path in (SRC_APP / "runtime").glob("*.py")}
    assert expected <= actual
