#!/usr/bin/env python3
"""Create governed Character profiles and queue full live-avatar packs.

Run this while the Omnix gateway and Image Generation worker are running locally.
The script never invents access to files stored only on another machine; it asks the
running gateway to discover its actual governed `voice_profile` assets.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Omnix gateway URL")
    parser.add_argument("--provider-id", default="", help="Optional Image Generation provider")
    parser.add_argument("--style", default="illustrated character portrait")
    parser.add_argument("--include-reference-profiles", action="store_true")
    parser.add_argument("--no-wait", action="store_true", help="Queue base avatars and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    response = _json_request(
        f"{base_url}/api/characters/backfill-cloned-voices",
        method="POST",
        payload={
            "queue_avatar_generation": True,
            "appearance_template": (
                "Create an original fictional conversational companion suitable for a polished live-chat portrait. "
                "Do not depict or imitate a real public person."
            ),
            "style": args.style,
            "provider_id": args.provider_id,
            "include_reference_profiles": args.include_reference_profiles,
        },
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))
    generation_ids = [
        item["generation_batch_id"]
        for item in response.get("items", [])
        if item.get("generation_batch_id")
    ]
    if args.no_wait or not generation_ids:
        return 0

    pending = set(generation_ids)
    viseme_ids: set[str] = set()
    failed = 0
    while pending:
        for batch_id in list(pending):
            batch = _json_request(f"{base_url}/api/character-avatar-generations/{batch_id}")
            status = batch.get("status")
            print(f"{batch.get('character_id')}: base avatar {status}")
            if status == "completed":
                pending.remove(batch_id)
                viseme = _json_request(
                    f"{base_url}/api/characters/{batch['character_id']}/avatar-visemes",
                    method="POST",
                )
                viseme_ids.add(viseme["id"])
            elif status == "failed":
                pending.remove(batch_id)
                failed += 1
        if pending:
            time.sleep(max(0.25, args.poll_seconds))

    pending_visemes = set(viseme_ids)
    while pending_visemes:
        for batch_id in list(pending_visemes):
            batch = _json_request(f"{base_url}/api/character-avatar-visemes/{batch_id}")
            status = batch.get("status")
            print(f"{batch.get('character_id')}: precise visemes {status}")
            if status in {"completed", "failed"}:
                pending_visemes.remove(batch_id)
                if status == "failed":
                    failed += 1
        if pending_visemes:
            time.sleep(max(0.25, args.poll_seconds))

    print(f"Backfill complete with {failed} failed generation batches.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
