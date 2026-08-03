"""Standalone Omnix-compatible Kyutai streaming STT runtime."""
from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.providers.kyutai_authority import (
    evaluate_kyutai_authority,
    parse_authority_mode,
)
from app.providers.kyutai_live_stt import KyutaiLiveSttProvider
from app.providers.kyutai_stt_websocket import install_kyutai_stt_websocket

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
provider = KyutaiLiveSttProvider()
install_kyutai_stt_websocket(app, provider=provider)


async def _probed_health(language: str, *, force: bool = False) -> dict[str, object]:
    probe_max_age = float(os.environ.get("KYUTAI_STT_HEALTH_PROBE_MAX_AGE_SECONDS", "5"))
    upstream_ready = await provider.probe(
        language=language,
        max_age_seconds=0.0 if force else probe_max_age,
    )
    health = dict(await provider.health())
    return {
        "ok": upstream_ready and health.get("state") == "closed",
        **health,
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
        **decision.payload(),
    }


def main() -> None:
    port = int(os.environ.get("OMNIX_STT_PORT", "5202"))
    print(f"[STT] Starting Kyutai adapter on http://0.0.0.0:{port}")
    print(f"[STT] Upstream Kyutai service: {provider.base_url}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()