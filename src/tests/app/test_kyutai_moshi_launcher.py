from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.launcher.huggingface_token_store import save_huggingface_token

_TEST_TOKEN = "hf_" + "b" * 32


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_launcher_module() -> ModuleType:
    script = _repo_root() / "scripts" / "run_kyutai_moshi.py"
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


def test_compose_environment_uses_launcher_saved_token_and_safe_defaults(
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
    assert environment["KYUTAI_OMNIX_SECURE_ENTRYPOINT"].endswith(
        "/scripts/kyutai_moshi_secure_entrypoint.sh"
    )
    assert environment["OMNIX_KYUTAI_BUILD_JOBS"] == "2"
    assert environment["OMNIX_KYUTAI_UV_BUILD_JOBS"] == "1"
    assert environment["OMNIX_KYUTAI_UV_INSTALL_JOBS"] == "2"
    assert environment["OMNIX_KYUTAI_BUILD_NICE_LEVEL"] == "10"
    assert environment["OMNIX_KYUTAI_MEMORY_LIMIT"] == "16g"


def test_existing_image_starts_without_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_launcher_module()
    monkeypatch.setattr(module, "_docker_image_exists", lambda _environment: True)
    monkeypatch.delenv("KYUTAI_MOSHI_FORCE_REBUILD", raising=False)

    command, reason = module._startup_command(["docker", "compose"], {})

    assert command == ["docker", "compose", "up", "stt"]
    assert reason == "reusing existing Moshi image and container"


def test_missing_image_builds_once(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_launcher_module()
    monkeypatch.setattr(module, "_docker_image_exists", lambda _environment: False)
    monkeypatch.delenv("KYUTAI_MOSHI_FORCE_REBUILD", raising=False)

    command, reason = module._startup_command(["docker", "compose"], {})

    assert command == ["docker", "compose", "up", "--build", "stt"]
    assert reason == "Moshi image is missing"


def test_moshi_output_redacts_hugging_face_and_bearer_tokens() -> None:
    module = _load_launcher_module()
    fake_token = "hf_" + "K" * 32

    redacted = module._redact_line(
        f"uvx hf auth login --token {fake_token} HUGGING_FACE_HUB_TOKEN={fake_token} "
        f"Authorization: Bearer {fake_token}"
    )

    assert fake_token not in redacted
    assert redacted.count("[REDACTED]") >= 3


def test_vram_preflight_blocks_low_free_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    monkeypatch.setattr(module, "_gpu_vram_snapshot", lambda: (24_564, 21_000, 3_564))
    monkeypatch.setenv("KYUTAI_MOSHI_MIN_FREE_VRAM_MB", "6144")

    assert module._passes_vram_preflight() is False


def test_vram_preflight_allows_safe_free_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_launcher_module()
    monkeypatch.setattr(module, "_gpu_vram_snapshot", lambda: (24_564, 8_000, 16_564))
    monkeypatch.setenv("KYUTAI_MOSHI_MIN_FREE_VRAM_MB", "6144")

    assert module._passes_vram_preflight() is True


def test_gpu_snapshot_reads_first_nvidia_device(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_launcher_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/tools/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="24564, 7160, 17404\n",
        ),
    )

    assert module._gpu_vram_snapshot() == (24_564, 7_160, 17_404)


def test_secure_entrypoint_and_compose_persist_heavy_setup() -> None:
    root = _repo_root()
    entrypoint = (root / "scripts" / "kyutai_moshi_secure_entrypoint.sh").read_text(
        encoding="utf-8"
    )
    compose = (root / "docker-compose.kyutai-stt.yml").read_text(encoding="utf-8")

    assert "set -euo pipefail" in entrypoint
    assert "set -x" not in entrypoint
    assert "CARGO_BUILD_JOBS" in entrypoint
    assert "Reusing cached moshi-server" in entrypoint
    assert "omnix-kyutai-stt-venv:/app/moshi-server/.venv" in compose
    assert "omnix-kyutai-stt-cargo-install:/app/omnix-cargo-install" in compose
    assert "mem_limit: ${OMNIX_KYUTAI_MEMORY_LIMIT:-16g}" in compose
    assert "cpu_shares: 512" in compose
