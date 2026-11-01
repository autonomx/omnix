"""EV-13's first audio: how soon a final response is heard, through the RPG's speech routes and the speech service.

The voice routes are served over HTTP (as the page reaches them), so a sentence's audio arrives as it is streamed.
For each response, from the moment its final text shows: its speech plan (``/speech-plan``), then its sentences'
audio in their speakers' cast voices (``/speech-audio``: every text is new, so streamed from the speech service), each
asked for when the one before has arrived, as the page does. Its playback is simulated as the page's player does it:
it starts once ``START_BUFFER_S`` is buffered (the response's first audio, what the target counts; the page's own audio
set-up is not in it), and when it runs dry waits until ``REBUFFER_S`` is buffered (the waits are counted). A sentence
that used up its token budget is counted as a runaway: the model failing to stop, not speech. Responses are prose of an Aurelia campaign (its world's own
passages), two in three spoken by the narrator, the rest by someone of the campaign; the turns use the scripted model.
After one warm-up sentence. Then each first sentence once more, from the campaign's audio cache.

Target (roadmap §6, EV-13): p95 ≤ 1.5 s (starting target). Run against a speech service you started for it, with
``OMNIX_TTS_URL`` and ``OMNIX_SERVICE_TOKEN`` set to its address and token, and ``OMNIX_GATEWAY_TTS_HTTP=1``:

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> OMNIX_TTS_URL=http://127.0.0.1:5101 \\
        OMNIX_SERVICE_TOKEN=... OMNIX_GATEWAY_TTS_HTTP=1 python scripts/rpg_first_audio_eval.py \\
        --allow-database <db> --output docs/measurements/rpg-first-audio-<date>.json
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import threading
import time
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.conversation.tts_stream_contract import estimate_chat_stream_max_new_tokens  # noqa: E402
from tests.rehearsal.rpg import worlds  # noqa: E402

START_BUFFER_S = 0.4  # the page's player starts once this much is buffered (``rpgSpeechSink.ts``)
REBUFFER_S = 0.75  # and, having run dry, resumes once this much is
BYTES_PER_SECOND = 24_000 * 2  # mono PCM16 at the service's rate
CODEC_STEPS_PER_SECOND = 12.5  # as the voice route counts a runaway
RUNAWAY_FRACTION = 0.95


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def quantile(values: list[float], q: float) -> float | None:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1) if ordered else None


def texts(document: dict[str, Any], count: int) -> list[str]:
    """Prose of the campaign, each once: every passage of its world (descriptions, lore, quests' and items' text)
    long enough to be a response, in the world's own order."""
    from app.apps.rpg.foundation.state import access as sections

    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            text = " ".join(value.split())
            if 60 <= len(text) <= 600 and text[-1] in ".!?\"”" and " " in text and text not in found:
                found.append(text)

    walk(sections.world_model_of(_d(sections.simulation_state_of(document))))
    return found[:count]


def serve_voice_routes() -> str:
    """The campaign's voice routes on a local HTTP server in this process; its base URL."""
    import uvicorn
    from fastapi import FastAPI

    from app.apps.rpg.edge.api.feature_routes.rpg_voice_routes import register_rpg_voice_routes
    from tests.support.routers import include_router_registrar

    app = FastAPI()
    include_router_registrar(app, register_rpg_voice_routes)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            return f"http://127.0.0.1:{port}"
        time.sleep(0.05)
    raise SystemExit("the voice routes did not start")


def heard(client: httpx.Client, base: str, speaker: str, text: str) -> dict[str, Any]:
    """A response spoken as the page speaks it: arrivals (time, bytes so far) from its plan's request."""
    started = time.perf_counter()
    plan = client.post(f"{base}/speech-plan", json={"blocks": [{"speaker_id": speaker, "text": text}]}).json()
    arrivals: list[tuple[float, int]] = []
    received = 0
    statuses = []
    runaways = 0
    for segment in plan["segments"]:
        for sentence in segment["sentences"]:
            with client.stream("POST", f"{base}/speech-audio",
                               json={"speaker_id": segment["speaker_id"], "text": sentence}) as answer:
                statuses.append(answer.status_code)
                if answer.status_code != 200:
                    break
                before = received
                for piece in answer.iter_bytes():
                    received += len(piece)
                    arrivals.append((time.perf_counter() - started, received))
                budget = estimate_chat_stream_max_new_tokens(sentence)
                runaways += (received - before) / BYTES_PER_SECOND >= RUNAWAY_FRACTION * budget / CODEC_STEPS_PER_SECOND
    first = arrivals[0][0] if arrivals else None
    played = playback(arrivals)
    return {"speaker_id": speaker, "voice_id": plan["segments"][0]["voice_id"], "chars": len(text),
            "sentences": sum(len(segment["sentences"]) for segment in plan["segments"]),
            "first_sentence": plan["segments"][0]["sentences"][0], "statuses": statuses,
            "first_byte_ms": round(first * 1000, 1) if first is not None else None,
            "first_audio_ms": played.get("start_ms"), "runaways": runaways,
            "audio_s": round(received / BYTES_PER_SECOND, 2), **played}


