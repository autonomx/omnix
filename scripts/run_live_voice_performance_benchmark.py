#!/usr/bin/env python3
"""Run and analyze the five-turn local live-voice hardware benchmark.

The benchmark assumes the real Omnix services are already running on the local
machine (Nemotron + Parakeet EOU STT, gateway/Qwen TTS, and Vite). It drives the
browser with examples/voice/interaction-1.wav through interaction-5.wav and then
analyzes the matching window from resources/logs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT_DIR / "src" / "tests"
TEST_PATH = TESTS_DIR / "e2e" / "test_live_voice_performance.py"
DEFAULT_AUDIO_DIR = ROOT_DIR / "examples" / "voice"
DEFAULT_LOGS_DIR = ROOT_DIR / "resources" / "logs"
LIVE_LOG_NAME = "live-call-streaming.log"
TTS_LOG_NAME = "tts-streaming.log"
EXPECTED_STT_PROVIDER = "nemotron_parakeet_eou"
LLM_PROVIDER_EVIDENCE_EVENTS = frozenset(
    {
        "live_chat_provider_route_resolved",
        "live_chat_speculation_handshake_ready",
        "live_chat_speculation_session_resolved",
        "live_chat_speculation_inline_stream_allocated",
    }
)
METRICS = (
    "stt_finalize_ms",
    "final_to_response_open_ms",
    "response_open_to_first_token_ms",
    "final_to_first_token_ms",
    "first_token_to_first_audio_ms",
    "final_to_first_audio_ms",
    "first_pcm_to_first_playback_ms",
    "first_token_to_first_playback_ms",
    "final_to_first_playback_ms",
    "speech_end_to_first_playback_ms",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "p95": None, "min": None, "max": None}
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    median = (
        ordered[midpoint]
        if count % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2
    )
    return {
        "count": count,
        "median": round(median, 3),
        "p95": round(float(_percentile(ordered, 0.95) or 0.0), 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


def _load_json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def _load_rotated_json_lines(path: Path, *, backup_count: int = 4) -> list[dict[str, Any]]:
    """Load a chronological JSONL stream across active and rotated segments."""
    records: list[dict[str, Any]] = []
    for index in range(max(0, backup_count), 0, -1):
        records.extend(_load_json_lines(Path(f"{path}.{index}")))
    records.extend(_load_json_lines(path))
    return records


def _window_records(
    records: list[dict[str, Any]],
    started_at: datetime,
    completed_at: datetime,
) -> list[dict[str, Any]]:
    lower = started_at - timedelta(seconds=2)
    upper = completed_at + timedelta(seconds=3)
    filtered: list[dict[str, Any]] = []
    for record in records:
        timestamp = _parse_utc(record.get("timestamp_utc"))
        if timestamp is not None and lower <= timestamp <= upper:
            filtered.append(record)
    return filtered


def _preflight(url: str, label: str, *, json_required: bool = False) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        raise RuntimeError(f"{label} is not ready at {url}: {exc}") from exc
    if not json_required:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} returned invalid JSON at {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned an unexpected payload at {url}: {payload!r}")
    return payload


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _release_turns(live_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    first_seen: dict[str, datetime] = {}
    for record in live_records:
        if record.get("event") != "release_metric":
            continue
        turn_id = str(record.get("turn_id") or "").strip()
        metric = str(record.get("metric_name") or "").strip()
        if not turn_id or metric not in METRICS:
            continue
        try:
            value = float(record.get("value_ms"))
        except (TypeError, ValueError):
            continue
        grouped.setdefault(turn_id, {"turn_id": turn_id})[metric] = value
        timestamp = _parse_utc(record.get("timestamp_utc"))
        if timestamp is not None and turn_id not in first_seen:
            first_seen[turn_id] = timestamp

    turns = [
        metrics
        for metrics in grouped.values()
        if "speech_end_to_first_playback_ms" in metrics
    ]
    turns.sort(key=lambda item: first_seen.get(item["turn_id"], datetime.max.replace(tzinfo=timezone.utc)))
    for turn in turns:
        if "final_to_first_playback_ms" in turn:
            turn["speech_end_to_final_ms"] = (
                turn["speech_end_to_first_playback_ms"] - turn["final_to_first_playback_ms"]
            )
    return turns


def _p0_tts_metrics(tts_records: list[dict[str, Any]]) -> dict[str, list[float]]:
    current_output_by_thread: dict[object, str] = {}
    lane_waits: list[float] = []
    provider_to_raw: list[float] = []
    raw_to_audible: list[float] = []
    route_to_frame: list[float] = []

    for record in tts_records:
        event = str(record.get("event") or "")
        thread_id = record.get("thread_id")
        output_id = str(record.get("output_id") or "").strip()
        if output_id:
            current_output_by_thread[thread_id] = output_id
        current_output = output_id or current_output_by_thread.get(thread_id, "")
        is_p0 = str(current_output).endswith("-p0")
        if event == "tts_lane_ticket_acquired" and int(record.get("effective_priority") or -1) == 0 and is_p0:
            try:
                lane_waits.append(float(record.get("wait_ms")))
            except (TypeError, ValueError):
                pass
        elif event == "first_raw_chunk_ready" and is_p0:
            try:
                provider_to_raw.append(float(record.get("provider_to_first_raw_ms")))
            except (TypeError, ValueError):
                pass
        elif event == "first_audible_pcm_block_ready" and is_p0:
            try:
                raw_to_audible.append(float(record.get("raw_to_audible_block_ms")))
            except (TypeError, ValueError):
                pass
        elif event == "first_pcm_frame_sent" and is_p0:
            try:
                route_to_frame.append(float(record.get("route_to_first_frame_ms")))
            except (TypeError, ValueError):
                pass
    return {
        "lane_wait_ms": lane_waits,
        "provider_to_first_raw_ms": provider_to_raw,
        "raw_to_audible_ms": raw_to_audible,
        "route_to_first_frame_ms": route_to_frame,
    }


def _analyze(
    manifest: dict[str, Any],
    live_records: list[dict[str, Any]],
    tts_records: list[dict[str, Any]],
    *,
    expected_provider: str,
    expect_tts_speculation: str,
    max_median_ms: float | None,
    max_p95_ms: float | None,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    interactions = list(manifest.get("interactions") or [])
    turns = _release_turns(live_records)
    if len(interactions) != 5:
        failures.append(f"expected 5 driven interactions, observed {len(interactions)}")
    if len(turns) != 5:
        failures.append(f"expected 5 completed release-metric turns, observed {len(turns)}")

    metric_summaries: dict[str, Any] = {}
    for metric in (*METRICS, "speech_end_to_final_ms"):
        values = [float(turn[metric]) for turn in turns if metric in turn]
        metric_summaries[metric] = _summary(values)

    route_records = [
        record
        for record in (*live_records, *tts_records)
        if record.get("event") in LLM_PROVIDER_EVIDENCE_EVENTS
    ]
    provider_names = sorted(
        {
            str(
                record.get("effective_provider_name")
                or record.get("provider_id")
                or ""
            )
            .strip()
            .casefold()
            for record in route_records
            if str(
                record.get("effective_provider_name")
                or record.get("provider_id")
                or ""
            ).strip()
        }
    )
    expected = expected_provider.strip().casefold()
    if expected and expected not in provider_names:
        failures.append(
            f"expected live LLM provider {expected_provider!r}, observed {provider_names or ['<none>']}"
        )
    unexpected = [name for name in provider_names if expected and name != expected]
    if unexpected:
        failures.append(f"unexpected live LLM provider routes observed: {unexpected}")

    stt_records = [
        record
        for record in live_records
        if str(record.get("provider") or "").strip().casefold() == EXPECTED_STT_PROVIDER
        and str(record.get("event") or "").startswith("stt_")
    ]
    if not stt_records:
        failures.append(
            f"no {EXPECTED_STT_PROVIDER} STT diagnostics were observed during the benchmark window"
        )

    max_underruns = 0
    explicit_underruns = 0
    for record in live_records:
        if record.get("event") == "worklet_underrun":
            explicit_underruns += 1
        for key in ("underrun_count", "underruns"):
            try:
                max_underruns = max(max_underruns, int(record.get(key) or 0))
            except (TypeError, ValueError):
                pass
    if max_underruns > 0 or explicit_underruns > 0:
        failures.append(
            f"audio underrun observed: explicit={explicit_underruns}, max_counter={max_underruns}"
        )

    speculative_tts_starts = sum(
        1
        for record in (*live_records, *tts_records)
        if record.get("event") == "speculative_tts_prefetch_started"
    )
    if expect_tts_speculation == "disabled" and speculative_tts_starts:
        failures.append(f"speculative TTS expected disabled but started {speculative_tts_starts} time(s)")
    if expect_tts_speculation == "enabled" and speculative_tts_starts == 0:
        failures.append("speculative TTS expected enabled but no prefetch starts were observed")

    llm_reuse_count = sum(1 for record in live_records if record.get("event") == "llm_speculation_reused")
    llm_provider_ttft = [
        float(record["first_provider_text_ms"])
        for record in tts_records
        if record.get("event") == "live_voice_raw_provider_stream_metrics"
        and isinstance(record.get("first_provider_text_ms"), (int, float))
    ]

    p0_metrics = _p0_tts_metrics(tts_records)
    speech_summary = metric_summaries["speech_end_to_first_playback_ms"]
    median_value = speech_summary.get("median")
    p95_value = speech_summary.get("p95")
    if max_median_ms is not None and isinstance(median_value, (int, float)) and median_value > max_median_ms:
        failures.append(
            f"median speech-end->playback {median_value:.1f} ms exceeds limit {max_median_ms:.1f} ms"
        )
    if max_p95_ms is not None and isinstance(p95_value, (int, float)) and p95_value > max_p95_ms:
        failures.append(
            f"p95 speech-end->playback {p95_value:.1f} ms exceeds limit {max_p95_ms:.1f} ms"
        )

    report = {
        "schema_version": 1,
        "completed": not failures,
        "interaction_count": len(interactions),
        "release_turn_count": len(turns),
        "interactions": interactions,
        "turns": turns,
        "metrics": metric_summaries,
        "provider_names": provider_names,
        "expected_provider": expected_provider,
        "stt_provider": EXPECTED_STT_PROVIDER,
        "stt_diagnostic_count": len(stt_records),
        "audio": {
            "explicit_underrun_events": explicit_underruns,
            "max_underrun_counter": max_underruns,
        },
        "speculation": {
            "llm_reuse_count": llm_reuse_count,
            "tts_prefetch_start_count": speculative_tts_starts,
            "tts_expectation": expect_tts_speculation,
        },
        "llm_provider_first_text_ms": _summary(llm_provider_ttft),
        "p0_tts": {key: _summary(values) for key, values in p0_metrics.items()},
        "failures": failures,
    }
    return report, failures


def _markdown_report(report: dict[str, Any], *, run_id: str, git_sha: str) -> str:
    lines = [
        "# Live Voice Hardware Benchmark",
        "",
        f"- Run: `{run_id}`",
        f"- Git: `{git_sha}`",
        f"- Provider: `{', '.join(report.get('provider_names') or ['unknown'])}`",
        f"- STT: `{report.get('stt_provider') or 'unknown'}`",
        f"- Interactions: **{report.get('interaction_count')}**",
        f"- Completed release turns: **{report.get('release_turn_count')}**",
        f"- LLM speculation reused: **{report.get('speculation', {}).get('llm_reuse_count', 0)}**",
        f"- Speculative TTS starts: **{report.get('speculation', {}).get('tts_prefetch_start_count', 0)}**",
        f"- Audio underruns: **{report.get('audio', {}).get('max_underrun_counter', 0)}**",
        "",
        "| Metric | Median ms | p95 ms | Min ms | Max ms |",
        "|---|---:|---:|---:|---:|",
    ]
    display_metrics = (
        "stt_finalize_ms",
        "speech_end_to_final_ms",
        "final_to_first_token_ms",
        "first_token_to_first_audio_ms",
        "final_to_first_playback_ms",
        "first_pcm_to_first_playback_ms",
        "speech_end_to_first_playback_ms",
    )
    for metric in display_metrics:
        summary = report.get("metrics", {}).get(metric, {})
        lines.append(
            f"| `{metric}` | {summary.get('median')} | {summary.get('p95')} | "
            f"{summary.get('min')} | {summary.get('max')} |"
        )
    lines.extend(["", "## First-phrase TTS", ""])
    for metric, summary in report.get("p0_tts", {}).items():
        lines.append(f"- `{metric}`: median **{summary.get('median')} ms**, p95 **{summary.get('p95')} ms**")
    failures = report.get("failures") or []
    lines.extend(["", "## Result", ""])
    if failures:
        lines.append("**FAIL**")
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("**PASS**")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local five-turn Live Voice hardware benchmark")
    parser.add_argument("--headed", action="store_true", help="Show Chromium while the benchmark runs")
    parser.add_argument("--app-url", default="http://127.0.0.1:5173", help="Vite/Omnix web URL")
    parser.add_argument(
        "--stt-url",
        default="http://127.0.0.1:5201",
        help="Nemotron + Parakeet EOU STT base URL",
    )
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--logs-dir", type=Path, default=DEFAULT_LOGS_DIR)
    parser.add_argument("--expected-provider", default="cerebras")
    parser.add_argument(
        "--expect-tts-speculation",
        choices=("disabled", "enabled", "any"),
        default="disabled",
    )
    parser.add_argument("--max-median-ms", type=float, default=None)
    parser.add_argument("--max-p95-ms", type=float, default=None)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    audio_paths = [args.audio_dir / f"interaction-{index}.wav" for index in range(1, 6)]
    missing = [str(path) for path in audio_paths if not path.is_file()]
    if missing:
        print(f"ERROR: missing benchmark WAVs: {missing}", file=sys.stderr)
        return 2

    if not args.skip_preflight:
        try:
            _preflight(f"{args.app_url.rstrip('/')}/chatbot", "Omnix web app")
            authority = _preflight(
                f"{args.stt_url.rstrip('/')}/authorityz?language=en&mode=test",
                "Live STT authority gate",
                json_required=True,
            )
            _preflight(
                f"{args.app_url.rstrip('/')}/api/tts/live-call/capabilities",
                "Live TTS capability route",
                json_required=True,
            )
            print(f"Live STT authority preflight: {json.dumps(authority, sort_keys=True)}")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    git_sha = _git_short_sha()
    run_started = _utc_now()
    run_id = f"{run_started.strftime('%Y%m%d-%H%M%S')}-{git_sha}"
    run_dir = args.logs_dir / "benchmarks" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"

    env = os.environ.copy()
    env["OMNIX_RUN_LIVE_VOICE_PERFORMANCE"] = "1"
    env["OMNIX_BASE_URL"] = args.app_url
    env["OMNIX_STT_URL"] = args.stt_url
    env["OMNIX_LIVE_VOICE_EXPECTED_PROVIDER"] = args.expected_provider
    env["OMNIX_LIVE_VOICE_BENCHMARK_AUDIO_DIR"] = str(args.audio_dir.resolve())
    env["OMNIX_LIVE_VOICE_BENCHMARK_MANIFEST"] = str(manifest_path.resolve())

    command = [
        sys.executable,
        "-m",
        "pytest",
        "--rootdir",
        str(TESTS_DIR),
        "-c",
        str(TESTS_DIR / "pytest.ini"),
        str(TEST_PATH),
        "-q",
        "-s",
    ]
    if args.headed:
        command.append("--headed")

    print("=" * 78)
    print("Omnix Live Voice Hardware Benchmark")
    print(f"Git      : {git_sha}")
    print(f"Provider : {args.expected_provider}")
    print(f"STT      : {EXPECTED_STT_PROVIDER}")
    print(f"Audio    : {args.audio_dir}")
    print(f"Logs     : {args.logs_dir}")
    print(f"Run dir  : {run_dir}")
    print("Files    : " + ", ".join(path.name for path in audio_paths))
    print("=" * 78)

    test_result = subprocess.run(command, cwd=ROOT_DIR, env=env, check=False)
    time.sleep(1.0)  # allow the gateway's queued JSONL diagnostics to flush

    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: could not read benchmark manifest: {exc}", file=sys.stderr)
            return test_result.returncode or 2
    else:
        manifest = {
            "started_at_utc": run_started.isoformat(timespec="milliseconds"),
            "completed_at_utc": _utc_now().isoformat(timespec="milliseconds"),
            "interactions": [],
            "completed": False,
        }

    started_at = _parse_utc(manifest.get("started_at_utc")) or run_started
    completed_at = _parse_utc(manifest.get("completed_at_utc")) or _utc_now()
    live_records = _window_records(
        _load_rotated_json_lines(args.logs_dir / LIVE_LOG_NAME),
        started_at,
        completed_at,
    )
    tts_records = _window_records(
        _load_rotated_json_lines(args.logs_dir / TTS_LOG_NAME),
        started_at,
        completed_at,
    )

    _write_jsonl(run_dir / "live-call-streaming.run.log", live_records)
    _write_jsonl(run_dir / "tts-streaming.run.log", tts_records)

    report, failures = _analyze(
        manifest,
        live_records,
        tts_records,
        expected_provider=args.expected_provider,
        expect_tts_speculation=args.expect_tts_speculation,
        max_median_ms=args.max_median_ms,
        max_p95_ms=args.max_p95_ms,
    )
    report.update(
        {
            "run_id": run_id,
            "git_sha": git_sha,
            "test_exit_code": test_result.returncode,
            "started_at_utc": started_at.isoformat(timespec="milliseconds"),
            "completed_at_utc": completed_at.isoformat(timespec="milliseconds"),
        }
    )
    if test_result.returncode != 0:
        report["failures"] = [*report.get("failures", []), f"browser driver exited {test_result.returncode}"]
        failures = list(report["failures"])
        report["completed"] = False

    report_json_path = run_dir / "report.json"
    report_md_path = run_dir / "report.md"
    report_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = _markdown_report(report, run_id=run_id, git_sha=git_sha)
    report_md_path.write_text(markdown, encoding="utf-8")

    print()
    print(markdown)
    print(f"Report JSON : {report_json_path}")
    print(f"Run logs    : {run_dir}")
    if failures:
        return test_result.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
