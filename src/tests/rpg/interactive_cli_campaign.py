"""CA/CB/CF — interactive command-line RPG campaign runner.

This runner is for live human/agent playtesting, not LLM-as-player autoplay.
It prompts for player input in the terminal for a fixed number of turns, captures
turn results, and writes review artifacts similar in spirit to autoplay reports.

Examples from repo root:

    python src/tests/rpg/interactive_cli_campaign.py --turns 30
    python src/tests/rpg/interactive_cli_campaign.py --turns 30 --session-id cli_live_test
    python src/tests/rpg/interactive_cli_campaign.py --turns 30 --script-file commands.txt

A coding agent such as Cline/Codex can drive stdin live, while the runtime still
uses the normal deterministic apply_turn path.  CB adds provider/narrator
classification diagnostics. CF adds per-turn performance timing so slow live
provider/runtime phases are visible in JSON, HTML, and ZIP artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rpg.survival_report_artifacts import write_survival_report_artifacts  # noqa: E402
from rpg.interactive_cli_commerce_followup import (  # noqa: E402
    apply_commerce_followup_repair,
    extract_service_offer_context,
)
from rpg.interactive_cli_intent_fallback import (  # noqa: E402
    classify_service_intent_with_fallback,
    narration_source_for_turn,
)
from rpg.interactive_cli_quest_followup import apply_quest_followup_repair  # noqa: E402
from tests.rpg.manual.session_helpers import (  # noqa: E402
    _ensure_manual_session,
    _reset_manual_session_artifacts,
)
from tests.rpg.manual.live_survival_seed import seed_live_survival_session  # noqa: E402
from tests.rpg.manual.turn_execution import _extract_narration, _run_one_manual_turn  # noqa: E402

INTERACTIVE_CLI_CAMPAIGN_VERSION = "interactive_cli_campaign_v3"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "resources" / "data" / "test-results"
STOP_COMMANDS = {"/quit", "/exit", "/stop"}
SLOW_TURN_THRESHOLD_SECONDS = 10.0


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _elapsed_since(started: float) -> float:
    return round(max(0.0, time.perf_counter() - started), 4)


def _percentile(values: Sequence[float], percentile: float) -> float:
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 4)
    position = (len(values) - 1) * (percentile / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1.0 - weight) + values[upper] * weight, 4)


def _sum_phase(turns: Sequence[Mapping[str, Any]], key: str) -> float:
    return round(sum(_safe_float(_safe_dict(turn.get("interactive_cli_performance")).get(key)) for turn in turns), 4)


def _performance_summary(turns: Sequence[Mapping[str, Any]], *, elapsed_seconds: float) -> Dict[str, Any]:
    totals = [_safe_float(_safe_dict(turn.get("interactive_cli_performance")).get("turn_total_seconds")) for turn in turns]
    totals = [value for value in totals if value > 0]
    phase_keys = [
        "runtime_apply_turn_seconds",
        "offer_context_extract_seconds",
        "intent_router_seconds",
        "commerce_repair_seconds",
        "quest_dialogue_repair_seconds",
        "post_repair_context_seconds",
        "print_prepare_seconds",
        "turn_total_seconds",
    ]
    phase_totals = {key: _sum_phase(turns, key) for key in phase_keys}
    completed = max(1, len(turns))
    phase_averages = {key: round(value / completed, 4) for key, value in phase_totals.items()}
    slow_turns = []
    for turn in turns:
        perf = _safe_dict(turn.get("interactive_cli_performance"))
        total = _safe_float(perf.get("turn_total_seconds"))
        if total >= SLOW_TURN_THRESHOLD_SECONDS:
            slow_turns.append(
                {
                    "turn_index": turn.get("turn_index"),
                    "player_input": _safe_str(turn.get("player_input"))[:160],
                    "turn_total_seconds": round(total, 4),
                    "runtime_apply_turn_seconds": round(_safe_float(perf.get("runtime_apply_turn_seconds")), 4),
                    "intent_router_seconds": round(_safe_float(perf.get("intent_router_seconds")), 4),
                    "narration_source": _safe_str(turn.get("narration_source")),
                    "provider_called": bool(_safe_dict(turn.get("interactive_cli_intent_diagnostics")).get("provider_called")),
                }
            )
    return {
        "format_version": "interactive_cli_performance_v1",
        "elapsed_seconds": round(elapsed_seconds, 4),
        "completed_turns": len(turns),
        "avg_turn_seconds": round(sum(totals) / len(totals), 4) if totals else 0.0,
        "min_turn_seconds": round(min(totals), 4) if totals else 0.0,
        "max_turn_seconds": round(max(totals), 4) if totals else 0.0,
        "p50_turn_seconds": _percentile(totals, 50),
        "p95_turn_seconds": _percentile(totals, 95),
        "slow_turn_threshold_seconds": SLOW_TURN_THRESHOLD_SECONDS,
        "slow_turn_count": len(slow_turns),
        "slow_turns": slow_turns[:20],
        "phase_totals_seconds": phase_totals,
        "phase_avg_seconds": phase_averages,
        "note": "runtime_apply_turn_seconds includes deterministic runtime plus any narration work inside _run_one_manual_turn; intent_router_seconds includes the central provider intent-classifier call.",
    }


def default_run_id() -> str:
    return f"interactive_{_timestamp()}_{uuid.uuid4().hex[:8]}"


def default_output_dir(run_id: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / f"interactive-cli-campaign-{run_id}"


def _extract_turn_contract(result: Mapping[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    return _safe_dict(result.get("turn_contract") or _safe_dict(result.get("result")).get("turn_contract"))


def _extract_simulation_state(result: Mapping[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    session = _safe_dict(result.get("session") or _safe_dict(result.get("result")).get("session"))
    return _safe_dict(
        result.get("simulation_state")
        or _safe_dict(result.get("result")).get("simulation_state")
        or session.get("simulation_state")
        or _safe_dict(session.get("setup_payload")).get("simulation_state")
    )


def _extract_survival_state(result: Mapping[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    contract = _extract_turn_contract(result)
    sim = _extract_simulation_state(result)
    return _safe_dict(result.get("survival") or _safe_dict(result.get("result")).get("survival") or contract.get("survival") or sim.get("survival"))


def _turn_report_row(turn_summary: Mapping[str, Any]) -> Dict[str, Any]:
    raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    return {
        "turn": turn_summary.get("turn_index"),
        "player_input": turn_summary.get("player_input"),
        "result": raw_result,
        "turn_contract": _extract_turn_contract(raw_result),
        "survival": _extract_survival_state(raw_result),
        "error": turn_summary.get("error"),
        "scenario_warnings": _safe_list(turn_summary.get("scenario_warnings")),
        "regression_warnings": _safe_list(turn_summary.get("regression_warnings")),
        "interactive_cli_intent_diagnostics": _safe_dict(turn_summary.get("interactive_cli_intent_diagnostics")),
        "interactive_cli_quest_followup": _safe_dict(turn_summary.get("interactive_cli_quest_followup")),
        "interactive_cli_performance": _safe_dict(turn_summary.get("interactive_cli_performance")),
        "narration_source": _safe_str(turn_summary.get("narration_source")),
    }


def build_interactive_campaign_summary(*, run_id: str, session_id: str, requested_turns: int, turns: Sequence[Mapping[str, Any]], started_at: float, ended_at: float, stop_reason: str) -> Dict[str, Any]:
    warnings: List[str] = []
    errors = 0
    llm_turns = 0
    commerce_repairs = 0
    quest_repairs = 0
    provider_requested = 0
    provider_called = 0
    narration_sources: Dict[str, int] = {}
    for turn in turns:
        warnings.extend(_safe_list(turn.get("scenario_warnings")))
        warnings.extend(_safe_list(turn.get("regression_warnings")))
        if turn.get("error"):
            errors += 1
        if bool(turn.get("llm_called")):
            llm_turns += 1
        if _safe_dict(turn.get("interactive_cli_commerce_followup")).get("applied"):
            commerce_repairs += 1
        if _safe_dict(turn.get("interactive_cli_quest_followup")).get("applied"):
            quest_repairs += 1
        diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
        if diagnostics.get("provider_requested"):
            provider_requested += 1
        if diagnostics.get("provider_called"):
            provider_called += 1
        source = _safe_str(turn.get("narration_source") or narration_source_for_turn(turn) or "unknown")
        narration_sources[source] = narration_sources.get(source, 0) + 1
    elapsed_seconds = round(max(0.0, ended_at - started_at), 3)
    performance = _performance_summary(turns, elapsed_seconds=elapsed_seconds)
    return {
        "format_version": INTERACTIVE_CLI_CAMPAIGN_VERSION,
        "run_id": run_id,
        "session_id": session_id,
        "requested_turns": requested_turns,
        "completed_turns": len(turns),
        "stop_reason": stop_reason,
        "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
        "ended_at": datetime.fromtimestamp(ended_at).isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed_seconds,
        "avg_turn_seconds": performance.get("avg_turn_seconds"),
        "p95_turn_seconds": performance.get("p95_turn_seconds"),
        "max_turn_seconds": performance.get("max_turn_seconds"),
        "slow_turn_count": performance.get("slow_turn_count"),
        "error_count": errors,
        "warning_count": len(warnings),
        "llm_turn_count": llm_turns,
        "provider_requested_count": provider_requested,
        "provider_called_count": provider_called,
        "commerce_followup_repair_count": commerce_repairs,
        "quest_followup_repair_count": quest_repairs,
        "narration_sources": narration_sources,
        "performance": performance,
        "warnings": sorted(set(_safe_str(w) for w in warnings if _safe_str(w)))[:100],
    }


def render_interactive_campaign_html(summary: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> str:
    summary = _safe_dict(summary)
    performance = _safe_dict(summary.get("performance"))
    rows = []
    for turn in turns:
        turn = _safe_dict(turn)
        raw_result = _safe_dict(turn.get("raw_result") or turn.get("result"))
        narration = _safe_str(turn.get("raw_narration") or _extract_narration(raw_result))
        survival = _extract_survival_state(raw_result)
        survival_text = ""
        if survival:
            survival_text = " · ".join(f"{escape(str(k))}: {escape(str(v))}" for k, v in survival.items() if k in {"hunger", "thirst", "fatigue"})
        commerce = _safe_dict(turn.get("interactive_cli_commerce_followup"))
        quest = _safe_dict(turn.get("interactive_cli_quest_followup"))
        diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
        perf = _safe_dict(turn.get("interactive_cli_performance"))
        narration_source = _safe_str(turn.get("narration_source") or narration_source_for_turn(turn))
        commerce_html = ""
        if commerce.get("applied"):
            commerce_html = "<p><strong>Commerce follow-up:</strong> answered from authoritative service offers.</p>"
        quest_html = ""
        if quest.get("applied"):
            kind = _safe_str(quest.get("inquiry_kind") or "quest")
            has_backed = _safe_dict(quest.get("quest_context")).get("has_backed_quest")
            quest_html = f"<p><strong>{escape(kind.title())} repair:</strong> answered from bounded/authoritative context. backed quest: {escape(_safe_str(has_backed))}</p>"
        perf_html = ""
        if perf:
            perf_html = "".join([
                "<details><summary>Turn performance</summary><ul>",
                f"<li>total: {escape(_safe_str(perf.get('turn_total_seconds')))}s</li>",
                f"<li>runtime/apply turn: {escape(_safe_str(perf.get('runtime_apply_turn_seconds')))}s</li>",
                f"<li>intent router/provider classifier: {escape(_safe_str(perf.get('intent_router_seconds')))}s</li>",
                f"<li>commerce repair: {escape(_safe_str(perf.get('commerce_repair_seconds')))}s</li>",
                f"<li>quest/dialogue repair: {escape(_safe_str(perf.get('quest_dialogue_repair_seconds')))}s</li>",
                "</ul>",
                f"<pre>{escape(_json_dumps(perf))}</pre>",
                "</details>",
            ])
        diagnostics_html = "\n".join([
            "<details><summary>Provider / intent diagnostics</summary>",
            "<ul>",
            f"<li>provider requested: {escape(_safe_str(diagnostics.get('provider_requested')))}</li>",
            f"<li>provider called: {escape(_safe_str(diagnostics.get('provider_called')))}</li>",
            f"<li>provider: {escape(_safe_str(diagnostics.get('provider_name')))}</li>",
            f"<li>model: {escape(_safe_str(diagnostics.get('model')))}</li>",
            f"<li>why not called/error: {escape(_safe_str(diagnostics.get('why_provider_not_called') or diagnostics.get('provider_error')))}</li>",
            f"<li>narration source: {escape(narration_source)}</li>",
            "</ul>",
            f"<pre>{escape(_json_dumps(diagnostics))}</pre>",
            "</details>",
        ])
        warning_html = "".join(f"<li>{escape(_safe_str(w))}</li>" for w in _safe_list(turn.get("scenario_warnings")) + _safe_list(turn.get("regression_warnings"))) or "<li>none</li>"
        rows.append("\n".join([
            "<section class='turn-card'>",
            f"<h2>Turn {escape(_safe_str(turn.get('turn_index')))}</h2>",
            f"<p><strong>Player:</strong> {escape(_safe_str(turn.get('player_input')))}</p>",
            f"<p><strong>Narration:</strong> {escape(narration or '[no narration found]')}</p>",
            f"<p><strong>Survival:</strong> {survival_text or 'n/a'}</p>",
            f"<p><strong>Narration source:</strong> {escape(narration_source)}</p>",
            f"<p><strong>Turn total:</strong> {escape(_safe_str(perf.get('turn_total_seconds') if perf else 'n/a'))}s</p>",
            commerce_html,
            quest_html,
            perf_html,
            diagnostics_html,
            "<details><summary>Warnings</summary><ul>",
            warning_html,
            "</ul></details>",
            "<details><summary>Raw compact turn JSON</summary>",
            f"<pre>{escape(_json_dumps(turn))}</pre>",
            "</details>",
            "</section>",
        ]))
    slow_turns_html = "".join(
        f"<li>Turn {escape(_safe_str(item.get('turn_index')))}: {escape(_safe_str(item.get('turn_total_seconds')))}s — runtime {escape(_safe_str(item.get('runtime_apply_turn_seconds')))}s, intent {escape(_safe_str(item.get('intent_router_seconds')))}s — {escape(_safe_str(item.get('player_input')))}</li>"
        for item in _safe_list(performance.get("slow_turns"))
    ) or "<li>none</li>"
    return "\n".join([
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Interactive RPG Campaign Report</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45;background:#111827;color:#e5e7eb}.summary,.turn-card{border:1px solid #374151;border-radius:14px;padding:16px;margin:14px 0;background:#1f2937}a{color:#93c5fd}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#0b1020;padding:12px;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}.metric{background:#111827;border-radius:10px;padding:10px}.warn{color:#fbbf24}</style>",
        "</head><body>",
        "<h1>Interactive RPG Campaign Report</h1>",
        "<section class='summary'>",
        "<h2>Run Summary</h2>",
        "<div class='grid'>",
        f"<div class='metric'><strong>Run</strong><br>{escape(_safe_str(summary.get('run_id')))}</div>",
        f"<div class='metric'><strong>Session</strong><br>{escape(_safe_str(summary.get('session_id')))}</div>",
        f"<div class='metric'><strong>Turns</strong><br>{escape(_safe_str(summary.get('completed_turns')))} / {escape(_safe_str(summary.get('requested_turns')))}</div>",
        f"<div class='metric'><strong>Elapsed</strong><br>{escape(_safe_str(summary.get('elapsed_seconds')))}s</div>",
        f"<div class='metric'><strong>Avg turn</strong><br>{escape(_safe_str(summary.get('avg_turn_seconds')))}s</div>",
        f"<div class='metric'><strong>P95 turn</strong><br>{escape(_safe_str(summary.get('p95_turn_seconds')))}s</div>",
        f"<div class='metric'><strong>Max turn</strong><br>{escape(_safe_str(summary.get('max_turn_seconds')))}s</div>",
        f"<div class='metric'><strong>Slow turns</strong><br>{escape(_safe_str(summary.get('slow_turn_count')))}</div>",
        f"<div class='metric'><strong>Stop</strong><br>{escape(_safe_str(summary.get('stop_reason')))}</div>",
        f"<div class='metric'><strong>Warnings</strong><br>{escape(_safe_str(summary.get('warning_count')))}</div>",
        f"<div class='metric'><strong>Errors</strong><br>{escape(_safe_str(summary.get('error_count')))}</div>",
        f"<div class='metric'><strong>Provider called</strong><br>{escape(_safe_str(summary.get('provider_called_count')))}</div>",
        f"<div class='metric'><strong>Commerce repairs</strong><br>{escape(_safe_str(summary.get('commerce_followup_repair_count')))}</div>",
        f"<div class='metric'><strong>Quest repairs</strong><br>{escape(_safe_str(summary.get('quest_followup_repair_count')))}</div>",
        "</div>",
        "<details open><summary>Performance summary</summary>",
        f"<p>{escape(_safe_str(performance.get('note')))}</p>",
        "<h3>Slow turns</h3><ul>",
        slow_turns_html,
        "</ul>",
        f"<pre>{escape(_json_dumps(performance))}</pre>",
        "</details>",
        "<p>Open survival artifact index if present: <a href='survival/survival-index.html'>survival/survival-index.html</a></p>",
        "</section>",
        *rows,
        "</body></html>",
    ])


def write_interactive_campaign_artifacts(*, output_dir: Path, summary: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = output_dir / "interactive-transcript.json"
    summary_path = output_dir / "interactive-summary.json"
    performance_path = output_dir / "interactive-performance.json"
    html_path = output_dir / "interactive-report.html"
    zip_path = output_dir / "interactive-campaign-results.zip"
    transcript_payload = {"format_version": INTERACTIVE_CLI_CAMPAIGN_VERSION, "summary": dict(summary), "turns": list(turns)}
    transcript_path.write_text(_json_dumps(transcript_payload), encoding="utf-8")
    summary_path.write_text(_json_dumps(summary), encoding="utf-8")
    performance_path.write_text(_json_dumps(_safe_dict(summary).get("performance")), encoding="utf-8")
    html_path.write_text(render_interactive_campaign_html(summary, turns), encoding="utf-8")
    survival_rows = [_turn_report_row(turn) for turn in turns]
    survival_dir = output_dir / "survival"
    survival_result = write_survival_report_artifacts(survival_dir, survival_rows)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(summary_path, "interactive-summary.json")
        zf.write(performance_path, "interactive-performance.json")
        zf.write(transcript_path, "interactive-transcript.json")
        zf.write(html_path, "interactive-report.html")
        for path in sorted(survival_dir.glob("*")):
            if path.is_file():
                zf.write(path, f"survival/{path.name}")
    return {"ok": True, "output_dir": str(output_dir), "summary_path": str(summary_path), "performance_path": str(performance_path), "transcript_path": str(transcript_path), "html_path": str(html_path), "zip_path": str(zip_path), "survival_artifacts": survival_result}


def read_scripted_commands(path: str | Path) -> List[str]:
    path = Path(path)
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def run_interactive_campaign(*, turns: int, session_id: str, output_dir: Path, input_func: Callable[[str], str] = input, scripted_commands: Sequence[str] | None = None, reset_session: bool = True, console_llm: bool = True, include_raw_result: bool = True, artifact_detail: str = "debug", enable_llm_intent_fallback: bool = True, provider_factory: Callable[[], Any] | None = None, seed_live_survival: bool = False) -> Dict[str, Any]:
    if turns <= 0:
        raise ValueError("turns_must_be_positive")
    session_id = _safe_str(session_id).strip() or f"interactive_cli_{uuid.uuid4().hex[:8]}"
    if reset_session:
        _reset_manual_session_artifacts(session_id)
    _ensure_manual_session(session_id)
    if seed_live_survival:
        seed_live_survival_session(session_id, reset_first=False)

    commands = list(scripted_commands or [])
    turn_summaries: List[Dict[str, Any]] = []
    last_service_offer_context: Dict[str, Any] = {}
    started_at = time.time()
    stop_reason = "turn_limit"
    print(f"Interactive RPG campaign session: {session_id}", flush=True)
    print(f"Target turns: {turns}", flush=True)
    print("Type /quit, /exit, or /stop to finish early.", flush=True)

    for index in range(1, turns + 1):
        if commands:
            player_input = commands.pop(0)
            print(f"\n[{index}/{turns}] PLAYER(scripted)> {player_input}", flush=True)
        else:
            try:
                player_input = input_func(f"\n[{index}/{turns}] PLAYER> ").strip()
            except EOFError:
                stop_reason = "eof"
                break
        if not player_input:
            print("Empty input skipped.", flush=True)
            continue
        if player_input.strip().lower() in STOP_COMMANDS:
            stop_reason = "user_stop_command"
            break

        turn_started = time.perf_counter()
        perf: Dict[str, Any] = {"format_version": "interactive_cli_turn_performance_v1"}

        phase = time.perf_counter()
        turn_summary = _run_one_manual_turn(
            session_id=session_id,
            turn={"player": player_input},
            turn_index=len(turn_summaries) + 1,
            scenario_name="interactive_cli_campaign",
            target_channel="interactive_cli_campaign",
            console_llm=console_llm,
            console_llm_raw=False,
            console_llm_max_chars=4000,
            include_raw_result=include_raw_result,
            artifact_detail=artifact_detail,
        )
        perf["runtime_apply_turn_seconds"] = _elapsed_since(phase)

        phase = time.perf_counter()
        raw_before_repair = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
        current_offer_context = extract_service_offer_context(raw_before_repair)
        perf["offer_context_extract_seconds"] = _elapsed_since(phase)

        phase = time.perf_counter()
        diagnostics = classify_service_intent_with_fallback(
            player_input=player_input,
            current_offer_context=current_offer_context,
            last_offer_context=last_service_offer_context,
            enable_llm=enable_llm_intent_fallback,
            provider_factory=provider_factory,
        )
        perf["intent_router_seconds"] = _elapsed_since(phase)
        turn_summary["interactive_cli_intent_diagnostics"] = diagnostics

        phase = time.perf_counter()
        turn_summary = apply_commerce_followup_repair(turn_summary, player_input=player_input, last_offer_context=last_service_offer_context, persist_session_id=session_id)
        perf["commerce_repair_seconds"] = _elapsed_since(phase)

        phase = time.perf_counter()
        turn_summary = apply_quest_followup_repair(turn_summary, player_input=player_input)
        perf["quest_dialogue_repair_seconds"] = _elapsed_since(phase)

        phase = time.perf_counter()
        raw_after_repair = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
        repaired_context = extract_service_offer_context(raw_after_repair)
        if repaired_context:
            last_service_offer_context = repaired_context
        elif current_offer_context:
            last_service_offer_context = current_offer_context
        turn_summary["narration_source"] = narration_source_for_turn(turn_summary)
        perf["post_repair_context_seconds"] = _elapsed_since(phase)

        phase = time.perf_counter()
        raw_result = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
        narration = _safe_str(turn_summary.get("raw_narration") or _extract_narration(raw_result))
        npc = _safe_dict(turn_summary.get("raw_npc") or raw_result.get("npc"))
        perf["print_prepare_seconds"] = _elapsed_since(phase)
        perf["turn_total_seconds"] = _elapsed_since(turn_started)
        perf["provider_called"] = bool(diagnostics.get("provider_called"))
        perf["narration_source"] = turn_summary.get("narration_source")
        turn_summary["interactive_cli_performance"] = perf
        turn_summaries.append(turn_summary)

        if narration:
            print(f"NARRATION> {narration}", flush=True)
        if npc.get("speaker") and npc.get("line"):
            print(f"{npc['speaker']}> {npc['line']}", flush=True)
        if diagnostics.get("provider_called"):
            print(f"[diagnostic] provider intent classifier called: {diagnostics.get('provider_name')} {diagnostics.get('model')} in {perf.get('intent_router_seconds')}s", flush=True)
        elif diagnostics.get("provider_requested"):
            print(f"[diagnostic] provider intent classifier requested but not called: {diagnostics.get('why_provider_not_called') or diagnostics.get('provider_error')}", flush=True)
        print(f"[performance] turn_total={perf.get('turn_total_seconds')}s runtime={perf.get('runtime_apply_turn_seconds')}s intent_router={perf.get('intent_router_seconds')}s source={turn_summary.get('narration_source')}", flush=True)
        if turn_summary.get("error"):
            print(f"ERROR> {turn_summary['error']}", flush=True)

    ended_at = time.time()
    summary = build_interactive_campaign_summary(run_id=output_dir.name.replace("interactive-cli-campaign-", ""), session_id=session_id, requested_turns=turns, turns=turn_summaries, started_at=started_at, ended_at=ended_at, stop_reason=stop_reason)
    artifacts = write_interactive_campaign_artifacts(output_dir=output_dir, summary=summary, turns=turn_summaries)
    print("\nInteractive campaign complete.", flush=True)
    print(f"Report: {artifacts['html_path']}", flush=True)
    print(f"Performance: {artifacts['performance_path']}", flush=True)
    print(f"ZIP: {artifacts['zip_path']}", flush=True)
    return {"summary": summary, "turns": turn_summaries, "artifacts": artifacts}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an interactive command-line RPG campaign and write review artifacts.")
    parser.add_argument("--turns", type=int, default=30, help="Expected/target number of player turns. Default: 30.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to interactive_cli_<run>.")
    parser.add_argument("--run-id", default="", help="Optional run id for artifact folder naming.")
    parser.add_argument("--output-dir", default="", help="Optional output directory. Defaults under resources/data/test-results.")
    parser.add_argument("--script-file", default="", help="Optional newline-delimited player commands for non-interactive smoke runs.")
    parser.add_argument("--no-reset-session-state", action="store_true", help="Do not delete saved session files before starting.")
    parser.add_argument("--no-console-llm", action="store_true", help="Do not print manual LLM console diagnostics per turn.")
    parser.add_argument("--no-llm-intent-fallback", action="store_true", help="Disable central-provider fallback intent classification for ambiguous service/commerce requests.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed the interactive session with starter survival needs, items, and currency.")
    parser.add_argument("--summary-only", action="store_true", help="Store compact turn summaries instead of raw result payloads.")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run_id = _safe_str(args.run_id).strip() or default_run_id()
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(run_id)
    session_id = _safe_str(args.session_id).strip() or f"interactive_cli_{run_id}"
    commands = read_scripted_commands(args.script_file) if args.script_file else None
    run_interactive_campaign(
        turns=int(args.turns),
        session_id=session_id,
        output_dir=output_dir,
        scripted_commands=commands,
        reset_session=not bool(args.no_reset_session_state),
        console_llm=not bool(args.no_console_llm),
        include_raw_result=not bool(args.summary_only),
        artifact_detail=args.artifact_detail,
        enable_llm_intent_fallback=not bool(args.no_llm_intent_fallback),
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