def playback(arrivals: list[tuple[float, int]]) -> dict[str, Any]:
    """The page's player over these arrivals: it starts once ``START_BUFFER_S`` is buffered (or all has arrived) and
    plays on; when it has played all that has arrived it waits (a wait) until ``REBUFFER_S`` is buffered or all has
    arrived. (The worklet lengthens its rebuffer after each wait, up to 1.5 s: a real second wait may be longer.)"""
    if not arrivals:
        return {"waits": 0, "waited_ms": 0.0}
    total = arrivals[-1][1] / BYTES_PER_SECOND
    start = next(at for at, got in arrivals if got / BYTES_PER_SECOND >= min(START_BUFFER_S, total))
    available = max(got for at, got in arrivals if at <= start) / BYTES_PER_SECOND
    clock, played, waits, waited, dry = start, 0.0, 0, 0.0, False
    for at, got in arrivals:
        if at <= start:
            continue
        if not dry:
            step = min(at - clock, available - played)  # played until this piece came, or until it ran dry
            played += step
            clock += step
            if clock < at:
                waits += 1
                dry = True
        available = got / BYTES_PER_SECOND
        if dry and (available - played >= REBUFFER_S or got == arrivals[-1][1]):
            waited += at - clock
            clock = at
            dry = False
    return {"waits": waits, "waited_ms": round(waited * 1000, 1), "start_ms": round(start * 1000, 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--responses", type=int, default=100)
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["OMNIX_RPG_TURNS_PER_HOUR"] = "0"
    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    from app.persistence.database import default_database
    from app.settings.access import install_database_settings_service

    install_database_settings_service(default_database())  # the speech provider's settings, as the gateway has them
    model = worlds.install_scripted_model()
    session_id = worlds.launch("aurelia")
    model.session_id = session_id
    base = f"{serve_voice_routes()}/api/rpg/sessions/{session_id}"
    client = httpx.Client(timeout=120, headers={"X-Omnix-Client": "rpg-harness"})
    cast = client.get(f"{base}/voices")
    if cast.status_code != 200:
        raise SystemExit(f"the cast did not load: {cast.status_code} {cast.text[:300]}")
    people = [row["speaker_id"] for row in cast.json()["cast"] if row["speaker_id"] != "narrator"]
    speakers = ["narrator", *people] if people else ["narrator"]
    warm = client.post(f"{base}/speech-audio", json={"speaker_id": "narrator", "text": "The road is quiet."})
    if warm.status_code != 200:
        raise SystemExit(f"the speech service did not answer: {warm.status_code} {warm.text[:200]}")
    rows = []
    for index, text in enumerate(texts(worlds.load(session_id), args.responses)):
        speaker = speakers[index % len(speakers)] if index % 3 else "narrator"  # two in three by the narrator
        rows.append(heard(client, base, speaker, text))
    replay = []
    for row in rows:
        started = time.perf_counter()
        again = client.post(f"{base}/speech-audio", json={"speaker_id": row["speaker_id"], "text": row["first_sentence"]})
        replay.append({"cache": again.headers.get("X-Omnix-Speech-Cache"),
                       "ms": round((time.perf_counter() - started) * 1000, 1)})
    ok = [row for row in rows if row["first_audio_ms"] is not None and set(row["statuses"]) == {200}]
    first = [row["first_audio_ms"] for row in ok]
    by_voice = {voice: {"responses": len(group), "p50": quantile(group, 0.5), "p95": quantile(group, 0.95)}
                for voice in sorted({row["voice_id"] for row in ok})
                for group in [[row["first_audio_ms"] for row in ok if row["voice_id"] == voice]]}
    summary = {
        "responses": len(rows), "failed": len(rows) - len(ok),
        "first_audio_ms": {"p50": quantile(first, 0.5), "p95": quantile(first, 0.95), "max": max(first, default=None),
                           "mean": round(statistics.mean(first), 1) if first else None},
        "by_voice": by_voice,
        "runaways": sum(row["runaways"] for row in ok),
        "first_byte_ms_p95": quantile([row["first_byte_ms"] for row in ok], 0.95),
        "playback": {"responses_with_a_wait": sum(row["waits"] > 0 for row in ok),
                     "waits": sum(row["waits"] for row in ok),
                     "waited_ms_p95": quantile([row["waited_ms"] for row in ok], 0.95),
                     "audio_s_total": round(sum(row["audio_s"] for row in ok), 1)},
        "from_cache_ms": {"p50": quantile([row["ms"] for row in replay], 0.5),
                          "p95": quantile([row["ms"] for row in replay], 0.95),
                          "hits": sum(row["cache"] == "hit" for row in replay)},
    }
    summary["passed"] = bool(first) and not summary["failed"] and summary["first_audio_ms"]["p95"] <= 1500
    service = os.environ.get("OMNIX_TTS_URL", "")
    health = _d(httpx.get(f"{service.rstrip('/')}/health", timeout=5).json()) if service else {}
    result = {"schema_version": 2, "measurement": "RPG first audio after a final response (EV-13)",
              "measured_on": date.today().isoformat(), "world": "aurelia",
              "transport": "the RPG's /speech-audio over HTTP: PCM16 streamed from the speech service's live-call stream",
              "speech_service": {"url": service, "provider": health.get("provider"),
                                 "model": _d(health.get("details")).get("configured_model"),
                                 "device": _d(health.get("gpu")).get("device")},
              "target": "first audio p95 <= 1500 ms (starting target)", **summary, "rows": rows}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
