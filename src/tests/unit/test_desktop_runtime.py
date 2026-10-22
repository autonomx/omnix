"""The desktop app's backend: environment contract, service boot, and the model services (roadmap §4.2, DT-3.3)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.desktop import env as desktop_env
from app.desktop import service_boot
from app.desktop.env import LaunchConfig, child_environment, service_environment
from app.desktop.services import ModelServices, plans
from app.models import catalog as model_catalog

ROOT = Path(__file__).resolve().parents[3]
SECRETS = {"OMNIXDESKTOP_DB_OWNER_PASSWORD": "owner-pw", "OMNIXDESKTOP_DB_APP_PASSWORD": "app-pw",
           "OMNIXDESKTOP_NOTIFY_SECRET": "notify"}


def _config(tmp_path: Path) -> LaunchConfig:
    return LaunchConfig(install_root=tmp_path / "install", data_dir=tmp_path / "data", http_port=43110,
                        pg_port=43111, metrics_port=43112, notify_port=43113,
                        service_ports={"stt": 43121, "tts": 43122, "image": 43123},
                        ffmpeg=tmp_path / "install" / "ffmpeg" / "ffmpeg.exe")


def _inherited() -> dict[str, str]:
    """A developer's shell: their Omnix's variables must not reach the desktop children."""
    return {**SECRETS, "PATH": "C:/dev/bin", "SystemRoot": "C:/Windows", "TEMP": "C:/Temp",
            "OMNIX_DATABASE_URL": "postgresql://dev@127.0.0.1:5432/omnix", "OMNIX_RUN_TOKEN_KEY": "dev-key",
            "OMNIX_AGENT_DEFAULT_REPOSITORY": "F:/LLM/omnix", "PYTHONPATH": "F:/LLM/omnix/src",
            "HF_HUB_CACHE": "C:/Users/dev/.cache/huggingface/hub", "OMNIX_LAUNCHER_KILL_PORT": "1"}


def test_the_gateway_environment_is_the_contract_and_nothing_inherited(tmp_path) -> None:
    config = _config(tmp_path)
    env = child_environment(config, _inherited(), owner=False)
    assert env["OMNIX_DATABASE_URL"] == "postgresql://omnix_app:app-pw@127.0.0.1:43111/omnix"
    assert "OMNIX_MIGRATION_DATABASE_URL" not in env and "OMNIX_RUN_TOKEN_KEY" not in env
    assert "OMNIX_AGENT_DEFAULT_REPOSITORY" not in env and "PYTHONPATH" not in env
    assert env["HF_HUB_CACHE"] == str(config.packs / "models")
    assert env["OMNIX_GATEWAY_TTS_HTTP"] == "1"  # the gateway has no Torch: TTS goes to the service
    assert env["OMNIX_TTS_URL"] == "http://127.0.0.1:43122" and env["OMNIX_STT_URL"] == "http://127.0.0.1:43121"
    assert env["OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT"] == "0"
    assert env["OMNIX_AGENT_ALLOW_UNSANDBOXED"] == "false"
    assert env["OMNIX_AGENT_RELAY_CONTAINER"] == desktop_env.SANDBOX_RELAY
    assert env["OMNIX_AGENT_BROKER_URL"] == "http://127.0.0.1:43110/api/agent-runs"
    assert env["OMNIX_FFMPEG"].endswith("ffmpeg.exe")
    assert env["OMNIX_ALLOWED_ORIGINS"] == "http://127.0.0.1:43110"
    assert not any(value == "owner-pw" for value in env.values())
    owner = child_environment(config, _inherited(), owner=True)
    assert owner["OMNIX_MIGRATION_DATABASE_URL"].startswith("postgresql://omnix_desktop_owner:owner-pw@")


def test_a_model_service_gets_only_what_it_needs(tmp_path) -> None:
    config = _config(tmp_path)
    sites = [config.packs / "runtimes" / "tts-windows-x64" / "site", config.packs / "runtimes" / "torch-windows-x64" / "site"]
    env = service_environment(config, "tts", service_token="svc-token", site_dirs=sites,
                              model_dir=config.packs / "models" / "snap", inherited=_inherited())
    assert env["OMNIX_SERVICE_TOKEN"] == "svc-token"
    assert env["OMNIX_DATABASE_URL"] == "postgresql://omnix_app:app-pw@127.0.0.1:43111/omnix"
    assert env["OMNIX_TTS_PORT"] == "43122" and env["OMNIX_LAUNCHER_KILL_PORT"] == "0"
    assert env["HF_HUB_OFFLINE"] == "1" and env["OMNIX_TTS_MODEL_DIR"].endswith("snap")
    assert env["OMNIX_DESKTOP_SITE_DIRS"].split(";" if sys.platform == "win32" else ":")[0].endswith(
        "tts-windows-x64" + ("\\" if sys.platform == "win32" else "/") + "site")
    for leaked in ("OMNIX_RUN_TOKEN_KEY", "OMNIX_MIGRATION_DATABASE_URL", "OMNIX_AGENT_DEFAULT_REPOSITORY", "PYTHONPATH"):
        assert leaked not in env
    assert not any(value in {"owner-pw", "notify"} for value in env.values())
    with pytest.raises(ValueError, match="service token"):
        service_environment(config, "tts", service_token="", site_dirs=sites, inherited=_inherited())


def test_service_boot_refuses_folders_outside_the_packs(tmp_path) -> None:
    packs = tmp_path / "packs"
    (packs / "runtimes" / "a" / "site").mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(service_boot.ServiceBootError, match="not inside the packs folder"):
        service_boot.pack_site_dirs({"OMNIX_PACKS_DIR": str(packs), "OMNIX_DESKTOP_SITE_DIRS": str(outside)})
    with pytest.raises(service_boot.ServiceBootError, match="is missing"):
        service_boot.pack_site_dirs({"OMNIX_PACKS_DIR": str(packs),
                                     "OMNIX_DESKTOP_SITE_DIRS": str(packs / "runtimes" / "b" / "site")})


def test_a_service_process_loads_nothing_from_the_gateways_packages(tmp_path) -> None:
    """With -S and service_boot, only the standard library, the app source and the packs are importable."""
    packs = tmp_path / "packs"
    overlay = packs / "runtimes" / "svc" / "site"
    layer = packs / "runtimes" / "torch" / "site"
    for folder, name, value in ((overlay, "shared_name", "overlay"), (layer, "shared_name", "layer"),
                                (layer, "layer_only", "layer")):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.py").write_text(f"WHERE = {value!r}\n", encoding="utf-8")
    probe = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from app.desktop import service_boot as b\n"
        "folders = b.pack_site_dirs()\n"
        "b.prepare(folders)\n"
        "import shared_name, layer_only\n"
        "try:\n"
        "    import pytest\n"
        "    gateway = True\n"
        "except ImportError:\n"
        "    gateway = False\n"
        "print(json.dumps({'shared': shared_name.WHERE, 'layer': layer_only.WHERE, 'gateway_package': gateway,\n"
        "                  'foreign': b.foreign_modules(folders, app_source=Path(sys.argv[1]))}))\n"
    )
    env = {"PATH": "", "SystemRoot": __import__("os").environ.get("SystemRoot", ""),
           "PYTHONPATH": str(ROOT / "src"), "OMNIX_PACKS_DIR": str(packs),
           "OMNIX_DESKTOP_SITE_DIRS": __import__("os").pathsep.join([str(overlay), str(layer)])}
    completed = subprocess.run([sys.executable, "-S", "-c", probe, str(ROOT / "src")], capture_output=True, text=True,
                               env=env, check=False, timeout=120)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["shared"] == "overlay"  # the overlay comes before the Torch layer
    assert result["layer"] == "layer"
    assert result["gateway_package"] is False  # pytest is in this interpreter's site-packages, not in a pack
    assert result["foreign"] == []


# --- The model services ---------------------------------------------------------------------------------------

REVISION = "0123456789abcdef0123456789abcdef01234567"
CATALOG = model_catalog.parse_catalog({
    "runtimes": {
        "torch-win": {"kind": "torch-layer", "platform": "windows-x64", "lock": "t", "files": "t.json"},
        "tts-win": {"kind": "overlay", "base": "torch-win", "platform": "windows-x64", "service": "tts",
                    "lock": "x", "files": "x.json"},
    },
    "bundles": {"voice-output": {"label": "Voice output", "capability": "tts", "variants": [
        {"platform": "windows-x64", "models": ["tts-model"], "runtimes": ["tts-win"], "min_commit_mb": 4096}]}},
    "models": {"tts-model": {"repo": "org/tts", "revision": REVISION, "service": "tts",
                             "files": {"m": {"sha256": "a" * 64, "size": 10}}}},
})


class _Process:
    def __init__(self) -> None:
        self.code: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.code or 0

    def kill(self) -> None:
        self.code = -9


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setattr(model_catalog, "current_platform", lambda: "windows-x64")
    monkeypatch.setattr("app.desktop.services.time.sleep", lambda seconds: None)
    config = _config(tmp_path)
    for name in SECRETS:
        monkeypatch.setenv(name, SECRETS[name])
    state = SimpleNamespace(events=[], launched=[], free=True, commit=64 * 2**30, healthy=True)

    def launch(command, **kwargs):
        process = _Process()
        state.launched.append((command, kwargs["env"], process))
        return process

    manager = ModelServices(config, python="python", service_token=lambda: "svc-token", emit=state.events.append,
                            logs=tmp_path / "logs", app_source=ROOT / "src", catalog=CATALOG,
                            port_free=lambda port: state.free, available_commit=lambda: state.commit,
                            launch=launch, healthy=lambda port: state.healthy)
    installed: dict[str, Any] = {"runtimes": set(), "models": set()}
    manager.runtimes = SimpleNamespace(current=lambda rid: rid in installed["runtimes"],
                                       site=lambda rid: config.packs / "runtimes" / rid / "site")
    manager.models = SimpleNamespace(installed=lambda mid: mid in installed["models"],
                                     snapshot=lambda mid: config.packs / "models" / mid)
    state.install = lambda: (installed["runtimes"].update({"torch-win", "tts-win"}), installed["models"].add("tts-model"))
    state.uninstall = lambda: (installed["runtimes"].clear(), installed["models"].clear())
    return manager, state


def _states(state) -> list[tuple[str, str]]:
    return [(event["service"], event["state"]) for event in state.events]


def test_a_service_starts_once_its_bundle_is_installed_and_reports_running_when_healthy(services) -> None:
    manager, state = services
    manager.reconcile()
    assert state.launched == []
    state.install()
    state.healthy = False
    manager.reconcile()
    command, env, _ = state.launched[0]
    assert command == ["python", "-S", "-m", "app.desktop.service_boot", "tts"]
    assert env["OMNIX_TTS_PORT"] == "43122" and env["OMNIX_SERVICE_TOKEN"] == "svc-token"
    assert env["OMNIX_TTS_MODEL_DIR"].endswith("tts-model")
    manager.reconcile()
    assert _states(state) == [("tts", "starting")]
    state.healthy = True
    manager.reconcile()
    assert _states(state)[-1] == ("tts", "running")


def test_a_busy_port_is_reported_never_killed(services) -> None:
    manager, state = services
    state.install()
    state.free = False
    manager.reconcile()
    assert state.launched == [] and _states(state) == [("tts", "blocked")]
    assert "port 43122 is in use" in state.events[-1]["message"]
    state.free = True
    manager.reconcile()
    assert len(state.launched) == 1


def test_too_little_memory_blocks_the_start(services) -> None:
    manager, state = services
    state.install()
    state.commit = 2 * 2**30
    manager.reconcile()
    assert state.launched == [] and "not enough memory" in state.events[-1]["message"]


def test_a_crashing_service_is_restarted_three_times_then_failed(services) -> None:
    manager, state = services
    state.install()
    manager.reconcile()
    for _ in range(3):
        state.launched[-1][2].code = 1
        manager.reconcile()
    assert len(state.launched) == 4
    state.launched[-1][2].code = 1
    manager.reconcile()
    assert _states(state)[-1] == ("tts", "failed")
    manager.reconcile()
    assert len(state.launched) == 4  # failed stays failed until its packs change


def test_removing_the_bundle_stops_its_service(services) -> None:
    manager, state = services
    state.install()
    manager.reconcile()
    process = state.launched[0][2]
    state.uninstall()
    manager.reconcile()
    assert process.terminated and _states(state)[-1] == ("tts", "stopped")


def test_plans_use_the_measured_requirement(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(model_catalog, "current_platform", lambda: "windows-x64")
    config = _config(tmp_path)
    runtimes = SimpleNamespace(current=lambda rid: True, site=lambda rid: config.packs / rid)
    models = SimpleNamespace(installed=lambda mid: True, snapshot=lambda mid: config.packs / "m" / mid)
    found = plans(config, CATALOG, runtimes, models)
    assert found["tts"].needed_bytes == 4096 * 2**20
    assert [path.name for path in found["tts"].site_dirs] == ["tts-win", "torch-win"]
