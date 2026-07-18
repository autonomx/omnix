from __future__ import annotations

import asyncio
import time

from app.gateway.event_loop_lag_monitor import (
    GatewayEventLoopLagMonitor,
    capture_runtime_contention_snapshot,
    classify_stack,
)


def test_classify_stack_distinguishes_tts_llm_and_framework_work() -> None:
    assert classify_stack(
        [
            {
                "file": "src/app/providers/vendor/qwen3_tts/model.py",
                "function": "generate_voice_clone_streaming",
            }
        ]
    ) == "tts_model_or_waveform_decoder"
    assert classify_stack(
        [
            {
                "file": "src/app/providers/lmstudio_provider.py",
                "function": "stream_provider_reply_chunks",
            }
        ]
    ) == "llm_streaming"
    assert classify_stack(
        [
            {
                "file": "src/app/gateway/main.py",
                "function": "stream_chat_message",
            }
        ]
    ) == "gateway_or_framework_callback"


def test_contention_snapshot_contains_only_code_location_stack_fields() -> None:
    snapshot = capture_runtime_contention_snapshot(
        event_loop_thread_id=None,
        stack_limit=4,
    )

    assert "thread_stacks" in snapshot
    assert "runtime_parallelism" in snapshot
    assert snapshot["thread_stacks"]
    for thread in snapshot["thread_stacks"]:
        assert set(thread) == {
            "thread_id",
            "thread_name",
            "daemon",
            "is_event_loop_thread",
            "category",
            "top_frame",
            "stack",
        }
        for frame in thread["stack"]:
            assert set(frame) == {"file", "line", "function"}


def test_watchdog_reports_blocked_and_recovered_event_loop() -> None:
    records: list[tuple[str, dict[str, object]]] = []

    def record(_stream_id: str, _source: str, event: str, **details: object) -> None:
        records.append((event, details))

    async def exercise() -> None:
        monitor = GatewayEventLoopLagMonitor(
            interval_seconds=0.005,
            threshold_seconds=0.010,
            refresh_seconds=0.100,
            stack_limit=4,
            log=record,
        )
        monitor.start()
        await asyncio.sleep(0.020)
        time.sleep(0.050)
        await asyncio.sleep(0.030)
        await monitor.stop()

    asyncio.run(exercise())

    events = [event for event, _details in records]
    assert "event_loop_lag_detected" in events
    assert "event_loop_lag_recovered" in events
    detected = next(details for event, details in records if event == "event_loop_lag_detected")
    assert float(detected["observed_lag_ms"]) >= 10.0
    assert detected["thread_stacks"]
    assert detected["runtime_parallelism"]
