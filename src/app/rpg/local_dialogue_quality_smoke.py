"""Local-only provider-backed runner for the RPG dialogue quality matrix."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.rpg.dialogue_quality_benchmark import (
    DialogueBenchmarkCase,
    aggregate_dialogue_benchmark_observations,
    default_dialogue_benchmark_cases,
    evaluate_dialogue_benchmark_case,
)
from app.rpg.local_live_smoke import assert_live_smoke_allowed


def run_local_dialogue_quality_smoke(
    *,
    base_url: str,
    cases: Iterable[DialogueBenchmarkCase] | None = None,
    timeout_seconds: float = 120.0,
    keep_fixture: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute fixture-aware quality cases through the public turn endpoint.

    This function is intentionally guarded by the same explicit local opt-in as the
    live latency smoke. It must never run inside GitHub Actions.
    """

    assert_live_smoke_allowed(env)
    resolved_cases = tuple(cases or default_dialogue_benchmark_cases())
    run_id = uuid.uuid4().hex
    observations = []
    timings = []
    raw_results = []
    fixture_session_ids: list[str] = []
    fixture_archived = False
    try:
        for index, case in enumerate(resolved_cases, start=1):
            fixture = _provision_case(
                base_url=base_url,
                session_id=None,
                case=case,
                run_id=run_id,
                timeout_seconds=timeout_seconds,
            )
            fixture_session_id = str(fixture.get("session_id") or "").strip()
            if not fixture_session_id:
                raise RuntimeError("dialogue quality fixture response omitted session_id")
            if fixture_session_id not in fixture_session_ids:
                fixture_session_ids.append(fixture_session_id)
            payload, elapsed_seconds, response_bytes = _post_case(
                base_url=base_url,
                session_id=fixture_session_id,
                case=case,
                submission_id=f"quality-smoke:{run_id}:{index}",
                timeout_seconds=timeout_seconds,
            )
            observation = evaluate_dialogue_benchmark_case(case, payload)
            observations.append(observation)
            timings.append(elapsed_seconds)
            raw_results.append(
                {
                    "case": asdict(case),
                    "fixture": fixture,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "response_bytes": response_bytes,
                    "interaction_id": payload.get("interaction_id"),
                    "trace_id": payload.get("trace_id"),
                    "observation": asdict(observation),
                }
            )
    finally:
        if fixture_session_ids and not keep_fixture:
            archive_results = [
                _archive_fixture(
                    base_url=base_url,
                    session_id=session_id,
                    timeout_seconds=timeout_seconds,
                )
                for session_id in fixture_session_ids
            ]
            fixture_archived = all(archive_results)
    aggregate = aggregate_dialogue_benchmark_observations(observations)
    aggregate["local_only"] = True
    aggregate["base_url"] = base_url.rstrip("/")
    aggregate["fixture_mode"] = "known_case_isolated_sessions"
    aggregate["fixture_session_id"] = (
        fixture_session_ids[0] if len(fixture_session_ids) == 1 else None
    )
    aggregate["fixture_session_ids"] = fixture_session_ids
    aggregate["fixture_archived"] = fixture_archived
    aggregate["latency_seconds"] = _latency_summary(timings)
    aggregate["results"] = raw_results
    return aggregate


def _provision_case(
    *,
    base_url: str,
    session_id: str | None,
    case: DialogueBenchmarkCase,
    run_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/rpg/local-qualification/dialogue-fixture"
    body = json.dumps(
        {
            "case_id": case.case_id,
            "run_id": run_id,
            "session_id": session_id,
        }
    ).encode("utf-8")
    return _request_json(
        urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Omnix-Rpg-Live-Smoke": "1",
            },
        ),
        timeout_seconds=timeout_seconds,
        context="dialogue quality fixture",
    )


def _archive_fixture(
    *,
    base_url: str,
    session_id: str,
    timeout_seconds: float,
) -> bool:
    url = f"{base_url.rstrip('/')}/api/rpg/sessions/{session_id}/delete"
    try:
        payload = _request_json(
            urllib.request.Request(url, data=b"{}", method="POST"),
            timeout_seconds=timeout_seconds,
            context="dialogue quality fixture cleanup",
        )
    except RuntimeError:
        return False
    return payload.get("ok") is True


def _post_case(
    *,
    base_url: str,
    session_id: str,
    case: DialogueBenchmarkCase,
    submission_id: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], float, int]:
    url = f"{base_url.rstrip('/')}/api/rpg/sessions/{session_id}/turn"
    body = json.dumps({"command": case.player_input}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Omnix-Rpg-Submission-Id": submission_id,
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise RuntimeError(
            f"dialogue quality request failed with HTTP {exc.code}: "
            f"{raw.decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"dialogue quality request failed: {exc}") from exc
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("dialogue quality response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("dialogue quality response must be a JSON object")
    return payload, elapsed, len(raw)


def _request_json(
    request: urllib.request.Request,
    *,
    timeout_seconds: float,
    context: str,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise RuntimeError(
            f"{context} request failed with HTTP {exc.code}: "
            f"{raw.decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{context} request failed: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{context} response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} response must be a JSON object")
    return payload


def _latency_summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(max(0.0, float(value)) for value in values)
    if not ordered:
        return {"sample_count": 0, "median": 0.0, "p95": 0.0, "maximum": 0.0}
    midpoint = len(ordered) // 2
    median = (
        ordered[midpoint]
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
    )
    p95_index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * 0.95)))
    return {
        "sample_count": len(ordered),
        "median": round(median, 3),
        "p95": round(ordered[p95_index], 3),
        "maximum": round(ordered[-1], 3),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local-only provider-backed RPG dialogue quality matrix.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--keep-fixture",
        action="store_true",
        help="Leave the disposable fixture session active for debugging.",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = run_local_dialogue_quality_smoke(
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
            keep_fixture=args.keep_fixture,
            env=os.environ,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
