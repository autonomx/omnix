"""CPU-only stand-ins for the model services in the multi-host topology (WP-6.8).

One process serves:

* an LM Studio compatible chat API (OpenAI ``/v1/chat/completions`` and the
  native ``/api/v0`` variant, streaming and non-streaming) with a fixed reply;
* the remote TTS API the gateway calls (``/health``, ``/api/tts/speakers``,
  streaming PCM ``/api/tts/live-call/stream`` and WAV
  ``/api/tts/generate_stream_audio``).

Run: ``python scripts/multihost/fake_model_service.py --port 8020``.
"""
from __future__ import annotations

import argparse
import io
import json
import time
import wave
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

REPLY = "Multi-host topology reply."
MODEL = "omnix-fake-model"

app = FastAPI(title="Omnix fake model service")


def _completion(stream: bool) -> Any:
    created = int(time.time())
    if not stream:
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": created,
            "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }

    def events():
        for index, word in enumerate(REPLY.split(" ")):
            chunk = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": created,
                "model": MODEL,
                "choices": [{"index": 0, "delta": {"content": (" " if index else "") + word}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        final = {
            "id": "chatcmpl-fake",
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }
        yield f"data: {json.dumps(final)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
@app.post("/api/v0/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    return _completion(bool(body.get("stream")))


@app.get("/v1/models")
@app.get("/api/v0/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "type": "llm", "state": "loaded"}]}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "status": "ready", "details": {"mode": "multihost_fake"}}


@app.get("/api/tts/speakers")
def speakers() -> dict[str, Any]:
    return {"speakers": ["default"]}


@app.post("/api/tts/live-call/stream")
def live_call_stream() -> Response:
    """Streaming PCM16 contract used by the gateway's remote TTS client."""
    return Response(
        bytes.fromhex("0020 00e0") * 2400,
        media_type="application/octet-stream",
        headers={"X-Omnix-Audio-Format": "pcm_s16le", "X-Omnix-Channels": "1", "X-Omnix-Sample-Rate": "24000"},
    )


@app.post("/api/tts/generate_stream_audio")
def synthesize() -> Response:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x20\x00\xe0" * 2400)
    return Response(output.getvalue(), media_type="audio/wav")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
