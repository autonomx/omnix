"""Standalone Omnix-compatible Kyutai streaming STT runtime."""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import httpx
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.providers.kyutai_authority import (
    evaluate_kyutai_authority,
    parse_authority_mode,
)
from app.providers.kyutai_live_stt import KyutaiLiveSttProvider
from app.providers.kyutai_stt_websocket import install_kyutai_stt_websocket
from app.providers.kyutai_transcript_normalization import (
    install_kyutai_transcript_normalization,
)

# Endpoint candidates are hints, not commits. Expose them below the 0.75
# authoritative commit threshold so the browser can start private LLM/TTS work
# while its endpoint-fusion policy still decides whether to continue or commit.
DEFAULT_ENDPOINT_CANDIDATE_THRESHOLD = 0.35
os.environ.setdefault(
    "KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD",
    str(DEFAULT_ENDPOINT_CANDIDATE_THRESHOLD),
)

install_kyutai_transcript_normalization()

app = FastAPI(title="Omnix Kyutai Live STT", version="1.0")
origins = [
    item.strip()
    for item in os.environ.get(
        "OMNIX_STT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
provider = KyutaiLiveSttProvider(
    path=os.environ.get("KYUTAI_STT_PATH", "/api/asr-streaming"),
)
install_kyutai_stt_websocket(app, provider=provider)


def _moshi_build_info_url() -> str:
    parsed = urlsplit(provider.base_url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    return urlunsplit((scheme, parsed.netloc, "/api/build_info", "", ""))


async def _moshi_http_ready() -> tuple[bool, str | None, str | None]:
    timeout = float(os.environ.get("KYUTAI_STT_BUILD_INFO_TIMEOUT_SECONDS", "2"))
    try:
        async with httpx.AsyncClient(timeout=max(0.25, timeout)) as client:
            response = await client.get(_moshi_build_info_url())
    except httpx.TimeoutException as exc:
        return False, "upstream_connect_timeout", type(exc).__name__
    except httpx.ConnectError as exc:
        return False, "upstream_connection_refused", type(exc).__name__
    except httpx.HTTPError as exc:
        return False, "upstream_service_unavailable", type(exc).__name__

    if response.status_code == 200:
        return True, None, None
    if response.status_code in {401, 403}:
        return False, "upstream_auth_rejected", f"HTTP{response.status_code}"
    if response.status_code == 404:
        return False, "upstream_endpoint_not_found", "HTTP404"
    if response.status_code == 429:
        return False, "upstream_rate_limited", "HTTP429"
    return False, "upstream_service_unavailable", f"HTTP{response.status_code}"


async def _probed_health(language: str, *, force: bool = False) -> dict[str, object]:
    http_ready, startup_error_code, startup_error_type = await _moshi_http_ready()
    health = dict(await provider.health())
    if not http_ready:
        return {
            "ok": False,
            **health,
            "http_ready": False,
            "upstream_ready": False,
            "last_error": "Moshi /api/build_info is not ready yet.",
            "last_error_code": startup_error_code,
            "last_error_type": startup_error_type,
            "last_error_stage": "build_info",
        }

    probe_max_age = float(os.environ.get("KYUTAI_STT_HEALTH_PROBE_MAX_AGE_SECONDS", "5"))
    upstream_ready = await provider.probe(
        language=language,
        max_age_seconds=0.0 if force else probe_max_age,
    )
    health = dict(await provider.health())
    return {
        "ok": upstream_ready and health.get("state") == "closed",
        **health,
        "http_ready": True,
        "upstream_ready": upstream_ready,
    }


@app.get("/healthz")
async def healthz(
    force: bool = Query(default=False),
) -> dict[str, object]:
    language = os.environ.get("OMNIX_LIVE_STT_LANGUAGE", "en")
    return await _probed_health(language, force=force)


@app.get("/authorityz")
async def authorityz(
    language: str = Query(default="en", min_length=2, max_length=16),
    mode: str = Query(default="observational", max_length=24),
    force: bool = Query(default=False),
) -> dict[str, object]:
    resolved_mode = parse_authority_mode(mode)
    health = await _probed_health(language, force=force)
    decision = evaluate_kyutai_authority(
        health,
        language=language,
        mode=resolved_mode,
    )
    return {
        "ok": decision.eligible,
        "provider": "kyutai",
        "http_ready": bool(health.get("http_ready")),
        **decision.payload(),
    }


def main() -> None:
    port = int(os.environ.get("OMNIX_STT_PORT", "5202"))
    print(f"[STT] Starting Kyutai adapter on http://0.0.0.0:{port}")
    print(f"[STT] Upstream Kyutai service: {provider.base_url}")
    print(f"[STT] Upstream Kyutai path: {provider.path}")
    print(
        "[STT] Endpoint candidate threshold: "
        f"{os.environ.get('KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD')}"
    )
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
