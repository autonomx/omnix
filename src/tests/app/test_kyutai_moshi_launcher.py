from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from app.launcher.huggingface_token_store import save_huggingface_token

_TEST_TOKEN = "hf_" + "b" * 32


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


def test_compose_environment_uses_launcher_saved_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_launcher_module()
    root = tmp_path / "omnix"
    root.mkdir()
    secret_dir = tmp_path / "private"
    monkeypatch.setenv("OMNIX_LAUNCHER_SECRET_DIR", str(secret_dir))
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    save_huggingface_token(_TEST_TOKEN, root)

    environment = module._compose_environment(root)

    assert environment["HUGGING_FACE_HUB_TOKEN"] == _TEST_TOKEN


def test_existing_moshi_image_is_reused_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    monkeypatch.delenv("KYUTAI_MOSHI_FORCE_REBUILD", raising=False)
    monkeypatch.setattr(module, "_docker_image_exists", lambda _environment: True)
    base = ["docker", "compose", "-f", "compose.yml"]

    command, reason = module._startup_command(base, {})

    assert command == [*base, "up", "stt"]
    assert reason == "reusing existing Moshi image and container"


def test_missing_moshi_image_triggers_initial_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    monkeypatch.delenv("KYUTAI_MOSHI_FORCE_REBUILD", raising=False)
    monkeypatch.setattr(module, "_docker_image_exists", lambda _environment: False)
    base = ["docker", "compose", "-f", "compose.yml"]

    command, reason = module._startup_command(base, {})

    assert command == [*base, "up", "--build", "stt"]
    assert reason == "Moshi image is missing"


def test_force_rebuild_overrides_existing_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    monkeypatch.setenv("KYUTAI_MOSHI_FORCE_REBUILD", "1")
    monkeypatch.setattr(module, "_docker_image_exists", lambda _environment: True)
    base = ["docker", "compose", "-f", "compose.yml"]

    command, reason = module._startup_command(base, {})

    assert command == [*base, "up", "--build", "stt"]
    assert reason == "forced rebuild requested"


def test_docker_image_check_uses_configured_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    calls: list[list[str]] = []
    monkeypatch.setenv("KYUTAI_MOSHI_IMAGE", "custom/moshi:test")

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._docker_image_exists({}) is True
    assert calls == [["docker", "image", "inspect", "custom/moshi:test"]]
