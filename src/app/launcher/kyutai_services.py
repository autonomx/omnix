from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from app.launcher.service_manager import ServiceSpec


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def build_kyutai_service_specs(root: Path) -> tuple[list[ServiceSpec], str]:
    enabled = _flag("OMNIX_KYUTAI_ENABLED", "1")
    moshi_auto_start = enabled and _flag("OMNIX_START_KYUTAI_MOSHI", "1")
    adapter_auto_start = enabled and _flag("OMNIX_START_KYUTAI_ADAPTER", "1")

    app_python = os.environ.get(
        "KYUTAI_STT_PYTHON",
        os.environ.get(
            "RPG_FLUX_PYTHON",
            r"C:\Users\unx47\miniconda3\envs\rpg-flux\python.exe",
        ),
    )
    unmute_dir = Path(
        os.environ.get("KYUTAI_UNMUTE_DIR", str(root.parent / "unmute"))
    ).expanduser()
    upstream_url = os.environ.get("KYUTAI_STT_URL", "ws://127.0.0.1:8090")
    upstream_path = os.environ.get("KYUTAI_STT_PATH", "/api/asr-streaming")
    adapter_port = int(os.environ.get("OMNIX_KYUTAI_STT_PORT", "5202"))
    language = os.environ.get("OMNIX_LIVE_STT_LANGUAGE", "en")
    endpoint_threshold = os.environ.get("KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD", "0.75")
    fallback_url = os.environ.get("OMNIX_STT_URL", "http://127.0.0.1:5201")
    browser_stt_url = os.environ.get(
        "VITE_ASSISTANT_STT_URL",
        (
            f"http://127.0.0.1:{adapter_port}"
            f"?language={quote(language)}"
            f"&authority=test"
            f"&endpoint_threshold={quote(endpoint_threshold)}"
            f"&fallback={quote(fallback_url, safe='')}"
        ),
    )

    shared_env = {
        "PYTHONPATH": str(root / "src"),
        "KYUTAI_UNMUTE_DIR": str(unmute_dir),
        "KYUTAI_OMNIX_COMPOSE_FILE": str(root / "docker-compose.kyutai-stt.yml"),
        "KYUTAI_STT_URL": upstream_url,
        "KYUTAI_STT_PATH": upstream_path,
        "OMNIX_STT_PORT": str(adapter_port),
        "OMNIX_LIVE_STT_LANGUAGE": language,
        "KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD": endpoint_threshold,
    }

    specs = [
        ServiceSpec(
            service_id="kyutai_moshi",
            label="Kyutai moshi-server",
            command=[app_python, str(root / "scripts" / "run_kyutai_moshi.py")],
            cwd=root,
            env=dict(shared_env),
            optional=True,
            enabled=enabled,
            auto_start=moshi_auto_start,
            description=(
                "Kyutai ASR upstream in Docker on 127.0.0.1:8090. "
                f"Pinned Unmute checkout: {unmute_dir}."
            ),
        ),
        ServiceSpec(
            service_id="kyutai_stt",
            label="Kyutai STT Adapter",
            command=[app_python, str(root / "src" / "kyutai_stt_runtime.py")],
            cwd=root,
            env=dict(shared_env),
            ports=(adapter_port,),
            optional=True,
            enabled=enabled,
            auto_start=adapter_auto_start,
            description=(
                f"Omnix live-STT adapter on 127.0.0.1:{adapter_port}; "
                f"streams to moshi-server on 127.0.0.1:8090{upstream_path}."
            ),
        ),
    ]
    return specs, browser_stt_url
