"""Standalone Omnix-compatible Kyutai streaming STT runtime."""
from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from app.providers.kyutai_live_stt import KyutaiLiveSttProvider
from app.providers.kyutai_stt_websocket import install_kyutai_stt_websocket

app = FastAPI(title="Omnix Kyutai Live STT", version="1.0")
provider = KyutaiLiveSttProvider()
install_kyutai_stt_websocket(app, provider=provider)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    language = os.environ.get("OMNIX_LIVE_STT_LANGUAGE", "en")
    probe_max_age = float(os.environ.get("KYUTAI_STT_HEALTH_PROBE_MAX_AGE_SECONDS", "5"))
    upstream_ready = await provider.probe(language=language, max_age_seconds=probe_max_age)
    health = dict(await provider.health())
    return {
        "ok": upstream_ready and health.get("state") == "closed",
        **health,
        "upstream_ready": upstream_ready,
    }


def main() -> None:
    port = int(os.environ.get("OMNIX_STT_PORT", "5202"))
    print(f"[STT] Starting Kyutai adapter on http://0.0.0.0:{port}")
    print(f"[STT] Upstream Kyutai service: {provider.base_url}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
