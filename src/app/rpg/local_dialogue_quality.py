"""Local-only live-provider dialogue quality evaluation for RPG interactions."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from app.rpg.local_live_smoke import assert_live_smoke_allowed, evaluate_live_smoke_payload
from app.rpg.presentation.dialogue_quality_benchmark import (
    DialogueBenchmarkCase,
    build_provider_free_dialogue_matrix,
    evaluate_dialogue_quality_matrix,
)
from app.rpg.release_gates import evaluate_dialogue_quality_release_gates

LOCAL_DIALOGUE_QUALITY_VERSION = "rpg_live_dialogue_quality_v1"


@dataclass(frozen=True)
class LiveDialogueTurnEvidence:
    case_id: str
    category: str
    submission_id: str
    interaction_id: str | None
    trace_id: str | None
    elapsed_seconds: float
    response_bytes: int
    provider_call_count: int | None
    provider_ms: float | None
    structural_ok: bool
    structural_failures: tuple[str, ...]


def build_live_dialogue_plan() -> list[DialogueBenchmarkCase]:
    """Use all accepted categories; rejected candidates are evaluator fixtures only."""

    return [case for case in build_provider_free_dialogue_matrix() if case.should_accept]


def evaluate_live_dialogue_payloads(
    cases: Iterable[DialogueBenchmarkCase],
    payloads: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate supplied payloads without network access or provider calls."""

    resolved_cases = list(cases)
    resolved_payloads = list(payloads)
    if len(resolved_cases) != len(resolved_payloads):
        raise ValueError("dialogue case and payload counts must match")

    actual_cases: list[DialogueBenchmarkCase] = []
    structural_reports: list[dict[str, Any]] = []
    for case, payload in zip(resolved_cases, resolved_payloads):
        structural = evaluate_live_smoke_payload(payload)
        structural_reports.append(structural)
        visible = payload.get("visible_response")
        actual_cases.append(
            DialogueBenchmarkCase(
                case_id=case.case_id,
                category=case.category,
                player_input=case.player_input,
                visible=visible if isinstance(visible, dict) else {},
                profile=case.profile,
                recent_interactions=case.recent_interactions,
                expected_speaker=case.expected_speaker,
                continuity_terms=case.continuity_terms,
                should_accept=True,
            )
        )

    benchmark = evaluate_dialogue_quality_matrix(actual_cases)
    gate = evaluate_dialogue_quality_release_gates(benchmark)
    structural_failures = sorted(
        {
            str(failure)
            for report in structural_reports
            for failure in report.get("failures") or []
        }
    )
    one_call_failures = [
        case.case_id
        for case, report in zip(resolved_cases, structural_reports)
        if report.get("provider_call_count") != 1
    ]
    failures: list[str] = []
    if structural_failures:
        failures.append("one_or_more_dialogue_turns_failed_structural_gates")
    if one_call_failures:
        failures.append("one_or_more_dialogue_turns_did_not_use_exactly_one_provider_call")
    failures.extend(str(item) for item in gate.get("failures") or [])

    return {
        "format_version": LOCAL_DIALOGUE_QUALITY_VERSION,
        "ok": not failures,
        "failures": sorted(set(failures)),
        "accepted_case_count": benchmark["accepted_case_count"],
        "rejected_case_count": benchmark["rejected_case_count"],
        "category_count": benchmark["category_count"],
        "categories": benchmark["categories"],
        "metrics": benchmark["metrics"],
        "thresholds": benchmark["thresholds"],
        "cases": benchmark["cases"],
        "structural_failures": structural_failures,
        "provider_call_failures": one_call_failures,
    }


def run_live_dialogue_quality(
    *,
    base_url: str,
    session_id: str,
    timeout_seconds: float = 120.0,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the full matrix against a disposable local session and active provider."""

    assert_live_smoke_allowed(env)
    cases = build_live_dialogue_plan()
    payloads: list[dict[str, Any]] = []
    evidence: list[LiveDialogueTurnEvidence] = []
    run_id = uuid.uuid4().hex

    for index, case in enumerate(cases, start=1):
        submission_id = f"live-quality:{run_id}:{index}"
        payload, elapsed, response_bytes, headers = _post_turn(
            base_url=base_url,
            session_id=session_id,
            command=case.player_input,
            submission_id=submission_id,
            timeout_seconds=timeout_seconds,
        )
        payloads.append(payload)
        structural = evaluate_live_smoke_payload(payload)
        evidence.append(
            LiveDialogueTurnEvidence(
                case_id=case.case_id,
                category=case.category,
                submission_id=submission_id,
                interaction_id=str(payload.get("interaction_id") or "") or None,
                trace_id=headers.get("x-omnix-rpg-trace-id") or str(payload.get("trace_id") or "") or None,
                elapsed_seconds=round(elapsed, 3),
                response_bytes=response_bytes,
                provider_call_count=structural.get("provider_call_count"),
                provider_ms=(
                    round(float(structural["provider_ms"]), 3)
                    if isinstance(structural.get("provider_ms"), (int, float))
                    else None
                ),
                structural_ok=bool(structural.get("ok")),
                structural_failures=tuple(str(item) for item in structural.get("failures") or []),
            )
        )

    report = evaluate_live_dialogue_payloads(cases, payloads)
    report.update(
        {
            "base_url": base_url.rstrip("/"),
            "session_id": session_id,
            "turn_evidence": [asdict(item) for item in evidence],
        }
    )
    return report


def _post_turn(
    *,
    base_url: str,
    session_id: str,
    command: str,
    submission_id: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], float, int, dict[str, str]]:
    url = f"{base_url.rstrip('/')}/api/rpg/sessions/{session_id}/turn"
    body = json.dumps({"command": command}).encode("utf-8")
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
            headers = {str(key).casefold(): str(value) for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise RuntimeError(
            f"dialogue request failed with HTTP {exc.code}: {raw.decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"dialogue request failed: {exc}") from exc
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("dialogue response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("dialogue response must be a JSON object")
    return payload, elapsed, len(raw), headers


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local-only live-provider RPG dialogue quality validation.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = run_live_dialogue_quality(
            base_url=args.base_url,
            session_id=args.session_id,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
