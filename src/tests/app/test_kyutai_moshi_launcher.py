from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_launcher_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "run_kyutai_moshi.py"
    spec = importlib.util.spec_from_file_location("test_run_kyutai_moshi", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_unmute_checkout_is_reused(tmp_path: Path) -> None:
    module = _load_launcher_module()
    unmute_dir = tmp_path / "unmute"
    unmute_dir.mkdir()
    compose = unmute_dir / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")

    assert module._ensure_unmute_checkout(unmute_dir) == compose


def test_missing_unmute_checkout_is_bootstrapped_at_pinned_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_launcher_module()
    unmute_dir = tmp_path / "unmute"
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/tools/{name}")

    def fake_run_git(_git: str, *arguments: str) -> None:
        calls.append(arguments)
        if arguments[0] == "clone":
            Path(arguments[-1]).mkdir(parents=True)
        if "checkout" in arguments:
            checkout_dir = Path(arguments[arguments.index("-C") + 1])
            (checkout_dir / "docker-compose.yml").write_text(
                "services: {}\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(module, "_run_git", fake_run_git)

    compose = module._ensure_unmute_checkout(unmute_dir)

    assert compose == unmute_dir / "docker-compose.yml"
    assert compose.is_file()
    assert any(module._UNMUTE_REPOSITORY in call for call in calls)
    assert sum(module._UNMUTE_PIN in call for call in calls) == 2
    assert not unmute_dir.with_name("unmute.bootstrap").exists()


def test_invalid_nonempty_unmute_directory_is_not_overwritten(
    tmp_path: Path,
) -> None:
    module = _load_launcher_module()
    unmute_dir = tmp_path / "unmute"
    unmute_dir.mkdir()
    (unmute_dir / "local-file.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(RuntimeError, match="already exists and is not empty"):
        module._ensure_unmute_checkout(unmute_dir)

    assert (unmute_dir / "local-file.txt").read_text(encoding="utf-8") == "keep me"
