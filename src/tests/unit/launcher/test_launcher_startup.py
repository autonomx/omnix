"""The Python launcher owns starting Omnix; the wrappers only call it (WP-11.4)."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from app.composition.launcher import __main__ as launcher_main
from app.composition.launcher import startup
from app.composition.launcher.config import LauncherConfig

ROOT = Path(__file__).resolve().parents[4]


def test_fixed_service_urls_are_set_and_defaults_yield_to_an_operator_value(tmp_path) -> None:
    env = {"OMNIX_TTS_URL": "http://elsewhere:1", "OMNIX_LIVE_AGENT_ENABLED": "0", "OMNIX_IMAGE_ENABLED": "0"}

    startup.apply_launcher_environment(tmp_path, env)

    assert env["OMNIX_TTS_URL"] == "http://127.0.0.1:5101"
    assert env["OMNIX_LAUNCHER_URL"] == "http://127.0.0.1:5055"
    assert env["OMNIX_LIVE_AGENT_ENABLED"] == "0"
    assert env["HERMES_ENABLED"] == "1" and env["OMNIX_LIVE_AGENT_REQUIRE_HERMES"] == "1"
    # Agent debug logs are opt-in (WP-10.1).
    assert env["OMNIX_AGENT_DEBUG_LOGS"] == "0"
    assert env["OMNIX_AGENT_LOG_DIR"] == str(tmp_path / "resources" / "logs" / "agent")
    assert env["OMNIX_BLOB_ROOT"] == str((tmp_path.parent / "omnix-runtime" / "blobs").resolve())
    assert env["OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS"] == "420"
    assert env["OMNIX_IMAGE_URL"] == ""
    assert env["OMNIX_TTS_MODEL_DIR"] == ""


def test_the_image_service_and_tts_model_follow_what_is_enabled_and_installed(tmp_path) -> None:
    model = tmp_path / "resources" / "models" / "tts" / "Qwen3-TTS-12Hz-0.6B-Base"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    (model / "preprocessor_config.json").write_text("{}")
    env: dict[str, str] = {}

    startup.apply_launcher_environment(tmp_path, env)

    assert env["OMNIX_IMAGE_URL"] == "http://127.0.0.1:5301"
    assert env["OMNIX_TTS_MODEL_DIR"] == env["OMNIX_QWEN3_TTS_MODEL_DIR"] == str(model)


class _Docker:
    def __init__(self, *, info=0, running="false", exists=True, healthy_after=2):
        self.calls = []
        self.info, self.running, self.exists, self.healthy_after = info, running, exists, healthy_after

    def __call__(self, command, **_kwargs):
        self.calls.append(command[1:])
        args = command[1:]
        if args[0] == "info":
            return subprocess.CompletedProcess(command, self.info, "", "")
        if args[0] == "inspect" and "{{.State.Running}}" in args:
            return subprocess.CompletedProcess(command, 0 if self.exists else 1, self.running, "")
        if args[0] == "start":
            return subprocess.CompletedProcess(command, 0, "", "")
        polls = sum(1 for call in self.calls if "{{.State.Health.Status}}" in call)
        return subprocess.CompletedProcess(command, 0, "healthy" if polls >= self.healthy_after else "starting", "")


def test_an_existing_postgres_container_is_started_and_waited_for() -> None:
    docker = _Docker()
    assert startup.ensure_postgres_container("omnix-postgres", run=docker, sleep=lambda _s: None, say=lambda _m: None) is None
    assert ["start", "omnix-postgres"] in docker.calls


@pytest.mark.parametrize(
    ("docker", "message"),
    [
        (_Docker(info=1), "Docker Desktop is not running"),
        (_Docker(exists=False), "Provision it with docker-compose.postgres.yml"),
        (_Docker(running="true", healthy_after=99), "did not become healthy"),
    ],
)
def test_postgres_problems_are_named(docker, message) -> None:
    error = startup.ensure_postgres_container("omnix-postgres", attempts=3, run=docker, sleep=lambda _s: None, say=lambda _m: None)
    assert message in error


def test_a_missing_voice_runtime_warns_and_a_wrong_python_fails(tmp_path) -> None:
    tts = tmp_path / "tts.exe"
    tts.write_text("")
    config = LauncherConfig(conda_root=tmp_path, environments={"app": "a", "tts": "t", "stt": "s"},
                            pythons={"tts": str(tts), "stt": str(tmp_path / "missing.exe")})

    errors, warnings = startup.interpreter_problems(
        config, run=lambda *_a, **_k: subprocess.CompletedProcess([], 1, "", "3.10")
    )

    assert errors == [f"the TTS runtime must be Python 3.11: {tts}. Run setup again."]
    assert len(warnings) == 1 and "STT runtime is missing" in warnings[0]


@pytest.fixture
def steps(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(startup, "launcher_already_running", lambda _port=5055: False)
    monkeypatch.setattr(startup, "interpreter_problems", lambda _config: ([], []))
    monkeypatch.setattr(startup, "apply_launcher_environment", lambda _root: {})
    monkeypatch.setattr(startup, "ensure_postgres_container", lambda name, **_k: calls.append(f"container:{name}"))
    monkeypatch.setattr(launcher_main, "_module", lambda *args: calls.append(" ".join(args)) or 0)
    monkeypatch.setattr(launcher_main, "_say", lambda *_a, **_k: None)
    return calls


def _args(**overrides) -> argparse.Namespace:
    values = {"gateway_url": "http://127.0.0.1:8000", "startup_timeout": None, "postgres_container": "omnix-postgres",
              "postgres_only": False, "check": False}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_the_check_stops_after_the_database_health_check(steps) -> None:
    assert launcher_main.start(_args(check=True)) == 0
    assert steps == ["container:omnix-postgres", "app.persistence health"]


def test_postgres_only_starts_only_the_container(steps) -> None:
    assert launcher_main.start(_args(postgres_only=True)) == 0
    assert steps == ["container:omnix-postgres"]


def test_migrations_run_after_the_health_check_and_before_any_service(steps, monkeypatch) -> None:
    served = []
    monkeypatch.setattr(launcher_main.threading, "Thread", lambda **_k: type("T", (), {"start": lambda self: served.append("autostart")})())
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: served.append("dashboard"))
    monkeypatch.setattr("app.runtime.net.bind_host", lambda: "127.0.0.1")

    assert launcher_main.start(_args()) == 0
    assert steps == ["container:omnix-postgres", "app.persistence health", "app.persistence migrate"]
    assert served == ["autostart", "dashboard"]


def test_a_second_launcher_is_refused_before_anything_starts(steps, monkeypatch) -> None:
    monkeypatch.setattr(startup, "launcher_already_running", lambda _port=5055: True)
    assert launcher_main.start(_args()) == 1
    assert steps == []


def test_the_wrappers_only_call_the_python_launcher() -> None:
    batch = (ROOT / "start_all.bat").read_text(encoding="utf-8")
    shell = (ROOT / "start_all.sh").read_text(encoding="utf-8")

    assert '-m app.composition.launcher start --postgres-container "%OMNIX_POSTGRES_CONTAINER%"' in batch
    assert 'exec "$RPG_FLUX_PYTHON" -m app.composition.launcher start' in shell
    # The Windows wrapper keeps only the protected credential hand-off.
    assert "manage_postgresql_credential.ps1" in batch and "-Action launch" in batch
    for moved in ("uvicorn", "docker", "app.persistence", "Invoke-WebRequest", "HERMES_ENABLED"):
        assert moved not in batch, moved
