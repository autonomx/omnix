from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import difflib
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.rpg.session.runtime import apply_turn
from app.rpg.world.conversation_threads import has_pending_player_conversation_response

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "test-results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "manual_rpg_llm_transcript.txt"
SERVICE_OUTPUT_PATH = OUTPUT_DIR / "manual_rpg_service_scenarios_all.txt"
CODE_DIFF_PATH = OUTPUT_DIR / "code-diff.txt"
RESULTS_ZIP_PATH = OUTPUT_DIR / "manual-rpg-test-results.zip"
TOKEN_USAGE_PATH = OUTPUT_DIR / "token-usage.txt"
CONVERSATION_PATH = OUTPUT_DIR / "conversation.html"
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
RPG_SESSION_DIRS = [
    REPO_ROOT / "resources" / "data" / "rpg_sessions",
    REPO_ROOT / "data" / "rpg_sessions",
]


DEFAULT_MANAGED_SERVER_HEALTH_URLS: List[str] = []
DEFAULT_CODE_DIFF_ROOTS = ["src"]
CODE_DIFF_EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "test-results",
}


_OUTPUTS: Dict[str, List[str]] = {}
_TOKEN_USAGE_ROWS: List[Dict[str, Any]] = []
_REGRESSION_WARNING_ROWS: List[Dict[str, Any]] = []
_REGRESSION_WARNINGS: List[str] = []
_OUTPUT_LOCK = threading.RLock()
_TOKEN_USAGE_LOCK = threading.RLock()
_REGRESSION_WARNING_LOCK = threading.RLock()


def _estimate_tokens_from_text(value: Any) -> int:
    text = "" if value is None else str(value)
    if not text:
        return 0
    # Rough English/code estimate. This is intentionally conservative and
    # provider-agnostic. Exact provider usage is preferred when available.
    return max(1, int(len(text) / 4))


def _extract_token_usage_from_any(value: Any) -> Dict[str, Any]:
    value_dict = _safe_dict(value)
    if not value_dict:
        return {}

    usage = _safe_dict(
        value_dict.get("usage")
        or value_dict.get("token_usage")
        or value_dict.get("tokens")
        or value_dict.get("llm_usage")
    )

    if not usage:
        result = _safe_dict(value_dict.get("result"))
        usage = _safe_dict(
            result.get("usage")
            or result.get("token_usage")
            or result.get("tokens")
            or result.get("llm_usage")
        )

    if not usage:
        narration_debug = _safe_dict(_safe_dict(value_dict.get("result")).get("narration_debug"))
        usage = _safe_dict(
            narration_debug.get("usage")
            or narration_debug.get("token_usage")
            or narration_debug.get("tokens")
            or narration_debug.get("llm_usage")
        )

    if not usage:
        return {}

    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt")
        or usage.get("input")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completion")
        or usage.get("output")
        or 0
    )
    total_tokens = (
        usage.get("total_tokens")
        or usage.get("total")
        or 0
    )

    try:
        prompt_tokens = int(prompt_tokens or 0)
    except Exception:
        prompt_tokens = 0
    try:
        completion_tokens = int(completion_tokens or 0)
    except Exception:
        completion_tokens = 0
    try:
        total_tokens = int(total_tokens or 0)
    except Exception:
        total_tokens = 0

    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "source": "provider",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "raw_usage": usage,
    }


def _extract_token_usage_from_result(result: Dict[str, Any], *, player_input: str = "") -> Dict[str, Any]:
    exact = _extract_token_usage_from_any(result)
    if exact:
        return exact

    narration = _extract_narration(result)
    turn_contract = _extract_turn_contract(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    raw_llm = (
        narration_debug.get("raw_llm_narrative")
        or narration_debug.get("raw_llm_text")
        or result_sub.get("raw_llm_narrative")
        or result_sub.get("raw_llm_text")
        or narration
    )

    estimated_prompt = _estimate_tokens_from_text(player_input) + _estimate_tokens_from_text(turn_contract)
    estimated_completion = _estimate_tokens_from_text(raw_llm or narration)
    return {
        "source": "estimated",
        "prompt_tokens": estimated_prompt,
        "completion_tokens": estimated_completion,
        "total_tokens": estimated_prompt + estimated_completion,
        "raw_usage": {},
    }


def _record_token_usage(
    *,
    scope: str,
    label: str,
    turn: int,
    player_input: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    usage = _extract_token_usage_from_result(result, player_input=player_input)
    row = {
        "scope": scope,
        "label": label,
        "turn": turn,
        "player_input": player_input,
        "source": usage.get("source", ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
    with _TOKEN_USAGE_LOCK:
        _TOKEN_USAGE_ROWS.append(row)
    return row


def _reset_token_usage() -> None:
    with _TOKEN_USAGE_LOCK:
        _TOKEN_USAGE_ROWS.clear()


def _reset_regression_warnings() -> None:
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.clear()
        _REGRESSION_WARNINGS.clear()


def _record_regression_warnings(row: Dict[str, Any]) -> None:
    warnings = _safe_list(row.get("regression_warnings")) + _safe_list(row.get("scenario_warnings"))
    if warnings:
        with _REGRESSION_WARNING_LOCK:
            _REGRESSION_WARNING_ROWS.append(row)


def _record_scenario_error(
    *,
    scenario_name: str,
    session_id: str = "",
    error: str,
) -> None:
    row = {
        "scenario": scenario_name,
        "session_id": session_id,
        "turn": 0,
        "player_input": "",
        "scenario_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
        "regression_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
    }
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.append(row)


def _add_regression_warning(
    *,
    scenario: str,
    turn: int,
    warning: str,
) -> None:
    warning_entry = f"{scenario}:turn_{turn}:{warning}"
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNINGS.append(warning_entry)


def _token_usage_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
    }


def write_token_usage_report(path: Path = TOKEN_USAGE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with _TOKEN_USAGE_LOCK:
        rows = list(_TOKEN_USAGE_ROWS)

    by_scope: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_scope.setdefault(str(row.get("scope") or "unknown"), []).append(row)

    lines: List[str] = []
    lines.append("Manual RPG transcript token usage")
    lines.append("=" * 80)
    lines.append("")
    lines.append("NOTE:")
    lines.append("- source=provider means token counts came from provider/runtime usage metadata.")
    lines.append("- source=estimated means counts are rough char/4 estimates from transcript data.")
    lines.append("")

    totals = _token_usage_totals(rows)
    lines.append("TOTALS")
    lines.append("-" * 80)
    lines.append(_compact_json(totals))
    lines.append("")

    lines.append("TOTALS BY SCOPE")
    lines.append("-" * 80)
    for scope in sorted(by_scope):
        lines.append(scope)
        lines.append(_compact_json(_token_usage_totals(by_scope[scope])))
    lines.append("")

    lines.append("ROWS")
    lines.append("-" * 80)
    lines.append(_compact_json(rows))
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote token usage to: {path.resolve()}", flush=True)


def _emit(value: Any = "", channel: str = "main") -> None:
    text = "" if value is None else str(value)
    print(text, flush=True)
    with _OUTPUT_LOCK:
        _OUTPUTS.setdefault(channel, []).append(text)


def _reset_output(channel: str | None = None) -> None:
    with _OUTPUT_LOCK:
        if channel is None:
            _OUTPUTS.clear()
            return
        _OUTPUTS[channel] = []


def _write_output(path: Path, channel: str = "main") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _OUTPUT_LOCK:
        lines = list(_OUTPUTS.get(channel, []))
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote transcript to: {path.resolve()}", flush=True)


def _write_all_outputs(mapping: Dict[str, Path]) -> None:
    for channel, path in mapping.items():
        _write_output(path, channel=channel)


def _write_current_transcript_outputs() -> None:
    """Write all known transcript channels from the current run.

    This is intentionally called at the end of the top-level run. It prevents
    --all from losing flat transcript files when service scenarios run after
    the flat transcript, especially when scenarios run in parallel.
    """
    with _OUTPUT_LOCK:
        channels = sorted(_OUTPUTS.keys())

    output_map: Dict[str, Path] = {}

    if "flat_summary" in channels:
        output_map["flat_summary"] = OUTPUT_DIR / "manual_rpg_llm_transcript__summary.txt"

    if "flat_legacy" in channels:
        output_map["flat_legacy"] = OUTPUT_PATH

    for channel in channels:
        if channel.startswith("flat_turn_"):
            suffix = channel.replace("flat_turn_", "turn_")
            output_map[channel] = OUTPUT_DIR / f"manual_rpg_llm_transcript__{suffix}.txt"

    if "service_summary" in channels:
        output_map["service_summary"] = OUTPUT_DIR / "manual_rpg_service_scenarios__summary.txt"

    if "service_legacy" in channels:
        output_map["service_legacy"] = SERVICE_OUTPUT_PATH

    for channel in channels:
        if not channel.startswith("service_"):
            continue
        if channel in {"service_summary", "service_legacy"}:
            continue
        scenario_name = channel.replace("service_", "", 1)
        output_map[channel] = OUTPUT_DIR / f"manual_rpg_service_scenarios__{scenario_name}.txt"

    _write_all_outputs(output_map)


def _new_manual_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _default_scenario_workers() -> int:
    raw = os.environ.get("OMNIX_MANUAL_SCENARIO_WORKERS", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            print(
                f"[manual][parallel] invalid OMNIX_MANUAL_SCENARIO_WORKERS={raw!r}; using 4",
                flush=True,
            )
            return 4
    return 4


def _scenario_workers_source() -> str:
    raw = os.environ.get("OMNIX_MANUAL_SCENARIO_WORKERS", "").strip()
    if raw:
        return f"env:OMNIX_MANUAL_SCENARIO_WORKERS={raw}"
    return "default:4"


def _thread_label() -> str:
    current = threading.current_thread()
    return f"{current.name}:{current.ident}"


def _effective_scenario_workers(
    requested_workers: int,
    scenario_count: int,
    *,
    parallel: bool,
) -> int:
    if not parallel:
        return 1
    if scenario_count <= 1:
        return 1
    return max(1, min(int(requested_workers or 1), scenario_count))


def _scoped_session_id(base_session_id: str, run_id: str, *, stable: bool = False) -> str:
    base = str(base_session_id or "").strip() or "manual_test_session"
    if stable:
        return base
    return f"{base}_{run_id}"


def _manual_service_session_id(scenario_name: str, run_id: str, *, stable: bool = False) -> str:
    base = f"manual_service_{scenario_name}"
    if stable:
        return base
    return f"{base}_{run_id}"


def _reset_manual_session_artifacts(session_id: str) -> None:
    """Best-effort delete of saved session artifacts before a manual scenario.

    The normal/default path uses unique run-scoped IDs, so this is mostly for
    --stable-session-ids runs and for local cleanup safety.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        return

    candidate_names = {
        f"{session_id}.json",
        f"{session_id}.rpg.json",
        f"{session_id}.session.json",
    }

    for root in RPG_SESSION_DIRS:
        if not root.exists():
            continue
        for name in candidate_names:
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                try:
                    candidate.unlink()
                    print(f"[manual][session] reset saved session artifact: {candidate}", flush=True)
                except Exception as exc:
                     print(
                         f"[manual][session] failed to delete {candidate}: {type(exc).__name__}: {exc}",
                         flush=True,
                     )


def _default_manual_currency() -> Dict[str, int]:
    return {"gold": 0, "silver": 0, "copper": 0}


def _ensure_manual_simulation_roots(session: Dict[str, Any]) -> Dict[str, Any]:
    setup_payload = _safe_dict(session.get("setup_payload"))
    if not setup_payload:
        setup_payload = {}
        session["setup_payload"] = setup_payload

    metadata = _safe_dict(setup_payload.get("metadata"))
    if not metadata:
        metadata = {}
        setup_payload["metadata"] = metadata

    simulation_state = _safe_dict(metadata.get("simulation_state"))
    if not simulation_state:
        simulation_state = {}
        metadata["simulation_state"] = simulation_state

    return simulation_state


def _sync_manual_simulation_state(session: Dict[str, Any], simulation_state: Dict[str, Any]) -> None:
    setup_payload = _safe_dict(session.get("setup_payload"))
    if not setup_payload:
        setup_payload = {}
        session["setup_payload"] = setup_payload

    metadata = _safe_dict(setup_payload.get("metadata"))
    if not metadata:
        metadata = {}

    session["simulation_state"] = simulation_state
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload


def _sanitize_manual_simulation_state_for_test(
    simulation_state: Dict[str, Any],
    *,
    currency: Dict[str, Any] | None = None,
    reset_player_items: bool = True,
) -> Dict[str, Any]:
    """Remove accumulated living-world/test state from cloned manual sessions.

    The template session may be dirty from previous manual transcript runs.
    Run-scoped session ids prevent file collisions, but they do not prevent
    cloned simulation_state roots from carrying old transaction history,
    memories, journal entries, stock depletion, world events, active services,
    and relationship/emotion data.
    """
    simulation_state = _safe_dict(simulation_state)

    # Runtime/system roots that must start clean for deterministic scenarios.
    simulation_state["transaction_history"] = []
    simulation_state["active_services"] = []
    simulation_state["memory_rumors"] = []
    simulation_state["relationship_state"] = {}
    simulation_state["npc_emotion_state"] = {}
    simulation_state["service_offer_state"] = {}
    simulation_state["journal_state"] = {"entries": []}
    simulation_state["world_event_state"] = {"events": []}

    simulation_state["memory_state"] = {
        "service_memories": [],
        "social_memories": [],
        "npc_memories": {},
        "npc_memories_flat": [],
        "rumors": [],
    }

    # Keep broad scene/location context, but normalize player inventory.
    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {}
        player_state["inventory_state"] = inventory_state

    if reset_player_items:
        inventory_state["items"] = []
        inventory_state["equipment"] = {}
        inventory_state["last_loot"] = []

    inventory_state.setdefault("capacity", 50)
    inventory_state["currency"] = {
        "gold": int(_safe_dict(currency or _default_manual_currency()).get("gold") or 0),
        "silver": int(_safe_dict(currency or _default_manual_currency()).get("silver") or 0),
        "copper": int(_safe_dict(currency or _default_manual_currency()).get("copper") or 0),
    }

    # Keep location coherent if either root exists.
    location_id = (
        _safe_str(simulation_state.get("location_id"))
        or _safe_str(simulation_state.get("current_location_id"))
        or _safe_str(player_state.get("location_id"))
        or _safe_str(player_state.get("current_location_id"))
    )
    if location_id:
        simulation_state["location_id"] = location_id
        simulation_state["current_location_id"] = location_id
        player_state["location_id"] = location_id
        player_state["current_location_id"] = location_id

    return simulation_state


def _sanitize_manual_session_for_test(
    session: Dict[str, Any],
    *,
    currency: Dict[str, Any] | None = None,
    reset_player_items: bool = True,
) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _ensure_manual_simulation_roots(session)
    _sanitize_manual_simulation_state_for_test(
        simulation_state,
        currency=currency,
        reset_player_items=reset_player_items,
    )
    _sync_manual_simulation_state(session, simulation_state)

    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["tick"] = 0
    runtime_state["turn_history"] = []
    runtime_state["last_turn_contract"] = {}
    runtime_state["last_turn_result"] = {}
    runtime_state["last_narration"] = ""
    runtime_state["last_turn_narration"] = ""
    session["runtime_state"] = runtime_state
    return session


def _bootstrap_flat_manual_session(session_id: str) -> bool:
    """Ensure the flat manual transcript session exists before apply_turn.

    Service scenarios already do this through _seed_session_currency(...).
    The flat transcript does not need special currency seeding, but it still
    needs a valid RPG session when run-scoped session ids are used.
    """
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    session = _sanitize_manual_session_for_test(
        session,
        currency=_default_manual_currency(),
        reset_player_items=True,
    )
    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception:
        return False
    return True


def _split_env_list(value: str) -> List[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _command_for_shell(command: str) -> tuple[Any, bool]:
    if os.name == "nt":
        return command, True
    return shlex.split(command), False


def _wait_for_health(url: str, *, timeout_seconds: float = 60.0) -> bool:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3.0) as response:
                status = getattr(response, "status", 0)
                if 200 <= int(status) < 500:
                    return True
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0)

    print(f"[manual][servers] health check timed out: {url} last_error={last_error}", flush=True)
    return False


class ManagedServerGroup:
    def __init__(
        self,
        *,
        commands: Sequence[str],
        health_urls: Sequence[str],
        startup_timeout_seconds: float = 90.0,
        enabled: bool = False,
    ) -> None:
        self.commands = [cmd for cmd in commands if cmd.strip()]
        self.health_urls = [url for url in health_urls if url.strip()]
        self.startup_timeout_seconds = startup_timeout_seconds
        self.enabled = enabled
        self.processes: List[subprocess.Popen[Any]] = []

    def start(self) -> None:
        if not self.enabled:
            return

        if not self.commands:
            print("[manual][servers] --manage-servers set, but no server commands configured.", flush=True)
            return

        print(f"[manual][servers] starting {len(self.commands)} managed server process(es)", flush=True)
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(SRC_ROOT))

        for index, command in enumerate(self.commands, start=1):
            popen_args, shell = _command_for_shell(command)
            print(f"[manual][servers] start {index}: {command}", flush=True)
            process = subprocess.Popen(
                popen_args,
                cwd=str(REPO_ROOT),
                env=env,
                shell=shell,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
                    else 0
                ),
            )
            self.processes.append(process)

        for url in self.health_urls:
            _wait_for_health(url, timeout_seconds=self.startup_timeout_seconds)

    def stop(self) -> None:
        if not self.processes:
            return

        print(f"[manual][servers] stopping {len(self.processes)} managed server process(es)", flush=True)
        for process in reversed(self.processes):
            if process.poll() is None:
                try:
                    if os.name == "nt":
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        process.terminate()
                except Exception:
                    with contextlib.suppress(Exception):
                        process.terminate()

        deadline = time.time() + 10.0
        for process in reversed(self.processes):
            while process.poll() is None and time.time() < deadline:
                time.sleep(0.2)
            if process.poll() is None:
                with contextlib.suppress(Exception):
                    process.kill()

        self.processes.clear()


def _run_git_command(args: List[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return completed.stdout or ""
    except Exception as exc:
        return f"[manual][code-diff] git command failed: git {' '.join(args)}\n{type(exc).__name__}: {exc}\n"


def _git_untracked_files_under_roots(roots: List[Path]) -> List[Path]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--others", "--exclude-standard"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []

    out: List[Path] = []
    root_resolved = [root.resolve() for root in roots]
    for line in (proc.stdout or "").splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = (REPO_ROOT / rel).resolve()
        if any(path == root or root in path.parents for root in root_resolved):
            out.append(path)
    return sorted(out)


def _format_untracked_file_for_diff(path: Path) -> str:
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except Exception:
        rel = str(path)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return (
            f"\n\n# UNTRACKED FILE: {rel}\n"
            f"# Could not read file: {type(exc).__name__}: {exc}\n"
        )

    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"\n\n"
        f"diff --git a/{rel} b/{rel}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{rel}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def _is_diff_candidate(path: Path, roots: Sequence[str]) -> bool:
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return False

    parts = set(rel.parts)
    if parts & CODE_DIFF_EXCLUDE_PARTS:
        return False

    rel_text = rel.as_posix()
    if not any(rel_text == root or rel_text.startswith(f"{root.rstrip('/')}/") for root in roots):
        return False

    if path.suffix in {".pyc", ".pyo", ".pyd", ".dll", ".exe", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip"}:
        return False

    return path.is_file()


def _git_untracked_files(roots: Sequence[str]) -> List[Path]:
    status = _run_git(["status", "--porcelain", "--untracked-files=all", "--", *roots])
    paths: List[Path] = []
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        raw_path = line[3:].strip()
        if not raw_path:
            continue
        candidate = REPO_ROOT / raw_path
        if _is_diff_candidate(candidate, roots):
            paths.append(candidate)
    return sorted(paths)


def _untracked_file_diff(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n[manual][code-diff] binary or non-utf8 file omitted\n\n"
    except Exception as exc:
        return f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n[manual][code-diff] failed to read file: {type(exc).__name__}: {exc}\n\n"

    return "".join(
        difflib.unified_diff(
            [],
            lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def write_code_diff_snapshot(
    path: Path = CODE_DIFF_PATH,
    *,
    roots: List[str] | None = None,
) -> None:
    if roots is None:
        roots = DEFAULT_CODE_DIFF_ROOTS
    path_roots = [Path(r) for r in roots]
    root_args = [str(r) for r in roots]

    diff = _run_git_command(["diff", "--", *root_args])
    untracked_files = _git_untracked_files_under_roots(path_roots)
    if untracked_files:
        diff += "\n\n# Untracked files included by manual_llm_transcript.py\n"
        for untracked in untracked_files:
            diff += _format_untracked_file_for_diff(untracked)
    path.write_text(diff, encoding="utf-8")


def _is_result_zip_candidate(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.resolve() == RESULTS_ZIP_PATH.resolve():
        return False
    if path.suffix.lower() == ".zip":
        return False
    if path.name in {
        "code-diff.txt",
        "token-usage.txt",
        "manual_rpg_llm_transcript.txt",
        "manual_rpg_service_scenarios_all.txt",
        "conversation.html",
    }:
        return True
    if path.name.startswith("manual_rpg_llm_transcript__") and path.suffix == ".txt":
        return True
    if path.name.startswith("manual_rpg_service_scenarios__") and path.suffix == ".txt":
        return True
    if path.name.startswith("manual_rpg_service_scenarios_") and path.suffix == ".txt":
        return True
    return False


def write_results_zip(path: Path = RESULTS_ZIP_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        candidate
        for candidate in OUTPUT_DIR.iterdir()
        if _is_result_zip_candidate(candidate)
    )

    if path.exists():
        path.unlink()

    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for candidate in candidates:
            archive.write(candidate, arcname=candidate.name)

    print(
        f"Wrote results zip to: {path.resolve()} ({len(candidates)} file(s))",
        flush=True,
    )


MANUAL_TEST_TURNS = [
    "I ask Bran for a room to rent",
    "I ask Bran for food",
    "I ask Bran if he has heard any rumors",
    "I ask Bran for directions to the market",
    "I follow Bran's directions to the market",
    "I ask Elara what she sells",
    "I buy a torch from Elara",
    "I ask Elara to repair my gear",
]

SERVICE_SCENARIOS = {
    "lodging_success": {
        "currency": {"gold": 0, "silver": 5, "copper": 0},
        "turns": [
            "I ask Bran for a room to rent",
            "I buy Common room cot from Bran",
        ],
    },
    "shop_success": {
        "currency": {"gold": 0, "silver": 2, "copper": 0},
        "turns": [
            "I follow Bran's directions to the market",
            "I ask Elara what she sells",
            "I buy a torch from Elara",
        ],
    },
    "blocked_purchase": {
        "currency": {"gold": 0, "silver": 1, "copper": 0},
        "turns": [
            "I follow Bran's directions to the market",
            "I ask Elara what she sells",
            "I buy rope from Elara",
        ],
    },
    "paid_info": {
        "currency": {"gold": 0, "silver": 2, "copper": 0},
        "turns": [
            "I ask Bran if he has heard any rumors",
            "I buy Local rumor from Bran",
        ],
    },
    "ambient_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "turns": [
            "I wait and listen to the room",
            "I wait and listen a little longer",
        ],
    },
    "autonomous_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "turns": [
            "__ambient_tick__",
            "__ambient_tick__",
            "__ambient_tick__",
        ],
    },
    "conversation_discusses_event": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_event_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_world_events": [
            {
                "event_id": "manual:event:old_mill_traveler",
                "kind": "travel",
                "title": "A traveler arrived from the old mill road",
                "summary": "A nervous traveler came from the old mill road.",
                "location_id": "loc_tavern",
                "source": "manual_scenario_setup"
            }
        ],
        "turns": ["__ambient_tick_event__"],
    },
    "conversation_discusses_quest": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern"
                }
            ]
        },
        "turns": ["__ambient_tick_quest__"],
    },
    "player_invited_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What do you mean about the old mill?",
        ],
    },
    # ── Bundle H-I-J conversation scenarios ────────────────────────────────────
    #
    # These use the real LLM to produce narrated output. They exercise the full
    # apply_turn pipeline: topic pivot detection, NPC response beats, social
    # state familiarity tracking, and rumor seed propagation.
    #
    "npc_replies_after_player_join": {
        # Scenario: Player is invited into a running NPC conversation, replies,
        # and the NPC must produce a contextually appropriate response beat.
        # LLM narration should acknowledge the NPC responding directly to the player.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "I hear you. Tell me more about what is happening around here.",
        ],
    },
    "player_requests_backed_quest_topic": {
        # Scenario: Player joins a conversation and pivots the topic to a backed
        # active quest. The topic_pivot must be accepted (accepted=True, topic_type=quest).
        # LLM narration should reference the quest ("old mill", "armed figures", etc.).
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "allow_quest_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What can you tell me about the trouble at the old mill road?",
        ],
    },
    "player_requests_unbacked_topic": {
        # Scenario: Player joins and asks about something with no backing in the world
        # state (no quest, event, or memory). topic_pivot must be rejected
        # (accepted=False, pivot_rejected_reason non-empty). The NPC should deflect
        # without fabricating details about the unbacked subject.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the dragon lair hidden in the northern mountains.",
        ],
    },
    "npc_response_uses_social_state": {
        # Scenario: Player joins twice across two separate invitations. After the
        # first join, familiarity accumulates. On the second turn the NPC response
        # style should shift from "guarded" toward "evasive" or "helpful" as
        # familiarity increases. LLM narration should reflect a warmer NPC tone.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "I am happy to chat with you. What is on your mind?",
            "__ambient_tick_player_invited__",
            "Yes, I would love to hear more. You seem like someone worth talking to.",
        ],
    },
    "rumor_seed_from_conversation": {
        # Scenario: NPCs discuss an active quest. The conversation runtime should
        # attach a world signal (quest_interest) which seeds a rumor entry in
        # rumor_propagation_state. LLM narration should reflect NPC discussion of
        # quest-related facts ("old mill road", "armed figures").
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "allow_rumor_propagation": True,
            "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4,
            "max_signal_age_ticks": 20,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",
            "__ambient_tick__",
            "__ambient_tick__",
        ],
    },
    "rumor_signal_expires": {
        # Scenario: A quest rumor seed is created, then multiple ambient ticks
        # advance the clock past max_signal_age_ticks (set to 3 ticks here).
        # By turn 4 the seed should be expired and gone from rumor_propagation_state.
        # LLM narration on later turns should not reference the expired rumor.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "allow_rumor_propagation": True,
            "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4,
            "max_signal_age_ticks": 3,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",   # turn 1 — seeds the rumor (expires_tick = 1 + 3 = 4)
            "__ambient_tick__",          # turn 2 — seed still active
            "__ambient_tick__",          # turn 3 — seed at expiry boundary
            "__ambient_tick__",          # turn 4 — seed should be gone (expired)
            "__ambient_tick__",          # turn 5 — confirm no stale seed re-seeded
        ],
    },
    "npc_goal_influences_response_style": {
        # Scenario: Player is invited into a conversation. NPC goals are seeded so
        # that the dominant goal biases the NPC response style toward goal-driven
        # phrasing. The transcript verifies that npc_goal_state is populated and
        # npc_response_style is present in the result.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_goal_influence": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What should I know about the room?",
        ],
    },
    "scene_activity_schedules_idle_action": {
        # Scenario: Conversation is disabled but scene activities are enabled.
        # Two ambient ticks should each trigger at least one scene activity,
        # visible in scene_activity_state.recent. Hard constraint: no inventory,
        # currency, or transaction mutation.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "off",
            "conversation_chance_percent": 0,
            "allow_scene_activities": True,
            "scene_activity_interval_ticks": 1,
            "scene_activity_cooldown_ticks": 0,
            "allow_scene_activity_world_events": True,
            "allow_scene_activity_world_signals": True,
        },
        "turns": ["__scene_activity_tick__", "__scene_activity_tick__"],
    },
    "scene_activity_respects_cooldown": {
        # Scenario: After the first ambient tick creates a scene activity with
        # cooldown_ticks=10, the second tick must NOT create another activity.
        # scene_activity_state.recent should have at most 1 entry after 2 ticks.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "off",
            "conversation_chance_percent": 0,
            "allow_scene_activities": True,
            "scene_activity_interval_ticks": 1,
            "scene_activity_cooldown_ticks": 10,
        },
        "turns": ["__scene_activity_tick__", "__scene_activity_tick__"],
    },
    # ── Multi-turn NPC-to-NPC conversation (3-4 turns)
    "npc_npc_multiturn_conversation": {
        # Scenario: Two tavern NPCs (Bran and Mira) discuss a traveler who arrived
        # with news from the old mill road. Four ambient ticks drive 3-4 distinct
        # conversational beats. The world event provides a factual anchor so the
        # LLM has something specific to discuss across turns.
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": False,
            "allow_event_discussion": True,
            "allow_quest_discussion": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
            "max_world_events_per_thread": 4,
        },
        "setup_world_events": [
            {
                "event_id": "manual:event:mill_road_traveler",
                "kind": "travel",
                "title": "A traveler arrived from the old mill road",
                "summary": (
                    "A nervous traveler arrived at the Rusty Flagon Tavern from the old mill road, "
                    "speaking of strange lights seen near the mill at dusk and the sound of armed men."
                ),
                "location_id": "loc_tavern",
                "source": "manual_scenario_setup",
            }
        ],
        "turns": [
            "__ambient_tick__",   # turn 1 — Bran and Mira start discussing the traveler
            "__ambient_tick__",   # turn 2 — they speculate about the strange lights
            "__ambient_tick__",   # turn 3 — one of them mentions what they should do
            "__ambient_tick__",   # turn 4 — the conversation reaches a natural conclusion
        ],
    },
    "npc_npc_multiturn_quest_discussion": {
        # Scenario: NPCs carry a 4-turn conversation anchored to an active quest.
        # Each ambient tick adds a new beat to the same thread, building a coherent
        # discussion arc: awareness → detail → speculation → conclusion.
        # The LLM narration across all 4 turns should stay on-topic and reference
        # quest-specific facts ("old mill", "armed figures").
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": False,
            "allow_quest_discussion": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
            "max_world_events_per_thread": 4,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": (
                        "There is talk of armed figures gathering near the old mill road at night. "
                        "Locals are nervous and trade caravans have avoided the route."
                    ),
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",   # turn 1 — NPCs pick up the quest topic
            "__ambient_tick__",          # turn 2 — they share what they know
            "__ambient_tick__",          # turn 3 — speculation about who is involved
            "__ambient_tick__",          # turn 4 — discussion of what should be done
        ],
    },
    "npc_biography_shapes_bran_dialogue": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",
            "What can you tell me about the trouble at the old mill road?",
        ],
    },
    "npc_biography_shapes_mira_dialogue": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "test_force_conversation_speaker_id": "npc:Mira",
            "test_force_conversation_listener_id": "player",
        },
        "setup_memory_state": {
            "social_memories": [
                {
                    "memory_id": "memory:mira:pattern:old_road",
                    "actor_id": "npc:Mira",
                    "target_id": "player",
                    "summary": "Mira noticed that travelers avoid discussing the old road directly.",
                }
            ]
        },
        "setup_conversation_thread_state": {
            "pending_player_response": {
                "thread_id": "conversation:manual:mira:player",
                "topic_id": "topic:memory:memory:mira:pattern:old_road",
                "prompt": "Mira invites your response about the pattern she noticed.",
                "created_tick": 526,
                "expires_tick": 536,
                "source": "manual_scenario_setup",
            },
            "threads": [
                {
                    "thread_id": "conversation:manual:mira:player",
                    "participants": [
                        {"npc_id": "npc:Mira", "name": "Mira"},
                        {"npc_id": "player", "name": "Player"}
                    ],
                    "location_id": "loc_tavern",
                    "topic_id": "topic:memory:memory:mira:pattern:old_road",
                    "topic_type": "memory",
                    "topic": "Mira's observed pattern",
                    "topic_payload": {
                        "topic_id": "topic:memory:memory:mira:pattern:old_road",
                        "topic_type": "memory",
                        "title": "Mira's observed pattern",
                        "summary": "Mira noticed that travelers avoid discussing the old road directly.",
                        "source_id": "memory:mira:pattern:old_road",
                        "source_kind": "memory",
                        "location_id": "loc_tavern",
                        "priority": 4,
                        "allowed_facts": [
                            "Mira noticed that travelers avoid discussing the old road directly."
                        ],
                        "allowed_signal_kinds": ["social_tension", "ambient_interest"],
                        "source": "manual_scenario_setup"
                    },
                    "participation_mode": "player_invited",
                    "player_participation": {
                        "included": True,
                        "mode": "player_invited",
                        "pending_response": True,
                        "prompt": "Mira invites your response about the pattern she noticed.",
                        "topic_id": "topic:memory:memory:mira:pattern:old_road",
                        "created_tick": 526,
                        "expires_tick": 536
                    },
                    "beats": [
                        {
                            "beat_id": "conversation:beat:526:manual:mira:invite",
                            "thread_id": "conversation:manual:mira:player",
                            "speaker_id": "npc:Mira",
                            "speaker_name": "Mira",
                            "listener_id": "player",
                            "listener_name": "Player",
                            "line": "You noticed the same thread, I expect: Mira noticed that travelers avoid discussing the old road directly.",
                            "topic_id": "topic:memory:memory:mira:pattern:old_road",
                            "topic_type": "memory",
                            "topic": "Mira's observed pattern",
                            "tick": 526,
                            "participation_mode": "player_invited",
                            "source": "manual_scenario_setup"
                        }
                    ],
                    "status": "active",
                    "created_tick": 526,
                    "updated_tick": 526,
                    "source": "manual_scenario_setup"
                }
            ],
            "active_thread_ids": ["conversation:manual:mira:player"],
            "world_signals": [],
            "debug": {}
        },
        "turns": [
            "What pattern do you see here?",
        ],
    },
    "npc_biography_blocks_unbacked_secret": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the secret vault under the city.",
        ],
    },
    "npc_roleplay_fallback_validation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "npc_roleplay_fallback_on_invalid": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me something you are not allowed to invent.",
        ],
    },
}


CONVERSATION_EXPECTED_SCENARIOS = {
    "ambient_conversation",
    "autonomous_conversation",
    "conversation_discusses_event",
    "conversation_discusses_quest",
    "player_invited_conversation",
    "npc_replies_after_player_join",
    "player_requests_backed_quest_topic",
    "player_requests_unbacked_topic",
    "npc_response_uses_social_state",
    "rumor_seed_from_conversation",
    "rumor_signal_expires",
    "npc_goal_influences_response_style",
    "npc_biography_shapes_bran_dialogue",
    "npc_biography_shapes_mira_dialogue",
    "npc_biography_blocks_unbacked_secret",
    "npc_roleplay_fallback_validation",
    "npc_npc_multiturn_conversation",
    "npc_npc_multiturn_quest_discussion",
}


SCENE_ACTIVITY_ONLY_SCENARIOS = {
    "scene_activity_schedules_idle_action",
    "scene_activity_respects_cooldown",
}


PROMPTS = MANUAL_TEST_TURNS
LEGACY_PROMPTS = [
    "I ask Bran for a room to rent",
    "I want a better room. I then punch Bran",
    "I throw Bran to the ground",
    "I then apologize to Bran",
    "I ask Bran how he feels",
    "I ask Bran if he still has a room available",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _looks_like_synthetic_social_debug(value: Any) -> bool:
    text = _safe_str(value).lower()
    return any(
        fragment in text
        for fragment in (
            "room/environment",
            "the room/environment",
            "the tavern atmosphere",
            "environment/npcs",
            "npcs (general)",
            "synthetic_social_target",
            "ambient_non_npc_social_target",
            "unknown_or_synthetic_npc_target",
        )
    )



def _clone_or_create_manual_session(session_id: str) -> Dict[str, Any]:
    """
    Manual scenario sessions need to exist before apply_turn(...).

    apply_turn does not create arbitrary session IDs, so clone the known
    manual_test_session shape when available. If the session service exposes
    save/load helpers, persist the clone before running scenario turns.
    """
    try:
        from app.rpg.session.service import load_session, save_session

        existing = load_session(session_id)
        if existing:
            return _safe_dict(existing)

        template = load_session("manual_test_session")
        if template:
            cloned = deepcopy(template)
            manifest = _safe_dict(cloned.get("manifest"))
            manifest["session_id"] = session_id
            manifest["id"] = f"session:{session_id}"
            manifest["title"] = f"Manual Service Scenario: {session_id}"
            cloned["manifest"] = manifest

            cloned = _sanitize_manual_session_for_test(cloned)

            save_session(cloned)
            return cloned
    except Exception:
        pass

    return {}


def _ensure_manual_session(session_id: str) -> Dict[str, Any]:
    session = _clone_or_create_manual_session(session_id)
    if session:
        return session

    warmup = apply_turn(session_id="manual_test_session", player_input="I wait")
    template_session = _extract_session(warmup)
    if not template_session:
        return {}

    try:
        from app.rpg.session.service import save_session

        cloned = deepcopy(template_session)
        manifest = _safe_dict(cloned.get("manifest"))
        manifest["session_id"] = session_id
        manifest["id"] = f"session:{session_id}"
        manifest["title"] = f"Manual Service Scenario: {session_id}"
        cloned["manifest"] = manifest
        cloned = _sanitize_manual_session_for_test(cloned)
        save_session(cloned)
        return cloned
    except Exception:
        return {}


def _extract_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    return _safe_dict(result.get("result") or result)


def _extract_session(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(result).get("session"))


def _extract_simulation_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    session = _extract_session(result)
    direct = dict(_safe_dict(session.get("simulation_state")))
    if direct:
        if _safe_dict(result_sub.get("memory_state")):
            direct["memory_state"] = _safe_dict(result_sub.get("memory_state"))
        if _safe_dict(result_sub.get("relationship_state")):
            direct["relationship_state"] = _safe_dict(result_sub.get("relationship_state"))
        if _safe_dict(result_sub.get("npc_emotion_state")):
            direct["npc_emotion_state"] = _safe_dict(result_sub.get("npc_emotion_state"))
        if _safe_dict(result_sub.get("service_offer_state")):
            direct["service_offer_state"] = _safe_dict(result_sub.get("service_offer_state"))
        return direct

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    simulation_state = dict(_safe_dict(metadata.get("simulation_state")))
    if _safe_dict(result_sub.get("memory_state")):
        simulation_state["memory_state"] = _safe_dict(result_sub.get("memory_state"))
    if _safe_dict(result_sub.get("relationship_state")):
        simulation_state["relationship_state"] = _safe_dict(result_sub.get("relationship_state"))
    if _safe_dict(result_sub.get("npc_emotion_state")):
        simulation_state["npc_emotion_state"] = _safe_dict(result_sub.get("npc_emotion_state"))
    if _safe_dict(result_sub.get("service_offer_state")):
        simulation_state["service_offer_state"] = _safe_dict(result_sub.get("service_offer_state"))
    return simulation_state


def _extract_scene_activity_state(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("scene_activity_state"))


def _extract_npc_response_style(result: Dict[str, Any]) -> str:
    conversation = _extract_conversation_result(result)
    style = _safe_str(conversation.get("npc_response_style"))
    if style:
        return style
    style = _safe_str(_safe_dict(conversation.get("npc_response_beat")).get("response_style"))
    if style:
        return style
    return _safe_str(_safe_dict(conversation.get("beat")).get("response_style"))


def _pre_turn_contamination_snapshot(simulation_state: Dict[str, Any]) -> Dict[str, int]:
    if not simulation_state:
        return {
            "transaction_history_count": 0,
            "active_services_count": 0,
            "journal_entry_count": 0,
            "world_event_count": 0,
            "quest_count": 0,
        }

    journal_state = _safe_dict(simulation_state.get("journal_state"))
    world_event_state = _safe_dict(simulation_state.get("world_event_state"))
    quest_state = _safe_dict(simulation_state.get("quest_state"))
    return {
        "transaction_history_count": len(_safe_list(simulation_state.get("transaction_history"))),
        "active_services_count": len(_safe_list(simulation_state.get("active_services"))),
        "journal_entry_count": len(_safe_list(journal_state.get("entries"))),
        "world_event_count": len(_safe_list(world_event_state.get("events"))),
        "quest_count": len(_safe_list(quest_state.get("quests"))),
    }


def _extract_player_inventory(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))
    return _safe_dict(player_state.get("inventory_state"))


def _extract_player_currency(result: Dict[str, Any]) -> Dict[str, Any]:
    inventory_state = _extract_player_inventory(result)
    return _safe_dict(inventory_state.get("currency"))


def _extract_player_items(result: Dict[str, Any]) -> List[Any]:
    inventory_state = _extract_player_inventory(result)
    return _safe_list(inventory_state.get("items"))


def _extract_active_services(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    return _safe_list(simulation_state.get("active_services"))


def _extract_memory_rumors(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    return _safe_list(memory_state.get("rumors"))


def _extract_transaction_history(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    history = list(_safe_list(simulation_state.get("transaction_history")))

    service_debug = _extract_service_debug(result)
    current_record = _safe_dict(service_debug.get("transaction_record"))

    if current_record:
        current_id = _safe_str(current_record.get("transaction_id"))
        existing_ids = {
            _safe_str(_safe_dict(record).get("transaction_id"))
            for record in history
        }
        if not current_id or current_id not in existing_ids:
            history.append(current_record)

    return history


def _extract_service_memories(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    memories = list(_safe_list(memory_state.get("service_memories")))

    # Fallback: some result envelopes expose the current deterministic memory
    # entry before the mutated memory_state root is visible in the saved session.
    service_debug = _extract_service_debug(result)
    current_entry = _safe_dict(service_debug.get("memory_entry"))
    if current_entry:
        current_id = _safe_str(current_entry.get("memory_id"))
        existing_ids = {
            _safe_str(_safe_dict(entry).get("memory_id"))
            for entry in memories
        }
        if not current_id or current_id not in existing_ids:
            memories.append(current_entry)

    return memories


def _extract_relationship_state(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    relationship_state = dict(_safe_dict(simulation_state.get("relationship_state")))
    service_debug = _extract_service_debug(result)
    social_effects = _safe_dict(service_debug.get("social_effects"))
    key = _safe_str(social_effects.get("relationship_key"))
    relationship = _safe_dict(social_effects.get("relationship"))

    # Prefer the freshly applied deterministic relationship when the persisted
    # state is stale/empty for this key.
    if key and relationship:
        existing = _safe_dict(relationship_state.get(key))
        existing_axes = _safe_dict(existing.get("axes"))
        fresh_axes = _safe_dict(relationship.get("axes"))
        if fresh_axes and not existing_axes:
            relationship_state[key] = relationship

    return relationship_state


def _extract_npc_emotion_state(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    npc_emotion_state = dict(_safe_dict(simulation_state.get("npc_emotion_state")))
    service_debug = _extract_service_debug(result)
    social_effects = _safe_dict(service_debug.get("social_effects"))
    emotion = _safe_dict(social_effects.get("emotion"))
    owner_id = _safe_str(emotion.get("owner_id"))

    if owner_id and emotion and owner_id not in npc_emotion_state:
        npc_emotion_state[owner_id] = emotion

    return npc_emotion_state


def _extract_service_offer_state(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    service_offer_state = dict(_safe_dict(simulation_state.get("service_offer_state")))
    offers = _safe_dict(service_offer_state.get("offers"))
    if not offers:
        offers = {}
        service_offer_state["offers"] = offers

    service_debug = _extract_service_debug(result)
    stock_update = _safe_dict(service_debug.get("stock_update"))
    offer_id = _safe_str(stock_update.get("offer_id"))
    runtime_state = _safe_dict(stock_update.get("runtime_state"))

    if offer_id and runtime_state and offer_id not in offers:
        offers[offer_id] = runtime_state

    # Keep output compact: if there are still no offers, return the original
    # empty state rather than {"offers": {}}.
    if not offers and not _safe_dict(simulation_state.get("service_offer_state")):
        return {}

    return service_offer_state


def _extract_recalled_service_memories(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_list(narration_debug.get("recalled_service_memories"))
    current_memory_id = _safe_str(_safe_dict(_extract_service_debug(result).get("memory_entry")).get("memory_id"))
    if direct:
        return [
            memory
            for memory in direct
            if _safe_str(_safe_dict(memory).get("memory_id")) != current_memory_id
        ]

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return [
        memory
        for memory in _safe_list(resolved.get("recalled_service_memories"))
        if _safe_str(_safe_dict(memory).get("memory_id")) != current_memory_id
    ]


def _extract_service_memory_recall_debug(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_dict(narration_debug.get("service_memory_recall_debug"))
    if direct:
        return direct

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("service_memory_recall_debug"))


def _extract_recalled_npc_memories(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_list(narration_debug.get("recalled_npc_memories"))
    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    current_memory_id = _safe_str(
        _safe_dict(
            resolved.get("memory_entry")
            or _safe_dict(resolved.get("social_living_world_effects")).get("memory_entry")
            or _safe_dict(_safe_dict(resolved.get("service_application")).get("memory_entry"))
        ).get("memory_id")
    )

    memories = direct or _safe_list(resolved.get("recalled_npc_memories"))
    if not current_memory_id:
        return memories
    return [
        memory
        for memory in memories
        if _safe_str(_safe_dict(memory).get("memory_id")) != current_memory_id
    ]


def _extract_npc_memory_recall_debug(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_dict(narration_debug.get("npc_memory_recall_debug"))
    if direct:
        return direct

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("npc_memory_recall_debug"))


def _extract_social_living_world_effects(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("social_living_world_effects"))
    if direct:
        return direct

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("social_living_world_effects"))


def _extract_living_world_debug(result: Dict[str, Any]) -> Dict[str, Any]:
    service_debug = _extract_service_debug(result)
    resolved = _safe_dict(service_debug.get("resolved_result"))
    direct = _safe_dict(resolved.get("living_world_debug"))
    if direct:
        return direct
    return {
        "memory_entry": service_debug.get("memory_entry"),
        "social_effects": service_debug.get("social_effects"),
        "stock_update": service_debug.get("stock_update"),
        "rumor_added": service_debug.get("rumor_added"),
        "journal_entry": service_debug.get("journal_entry"),
        "service_world_event": service_debug.get("service_world_event"),
        "rumor_world_event": service_debug.get("rumor_world_event"),
    }


def _extract_journal_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("journal_state"))
    if direct:
        return direct
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("journal_state"))


def _extract_world_event_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("world_event_state"))
    if direct:
        return direct
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("world_event_state"))


def _extract_location_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("location_state"))
    if direct:
        return direct
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("location_state"))


def _extract_current_location_id(result: Dict[str, Any]) -> str:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    if _safe_str(result_sub.get("current_location_id")):
        return _safe_str(result_sub.get("current_location_id"))

    location_state = _extract_location_state(result)
    if _safe_str(location_state.get("current_location_id")):
        return _safe_str(location_state.get("current_location_id"))

    service_result = _safe_dict(_extract_service_debug(result).get("service_result"))
    if _safe_str(service_result.get("current_location_id")):
        return _safe_str(service_result.get("current_location_id"))

    travel_result = _extract_travel_result(result)
    if _safe_str(travel_result.get("to_location_id")):
        return _safe_str(travel_result.get("to_location_id"))
    if _safe_str(travel_result.get("from_location_id")):
        return _safe_str(travel_result.get("from_location_id"))

    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))
    return (
        _safe_str(player_state.get("location_id"))
        or _safe_str(simulation_state.get("location_id"))
        or _safe_str(simulation_state.get("current_location_id"))
    )


def _extract_travel_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("travel_result"))
    if direct:
        return direct
    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("travel_result"))

def _extract_conversation_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("conversation_result"))
    if direct:
        return direct
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_dict(narration_debug.get("conversation_result"))
    if direct:
        return direct
    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("conversation_result"))


def _extract_ambient_tick_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("ambient_tick_result"))
    if direct:
        return direct

    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_dict(narration_debug.get("ambient_tick_result"))
    if direct:
        return direct

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    direct = _safe_dict(resolved.get("ambient_tick_result"))
    if direct:
        return direct

    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("ambient_tick_result"))


def _extract_conversation_thread_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    direct = _safe_dict(result_sub.get("conversation_thread_state"))
    if direct:
        return direct
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    direct = _safe_dict(narration_debug.get("conversation_thread_state"))
    if direct:
        return direct
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("conversation_thread_state"))


def _extract_conversation_rumor_state(result: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _safe_dict(_safe_dict(_safe_dict(result).get("result")).get("resolved_result"))
    direct = _safe_dict(resolved.get("conversation_rumor_state"))
    if direct:
        return direct
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("conversation_rumor_state"))


def _extract_npc_goal_state(result: Dict[str, Any]) -> Dict[str, Any]:
    conversation = _extract_conversation_result(result)
    if _safe_dict(conversation.get("npc_goal_state")):
        return _safe_dict(conversation.get("npc_goal_state"))
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("npc_goal_state"))


def _extract_scene_activity_state(result: Dict[str, Any]) -> Dict[str, Any]:
    ambient = _extract_ambient_tick_result(result)
    scene = _safe_dict(ambient.get("scene_activity_result"))
    if _safe_dict(scene.get("scene_activity_state")):
        return _safe_dict(scene.get("scene_activity_state"))
    simulation_state = _extract_simulation_state(result)
    return _safe_dict(simulation_state.get("scene_activity_state"))


def _effective_service_status(
    service_result: Dict[str, Any],
    service_application: Dict[str, Any],
) -> str:
    purchase = _safe_dict(service_result.get("purchase"))
    if bool(service_application.get("applied") or purchase.get("applied")):
        return "purchased"
    return _safe_str(service_result.get("status"))


def _compact_turn_summary(
    *,
    index: int,
    player_input: str,
    result: Dict[str, Any],
    before_currency: Dict[str, Any] | None = None,
    before_items: List[Any] | None = None,
) -> Dict[str, Any]:
    service_debug = _extract_service_debug(result)
    service_result = _safe_dict(service_debug.get("service_result"))
    purchase = _safe_dict(service_debug.get("purchase"))
    service_application = _safe_dict(service_debug.get("service_application"))
    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    semantic_action = _safe_dict(
        resolved.get("semantic_action")
        or turn_contract.get("semantic_action")
        or _safe_dict(_safe_dict(turn_contract.get("action")).get("metadata")).get("semantic_action")
    )

    narration = _extract_narration(result)

    return {
        "turn": index,
        "player_input": player_input,
        "contract_version": turn_contract.get("version"),
        "contract_source": turn_contract.get("contract_source"),
        "action_type": _safe_str(
            _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("action_type")
            or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("action_type")
            or _safe_dict(_safe_dict(result).get("result")).get("action_type")
        ),
        "semantic_action_type": _safe_str(
            _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("semantic_action_type")
            or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("semantic_action_type")
            or _safe_dict(_safe_dict(result).get("result")).get("semantic_action_type")
        ),
        "semantic_family": _safe_str(
            _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("semantic_family")
            or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("semantic_family")
            or _safe_dict(_safe_dict(result).get("result")).get("semantic_family")
        ),
        "activity_label": semantic_action.get("activity_label"),
        "service_kind": service_result.get("service_kind"),
        "service_status": _effective_service_status(service_result, service_application),
        "selected_offer_id": service_result.get("selected_offer_id"),
        "purchase_blocked": purchase.get("blocked"),
        "purchase_applied": bool(
            purchase.get("applied")
            or service_application.get("applied")
        ),
        "blocked_reason": purchase.get("blocked_reason"),
        "currency_before": before_currency or {},
        "currency_after": _effective_player_currency_after(result),
        "items_before_count": len(before_items or []),
        "items_after": _extract_player_items(result),
        "active_services": _extract_active_services(result),
        "memory_rumors": _extract_memory_rumors(result),
        "transaction_record": service_debug.get("transaction_record"),
        "transaction_history_count": len(_extract_transaction_history(result)),
        "memory_entry": service_debug.get("memory_entry"),
        "service_memory_count": len(_extract_service_memories(result)),
        "recalled_service_memories": _extract_recalled_service_memories(result),
        "recalled_service_memory_count": len(_extract_recalled_service_memories(result)),
        "service_memory_recall_debug": _extract_service_memory_recall_debug(result),
        "recalled_npc_memories": _extract_recalled_npc_memories(result),
        "recalled_npc_memory_count": len(_extract_recalled_npc_memories(result)),
        "npc_memory_recall_debug": _extract_npc_memory_recall_debug(result),
        "relationship_state": _extract_relationship_state(result),
        "npc_emotion_state": _extract_npc_emotion_state(result),
        "social_effects": service_debug.get("social_effects"),
        "social_living_world_effects": _extract_social_living_world_effects(result),
        "stock_update": service_debug.get("stock_update"),
        "service_offer_state": _extract_service_offer_state(result),
        "living_world_debug": _extract_living_world_debug(result),
        "journal_state": _extract_journal_state(result),
        "journal_entry_count": len(_safe_list(_extract_journal_state(result).get("entries"))),
        "world_event_state": _extract_world_event_state(result),
        "world_event_count": len(_safe_list(_extract_world_event_state(result).get("events"))),
        "current_location_id": _extract_current_location_id(result),
        "location_state": _extract_location_state(result),
        "travel_result": _extract_travel_result(result),
        "conversation_result": _extract_conversation_result(result),
        "ambient_tick_result": _extract_ambient_tick_result(result),
        "conversation_thread_state": _extract_conversation_thread_state(result),
        "conversation_thread_count": len(_safe_list(_extract_conversation_thread_state(result).get("threads"))),
        "conversation_world_signal_count": len(_safe_list(_extract_conversation_thread_state(result).get("world_signals"))),
        "ambient_tick_applied": bool(_extract_ambient_tick_result(result).get("applied")),
        "ambient_tick_status": _safe_str(_extract_ambient_tick_result(result).get("status")),
        "pending_player_response": _safe_dict(
            _extract_conversation_thread_state(result).get("pending_player_response")
        ),
        "regression_warnings": _manual_regression_warnings(
            turn_index=index,
            player_input=player_input,
            result=result,
        ),
        "token_usage": _extract_token_usage_from_result(result, player_input=player_input),
        "available_actions": service_debug.get("available_actions"),
        "narration_preview": narration[:500] if narration else "",
        "ok": not bool(_safe_dict(result).get("error")),
        "error": _safe_dict(result).get("error"),
    }


def _emit_summary_block(title: str, rows: List[Dict[str, Any]], channel: str) -> None:
    _emit(title, channel=channel)
    _emit("=" * len(title), channel=channel)
    _emit("", channel=channel)
    _emit(_compact_json(rows), channel=channel)
    _emit("", channel=channel)


def _scenario_contamination_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    before_currency: Dict[str, Any] | None,
    before_items: List[Any] | None,
    result: Dict[str, Any],
    pre_turn_snapshot: Dict[str, int] | None = None,
    allows_seeded_world_events: bool = False,
    allows_seeded_journal_entries: bool = False,
    allows_seeded_quest_state: bool = False,
) -> List[str]:
    warnings: List[str] = []
    if turn_index == 1:
        active_services = _extract_active_services(result)
        transaction_history = _extract_transaction_history(result)
        journal_state = _extract_journal_state(result)
        world_event_state = _extract_world_event_state(result)
        if transaction_history:
            warnings.append("scenario_started_with_transaction_history")
        if active_services:
            warnings.append("scenario_started_with_active_services")
        if (
            int(pre_turn_snapshot.get("journal_entry_count") or 0) > 0
            and not allows_seeded_journal_entries
        ):
            warnings.append("scenario_started_with_journal_entries")
        if (
            int(pre_turn_snapshot.get("world_event_count") or 0) > 0
            and not allows_seeded_world_events
        ):
            warnings.append("scenario_started_with_world_events")

        if (
            int(pre_turn_snapshot.get("quest_count") or 0) > 0
            and not allows_seeded_quest_state
        ):
            warnings.append("scenario_started_with_quest_state")

    if scenario_name == "shop_success" and turn_index == 1:
        item_ids = {
            _safe_str(_safe_dict(item).get("item_id"))
            for item in (before_items or [])
        }
        if "torch" in item_ids:
            warnings.append("shop_success_started_with_torch")

    return warnings


def _player_facing_text_for_regression_scan(result: Dict[str, Any]) -> str:
    text = _extract_narration(result)
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    if not text:
        text = _safe_str(result_sub.get("narration"))
    return text or ""


def _current_memory_ids(result: Dict[str, Any]) -> set[str]:
    service_debug = _extract_service_debug(result)
    ids: set[str] = set()

    for candidate in (
        service_debug.get("memory_entry"),
        _safe_dict(_extract_social_living_world_effects(result)).get("memory_entry"),
    ):
        memory_id = _safe_str(_safe_dict(candidate).get("memory_id"))
        if memory_id:
            ids.add(memory_id)

    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    for candidate in (
        resolved.get("memory_entry"),
        _safe_dict(resolved.get("service_application")).get("memory_entry"),
        _safe_dict(resolved.get("social_living_world_effects")).get("memory_entry"),
    ):
        memory_id = _safe_str(_safe_dict(candidate).get("memory_id"))
        if memory_id:
            ids.add(memory_id)

    return ids


def _manual_regression_warnings(
    *,
    scenario_name: str = "",
    turn_index: int,
    player_input: str,
    result: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []
    text = _player_facing_text_for_regression_scan(result)
    lower = text.lower()

    if "the attempt fails" in lower:
        warnings.append("player_facing_generic_attempt_fails")
    if "registered offer" in lower or "registered offers" in lower:
        warnings.append("player_facing_registered_offer_leak")
    if "session_not_found" in lower or _safe_str(_safe_dict(result).get("error")) == "session_not_found":
        warnings.append("session_not_found")

    current_ids = _current_memory_ids(result)
    if current_ids:
        recalled = _extract_recalled_service_memories(result) + _extract_recalled_npc_memories(result)
        recalled_ids = {
            _safe_str(_safe_dict(memory).get("memory_id"))
            for memory in recalled
            if _safe_str(_safe_dict(memory).get("memory_id"))
        }
        overlap = sorted(current_ids & recalled_ids)
        if overlap:
            warnings.append(f"current_turn_memory_recalled:{','.join(overlap)}")

    service_debug = _extract_service_debug(result)
    service_result = _safe_dict(service_debug.get("service_result"))
    purchase = _safe_dict(service_debug.get("purchase"))
    service_application = _safe_dict(service_debug.get("service_application"))
    service_status = _effective_service_status(service_result, service_application)
    travel_result = _extract_travel_result(result)
    action_type = _safe_str(
        _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("action_type")
        or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("action_type")
        or _safe_dict(_safe_dict(result).get("result")).get("action_type")
    )
    semantic_action_type = _safe_str(
        _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("semantic_action_type")
        or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("semantic_action_type")
        or _safe_dict(_safe_dict(result).get("result")).get("semantic_action_type")
    )
    semantic_family = _safe_str(
        _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("semantic_family")
        or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("semantic_family")
        or _safe_dict(_safe_dict(result).get("result")).get("semantic_family")
    )
    player_lower = _safe_str(player_input).lower()

    conversation = _extract_conversation_result(result)
    conversation_triggered = bool(conversation.get("triggered"))

    if (
        conversation.get("triggered")
        and scenario_name not in CONVERSATION_EXPECTED_SCENARIOS
        and scenario_name not in SCENE_ACTIVITY_ONLY_SCENARIOS
    ):
        warnings.append("conversation_triggered_in_non_conversation_scenario")

    if scenario_name in SCENE_ACTIVITY_ONLY_SCENARIOS and conversation.get("triggered"):
        warnings.append("conversation_triggered_in_scene_activity_only_scenario")

    conversation = _extract_conversation_result(result)
    conversation_reason = _safe_str(conversation.get("reason"))
    pending_consumed = conversation_reason == "pending_player_response_consumed"

    if conversation_triggered and service_result.get("matched") and not pending_consumed:
        warnings.append("conversation_triggered_during_service_turn")

    if conversation_triggered and _safe_dict(_extract_travel_result(result)).get("matched"):
        warnings.append("conversation_triggered_during_travel_turn")

    if conversation_triggered and action_type in {"service_inquiry", "service_purchase", "travel"} and not pending_consumed:
        warnings.append(f"conversation_triggered_during_action_type:{action_type}")
    if conversation_triggered and action_type == "social_activity" and not has_pending_player_conversation_response(_extract_simulation_state(result), tick=_safe_int(_safe_dict(_extract_turn_contract(result).get("resolved_result")).get("current_tick"), 0)):
        warnings.append("conversation_triggered_during_action_type:social_activity")

    if (
        "ask" in player_lower
        and "directions" in player_lower
        and bool(travel_result.get("applied"))
    ):
        warnings.append("directions_inquiry_unexpectedly_travelled")

    if (
        ("follow" in player_lower and "directions" in player_lower)
        and not bool(travel_result.get("applied"))
    ):
        warnings.append("follow_directions_expected_travel_success")

    if _safe_str(service_result.get("kind")) == "service_purchase":
        if service_status == "blocked" and not _safe_str(purchase.get("blocked_reason")):
            warnings.append("blocked_purchase_missing_reason")
        if bool(purchase.get("applied") or service_application.get("applied")) and not _safe_dict(service_debug.get("transaction_record")):
            warnings.append("applied_purchase_missing_transaction_record")

    # Scenario-specific expectations.
    if scenario_name == "shop_success" and turn_index == 3:
        if not bool(purchase.get("applied") or service_application.get("applied")):
            warnings.append("shop_success_expected_purchase_applied")
    if scenario_name == "lodging_success" and turn_index == 2:
        if not bool(purchase.get("applied") or service_application.get("applied")):
            warnings.append("lodging_success_expected_purchase_applied")
    if scenario_name == "paid_info" and turn_index == 2:
        if not _safe_dict(service_debug.get("rumor_added")).get("rumor_id"):
            warnings.append("paid_info_missing_rumor_added")
        if not _safe_dict(service_debug.get("journal_entry")).get("entry_id"):
            warnings.append("paid_info_missing_journal_entry")
    if scenario_name == "ambient_conversation":
        conversation = _extract_conversation_result(result)
        if not conversation.get("triggered"):
            warnings.append("ambient_conversation_expected_thread_trigger")
        state = _extract_conversation_thread_state(result)
        if not _safe_list(state.get("world_signals")):
            warnings.append("ambient_conversation_expected_world_signal")
        action_type = _safe_str(
            _safe_dict(_extract_turn_contract(result).get("resolved_result")).get("action_type")
            or _safe_dict(_extract_turn_contract(result).get("resolved_action")).get("action_type")
            or _safe_dict(_safe_dict(result).get("result")).get("action_type")
        )
        if service_result.get("matched"):
            warnings.append("ambient_conversation_unexpected_service_result")
        if service_status not in {"", "not_service", "none"} and service_result.get("matched"):
            warnings.append("ambient_conversation_unexpected_service_status")
        if action_type in {"service_inquiry", "service_purchase"}:
            warnings.append("ambient_conversation_unexpected_commerce_action")
        service_debug = _extract_service_debug(result)
        memory_entry = _safe_dict(service_debug.get("memory_entry"))
        if memory_entry:
            warnings.append("ambient_conversation_unexpected_service_memory")

        simulation_state = _extract_simulation_state(result)
        memory_state = _safe_dict(simulation_state.get("memory_state"))
        social_memories = _safe_list(memory_state.get("social_memories"))
        for memory in social_memories:
            if _looks_like_synthetic_social_debug(memory):
                warnings.append("synthetic_environment_social_memory_created")

        relationship_state = _safe_dict(simulation_state.get("relationship_state"))
        for key, value in relationship_state.items():
            if _looks_like_synthetic_social_debug(key) or _looks_like_synthetic_social_debug(value):
                warnings.append("synthetic_environment_relationship_created")

        emotion_state = _safe_dict(simulation_state.get("npc_emotion_state"))
        for key, value in emotion_state.items():
            if _looks_like_synthetic_social_debug(key) or _looks_like_synthetic_social_debug(value):
                warnings.append("synthetic_environment_emotion_state_created")
        world_events = _safe_list(_extract_world_event_state(result).get("events"))
        if any(_safe_str(_safe_dict(event).get("kind")).startswith("service_") for event in world_events):
            warnings.append("ambient_conversation_unexpected_service_world_event")
    if scenario_name in {
        "autonomous_conversation",
        "conversation_discusses_event",
        "conversation_discusses_quest",
        "player_invited_conversation",
    }:
        conversation = _extract_conversation_result(result)
        if turn_index == 1 and not conversation.get("triggered"):
            warnings.append(f"{scenario_name}_expected_conversation_trigger")
        if service_result.get("matched"):
            warnings.append(f"{scenario_name}_unexpected_service_result")
        state = _extract_conversation_thread_state(result)
        if turn_index == 1 and not _safe_list(state.get("world_signals")):
            warnings.append(f"{scenario_name}_expected_world_signal")
        validation = _safe_dict(conversation.get("conversation_effect_validation"))
        if validation and not validation.get("ok"):
            warnings.append(f"{scenario_name}_conversation_effect_validation_failed")
    if scenario_name == "conversation_discusses_event":
        topic = _safe_dict(_extract_conversation_result(result).get("topic"))
        if _safe_str(topic.get("topic_type")) != "recent_event":
            warnings.append("conversation_discusses_event_expected_recent_event_topic")

    if scenario_name == "conversation_discusses_quest":
        topic = _safe_dict(_extract_conversation_result(result).get("topic"))
        if _safe_str(topic.get("topic_type")) != "quest":
            warnings.append("conversation_discusses_quest_expected_quest_topic")

    if scenario_name == "player_invited_conversation" and turn_index == 1:
        participation = _safe_dict(_extract_conversation_result(result).get("player_participation"))
        if _safe_str(participation.get("mode")) != "player_invited":
            warnings.append("player_invited_conversation_expected_player_invited_mode")
        if not participation.get("pending_response"):
            warnings.append("player_invited_conversation_expected_pending_response")

    # ── Bundle H-I-J scenario-specific regression checks ────────────────────────

    _player_invited_turn1_scenarios = {
        "npc_replies_after_player_join",
        "player_requests_backed_quest_topic",
        "player_requests_unbacked_topic",
        "npc_response_uses_social_state",
    }
    if scenario_name in _player_invited_turn1_scenarios and turn_index == 1:
        participation = _safe_dict(_extract_conversation_result(result).get("player_participation"))
        if _safe_str(participation.get("mode")) != "player_invited":
            warnings.append(f"{scenario_name}_expected_player_invited_mode_on_turn_1")
        if not participation.get("pending_response"):
            warnings.append(f"{scenario_name}_expected_pending_response_on_turn_1")

    if scenario_name in _player_invited_turn1_scenarios and turn_index == 3:
        # npc_response_uses_social_state has a second invite at turn 3
        participation = _safe_dict(_extract_conversation_result(result).get("player_participation"))
        if scenario_name == "npc_response_uses_social_state" and _safe_str(participation.get("mode")) != "player_invited":
            warnings.append("npc_response_uses_social_state_expected_second_player_invite")

    if scenario_name == "npc_replies_after_player_join" and turn_index == 2:
        conv = _extract_conversation_result(result)
        npc_beat = _safe_dict(conv.get("npc_response_beat"))
        if not npc_beat:
            warnings.append("npc_replies_after_player_join_missing_npc_response_beat")
        elif not _safe_str(npc_beat.get("line")):
            warnings.append("npc_replies_after_player_join_npc_response_beat_empty_line")
        if not conv.get("topic_pivot"):
            warnings.append("npc_replies_after_player_join_missing_topic_pivot_dict")

    if scenario_name == "player_requests_backed_quest_topic" and turn_index == 2:
        conv = _extract_conversation_result(result)
        pivot = _safe_dict(conv.get("topic_pivot"))
        if not pivot:
            warnings.append("player_requests_backed_quest_topic_missing_topic_pivot")
        else:
            if pivot.get("accepted") is not True:
                warnings.append("player_requests_backed_quest_topic_expected_pivot_accepted_true")
            pivot_topic_type = (
                _safe_str(pivot.get("topic_type"))
                or _safe_str(pivot.get("selected_topic_type"))
                or _safe_str(_safe_dict(pivot.get("selected_topic")).get("topic_type"))
            )
            if pivot_topic_type != "quest":
                warnings.append(
                    f"player_requests_backed_quest_topic_expected_quest_type_got_{pivot_topic_type or 'none'}"
                )
            if pivot.get("pivot_rejected_reason"):
                warnings.append("player_requests_backed_quest_topic_unexpected_rejection_reason")
        npc_beat = _safe_dict(conv.get("npc_response_beat"))
        if not npc_beat:
            warnings.append("player_requests_backed_quest_topic_missing_npc_response_beat")

    if scenario_name == "player_requests_unbacked_topic" and turn_index == 2:
        conv = _extract_conversation_result(result)
        pivot = _safe_dict(conv.get("topic_pivot"))
        if not pivot:
            warnings.append("player_requests_unbacked_topic_missing_topic_pivot")
        else:
            if not pivot.get("requested"):
                warnings.append("player_requests_unbacked_topic_expected_pivot_requested")
            if pivot.get("accepted") is not False:
                warnings.append("player_requests_unbacked_topic_expected_pivot_accepted_false")
            if not _safe_str(pivot.get("pivot_rejected_reason") or pivot.get("reason")):
                warnings.append("player_requests_unbacked_topic_expected_rejection_reason")
            if _safe_str(pivot.get("pivot_rejected_reason") or pivot.get("reason")) not in {
                "no_backed_topic_found",
                "requested_topic_not_backed_by_state",
            }:
                warnings.append("player_requests_unbacked_topic_expected_no_backed_topic_reason")
        npc_beat = _safe_dict(conv.get("npc_response_beat"))
        if not npc_beat:
            warnings.append("player_requests_unbacked_topic_missing_npc_deflection_beat")
        elif not _safe_str(npc_beat.get("line")):
            warnings.append("player_requests_unbacked_topic_npc_deflection_beat_empty_line")

    if scenario_name == "npc_response_uses_social_state" and turn_index == 2:
        conv = _extract_conversation_result(result)
        npc_beat = _safe_dict(conv.get("npc_response_beat"))
        if not npc_beat:
            warnings.append("npc_response_uses_social_state_missing_npc_beat_turn_2")
        elif not _safe_str(npc_beat.get("response_style")):
            warnings.append("npc_response_uses_social_state_missing_response_style_turn_2")

    if scenario_name in {"rumor_seed_from_conversation", "npc_npc_multiturn_quest_discussion"} and turn_index == 1:
        conv_thread_state = _extract_conversation_thread_state(result)
        world_signals = _safe_list(conv_thread_state.get("world_signals"))
        quest_signals = [
            s for s in world_signals
            if _safe_str(_safe_dict(s).get("kind")) in {
                "quest_interest", "rumor_pressure", "danger_warning", "social_tension"
            }
        ]
        if not quest_signals:
            warnings.append(f"{scenario_name}_expected_quest_eligible_world_signal_on_turn_1")
        # Check rumor_propagation_state if supported
        simulation_state = _extract_simulation_state(result)
        rumor_state = _safe_dict(simulation_state.get("rumor_propagation_state"))
        if scenario_name == "rumor_seed_from_conversation":
            if rumor_state and not _safe_list(rumor_state.get("rumor_seeds")):
                warnings.append("rumor_seed_from_conversation_no_rumor_seeds_after_quest_tick")

    if scenario_name == "rumor_signal_expires" and turn_index == 1:
        simulation_state = _extract_simulation_state(result)
        rumor_state = _safe_dict(simulation_state.get("rumor_propagation_state"))
        if rumor_state and not _safe_list(rumor_state.get("rumor_seeds")):
            warnings.append("rumor_signal_expires_no_seed_created_on_turn_1")

    if scenario_name == "rumor_signal_expires":
        ambient_tick = _extract_ambient_tick_result(result)
        signal_expiration = _safe_dict(ambient_tick.get("signal_expiration"))

        seed_expiration = _safe_dict(signal_expiration.get("seed_expiration"))
        expired_seen = (
            _safe_int(signal_expiration.get("expired_count"), 0) > 0
            or bool(_safe_list(signal_expiration.get("expired_signal_ids")))
            or bool(_safe_list(signal_expiration.get("expired_seed_ids")))
            or bool(_safe_list(seed_expiration.get("expired_seed_ids")))
        )

        if turn_index >= 4 and not expired_seen:
            warnings.append("rumor_signal_expires_expected_expired_signal")
    if scenario_name == "rumor_signal_expires":
        ambient_tick = _extract_ambient_tick_result(result)
        signal_expiration = _safe_dict(ambient_tick.get("signal_expiration"))

        seed_expiration = _safe_dict(signal_expiration.get("seed_expiration"))
        expired_seen = (
            _safe_int(signal_expiration.get("expired_count"), 0) > 0
            or bool(_safe_list(signal_expiration.get("expired_signal_ids")))
            or bool(_safe_list(signal_expiration.get("expired_seed_ids")))
            or bool(_safe_list(seed_expiration.get("expired_seed_ids")))
        )

        if turn_index >= 4 and not expired_seen:
            warnings.append("rumor_signal_expires_expected_expired_signal")

        rumor_state = _safe_dict(_extract_simulation_state(result).get("conversation_rumor_state"))
        seeds = _safe_list(rumor_state.get("rumor_seeds"))

        current_tick = _safe_int(
            signal_expiration.get("current_tick")
            or seed_expiration.get("current_tick")
            or _safe_dict(_extract_turn_contract(result).get("semantic_action")).get("tick"),
            0,
        )

        stale_seeds = [
            seed for seed in seeds
            if _safe_int(_safe_dict(seed).get("expires_tick"), 0)
            and current_tick >= _safe_int(_safe_dict(seed).get("expires_tick"), 0)
        ]

        if turn_index >= 4 and stale_seeds:
            warnings.append("rumor_signal_expires_stale_seed_still_present_on_turn_4")

    if scenario_name == "npc_goal_influences_response_style" and turn_index == 2:
        if conversation_reason != "pending_player_response_consumed":
            warnings.append("npc_goal_influences_response_style_expected_pending_response_consumed")
        response_style = _safe_str(
            _safe_dict(conversation.get("npc_response_beat")).get("response_style")
            or _safe_dict(conversation.get("beat")).get("response_style")
        )
        if not response_style:
            warnings.append("npc_goal_influences_response_style_missing_response_style")

    if scenario_name in {
        "npc_biography_shapes_bran_dialogue",
        "npc_biography_shapes_mira_dialogue",
        "npc_biography_blocks_unbacked_secret",
        "npc_roleplay_fallback_validation",
    }:
        conversation = _extract_conversation_result(result)
        response_beat = _safe_dict(conversation.get("npc_response_beat"))
        if turn_index == 2 and not response_beat:
            warnings.append(f"{scenario_name}_expected_npc_response_beat")
        if turn_index == 2:
            roleplay_source = _safe_str(
                response_beat.get("roleplay_source")
                or conversation.get("roleplay_source")
            )
            if not roleplay_source:
                warnings.append(f"{scenario_name}_missing_roleplay_source")
            biography_role = _safe_str(response_beat.get("biography_role"))
            if not biography_role:
                warnings.append(f"{scenario_name}_missing_biography_role")
            used_fact_ids = _safe_list(
                response_beat.get("used_fact_ids")
                or conversation.get("used_fact_ids")
            )
            if scenario_name == "npc_biography_shapes_bran_dialogue" and not used_fact_ids:
                warnings.append("npc_biography_shapes_bran_dialogue_missing_used_fact_ids")

            if scenario_name == "npc_biography_shapes_mira_dialogue":
                speaker_id = _safe_str(response_beat.get("speaker_id"))
                if speaker_id != "npc:Mira":
                    warnings.append(
                        f"npc_biography_shapes_mira_dialogue_expected_mira_got:{speaker_id or 'missing'}"
                    )
                if biography_role != "Curious local informant":
                    warnings.append(
                        "npc_biography_shapes_mira_dialogue_expected_informant_role"
                    )
                line = _safe_str(response_beat.get("line")).lower()
                if "pattern" not in line and "noticed" not in line and "thread" not in line:
                    warnings.append(
                        "npc_biography_shapes_mira_dialogue_expected_mira_style_reference"
                    )

    if scenario_name == "npc_biography_blocks_unbacked_secret" and turn_index == 2:
        conversation = _extract_conversation_result(result)
        response_beat = _safe_dict(conversation.get("npc_response_beat"))
        line = _safe_str(response_beat.get("line")).lower()
        forbidden_fragments = [
            "secret vault is",
            "under the city is",
            "you receive",
            "take this",
            "reward",
        ]
        for fragment in forbidden_fragments:
            if fragment in line:
                warnings.append("npc_biography_blocks_unbacked_secret_invented_forbidden_claim")

    if scenario_name == "scene_activity_schedules_idle_action" and turn_index == 1:
        conversation = _extract_conversation_result(result)
        if conversation.get("triggered"):
            warnings.append("scene_activity_schedules_idle_action_unexpected_conversation_trigger")
        activity_state = _extract_scene_activity_state(result)
        if not _safe_list(activity_state.get("recent")):
            warnings.append("scene_activity_schedules_idle_action_missing_recent_activity")

    if scenario_name == "scene_activity_respects_cooldown" and turn_index == 2:
        conversation = _extract_conversation_result(result)
        if conversation.get("triggered"):
            warnings.append("scene_activity_respects_cooldown_unexpected_conversation_trigger")
        activity_state = _extract_scene_activity_state(result)
        recent = _safe_list(activity_state.get("recent"))
        if len(recent) > 1:
            warnings.append("scene_activity_respects_cooldown_expected_single_activity")

    _multiturn_npc_npc_scenarios = {
        "npc_npc_multiturn_conversation",
        "npc_npc_multiturn_quest_discussion",
    }
    if scenario_name in _multiturn_npc_npc_scenarios:
        conv = _extract_conversation_result(result)
        if turn_index == 1 and not conv.get("triggered"):
            warnings.append(f"{scenario_name}_expected_conversation_trigger_on_turn_1")
        if service_result.get("matched"):
            warnings.append(f"{scenario_name}_unexpected_service_result")
        thread_state = _extract_conversation_thread_state(result)
        threads = _safe_list(thread_state.get("threads"))
        if turn_index >= 2 and not threads:
            warnings.append(f"{scenario_name}_expected_active_thread_on_turn_{turn_index}")
        # Threads must keep accumulating beats across turns
        if threads:
            max_beats = max(len(_safe_list(_safe_dict(t).get("beats"))) for t in threads)
            if turn_index >= 2 and max_beats < 2:
                warnings.append(
                    f"{scenario_name}_expected_at_least_2_beats_by_turn_{turn_index}_got_{max_beats}"
                )
    if scenario_name == "blocked_purchase" and turn_index == 3:
        if bool(purchase.get("applied") or service_application.get("applied")):
            warnings.append("blocked_purchase_unexpectedly_applied")
        if _safe_str(purchase.get("blocked_reason")) != "insufficient_funds":
            warnings.append("blocked_purchase_expected_insufficient_funds")

    current_location_id = _extract_current_location_id(result)

    provider_name = _safe_str(service_result.get("provider_name"))
    service_kind = _safe_str(service_result.get("service_kind"))
    if provider_name == "Elara" and service_kind in {"shop_goods", "repair"}:
        if current_location_id and current_location_id != "loc_market":
            warnings.append("elara_service_resolved_outside_market")
    if provider_name == "Bran" and service_kind in {"lodging", "meal", "paid_information"}:
        if current_location_id and current_location_id != "loc_tavern":
            warnings.append("bran_service_resolved_outside_tavern")

    conversation = _extract_conversation_result(result)
    if conversation.get("triggered"):
        thread = _safe_dict(conversation.get("thread"))
        participants = _safe_list(thread.get("participants"))
        participant_ids = {
            _safe_str(_safe_dict(participant).get("id"))
            for participant in participants
        }
        location_state = _extract_location_state(result)
        current_location = _safe_dict(location_state.get("current_location"))
        present_ids = {
            _safe_str(_safe_dict(npc).get("id"))
            for npc in _safe_list(current_location.get("present_npcs"))
        }
        if len(participants) < 2:
            warnings.append("conversation_triggered_with_less_than_two_participants")
        if present_ids and not participant_ids.issubset(present_ids):
            warnings.append("conversation_participant_not_present")
        # Guard against freeform mutation by conversation runtime.
        if _safe_dict(conversation.get("journal_entry")):
            warnings.append("conversation_created_journal_entry")
        if _safe_dict(conversation.get("transaction_record")):
            warnings.append("conversation_created_transaction_record")
        if _safe_dict(conversation.get("inventory_delta")):
            warnings.append("conversation_created_inventory_delta")

    if scenario_name in {"shop_success", "blocked_purchase"} and turn_index == 1:
        if not bool(travel_result.get("applied")):
            warnings.append(f"{scenario_name}_turn_1_expected_travel_applied")
        if current_location_id != "loc_market":
            warnings.append(f"{scenario_name}_turn_1_expected_loc_market")

    if scenario_name in {"shop_success", "blocked_purchase"} and turn_index in {2, 3}:
        if current_location_id != "loc_market":
            warnings.append(f"{scenario_name}_turn_{turn_index}_expected_loc_market")

    if scenario_name in {"lodging_success", "paid_info"}:
        if current_location_id not in {"loc_tavern", ""}:
            warnings.append(f"{scenario_name}_expected_loc_tavern")

    # Flat transcript expected location progression:
    # turn 4 asks directions but should remain in tavern;
    # turn 5 follows directions and should arrive at market.
    if not scenario_name and turn_index == 4:
        if bool(travel_result.get("applied")):
            warnings.append("flat_turn_4_directions_inquiry_should_not_travel")
        if _extract_current_location_id(result) not in {"loc_tavern", ""}:
            warnings.append("flat_turn_4_expected_tavern")

    if not scenario_name and turn_index == 5:
        if not bool(travel_result.get("applied")):
            warnings.append("flat_turn_5_follow_directions_should_travel")
        if _extract_current_location_id(result) != "loc_market":
            warnings.append("flat_turn_5_expected_market")

    return warnings


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    session = _sanitize_manual_session_for_test(
        session,
        currency=currency,
        reset_player_items=True,
    )

    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception:
        return False

    return True


def _apply_manual_scenario_setup(session_id: str, scenario: Dict[str, Any]) -> bool:
    try:
        from app.rpg.session.service import load_session, save_session
    except Exception:
        return False
    session = _safe_dict(load_session(session_id))
    if not session:
        return False

    simulation_state = _ensure_manual_simulation_roots(session)
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_settings = _safe_dict(runtime_state.get("runtime_settings"))

    conversation_settings = _safe_dict(scenario.get("conversation_settings"))
    if conversation_settings:
        current = _safe_dict(runtime_settings.get("conversation_settings"))
        current.update(conversation_settings)
        runtime_settings["conversation_settings"] = current

    setup_world_events = _safe_list(scenario.get("setup_world_events"))
    if setup_world_events:
        world_event_state = _safe_dict(simulation_state.get("world_event_state"))
        events = _safe_list(world_event_state.get("events"))
        for index, event in enumerate(setup_world_events, start=1):
            event = _safe_dict(event)
            event.setdefault("event_id", f"manual:world_event:{session_id}:{index}")
            event.setdefault("tick", index)
            events.append(event)
        world_event_state["events"] = events
        simulation_state["world_event_state"] = world_event_state

    setup_journal_entries = _safe_list(scenario.get("setup_journal_entries"))
    if setup_journal_entries:
        journal_state = _safe_dict(simulation_state.get("journal_state"))
        entries = _safe_list(journal_state.get("entries"))
        for index, entry in enumerate(setup_journal_entries, start=1):
            entry = _safe_dict(entry)
            entry.setdefault("entry_id", f"manual:journal:{session_id}:{index}")
            entries.append(entry)
        journal_state["entries"] = entries
        simulation_state["journal_state"] = journal_state

    setup_quest_state = _safe_dict(scenario.get("setup_quest_state"))
    if setup_quest_state:
        simulation_state["quest_state"] = setup_quest_state

    setup_memory_state = _safe_dict(scenario.get("setup_memory_state"))
    if setup_memory_state:
        memory_state = _safe_dict(simulation_state.get("memory_state"))
        memory_state.update(setup_memory_state)
        simulation_state["memory_state"] = memory_state

    setup_conversation_thread_state = _safe_dict(scenario.get("setup_conversation_thread_state"))
    if setup_conversation_thread_state:
        conversation_thread_state = _safe_dict(simulation_state.get("conversation_thread_state"))
        for key, value in setup_conversation_thread_state.items():
            conversation_thread_state[key] = value
        simulation_state["conversation_thread_state"] = conversation_thread_state

    runtime_state["runtime_settings"] = runtime_settings
    session["runtime_state"] = runtime_state
    _sync_manual_simulation_state(session, simulation_state)
    try:
        save_session(session)
        return True
    except Exception:
        return False


def _write_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    try:
        from app.rpg.session.service import load_session, save_session
    except Exception:
        return False

    session = _safe_dict(load_session(session_id))
    if not session:
        return False

    simulation_state = _ensure_manual_simulation_roots(session)

    # Preserve current location fields exactly as loaded. This helper is only
    # allowed to adjust currency; it must not bounce a scenario back to the
    # template/default tavern state after a travel turn.
    loaded_location_id = (
        _safe_str(simulation_state.get("location_id"))
        or _safe_str(simulation_state.get("current_location_id"))
        or _safe_str(_safe_dict(simulation_state.get("player_state")).get("location_id"))
        or _safe_str(_safe_dict(simulation_state.get("player_state")).get("current_location_id"))
    )
    loaded_location_state = _safe_dict(simulation_state.get("location_state"))
    loaded_present_npcs = _safe_list(simulation_state.get("present_npcs"))

    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {
            "items": [],
            "equipment": {},
            "capacity": 50,
            "last_loot": [],
        }
        player_state["inventory_state"] = inventory_state

    inventory_state["currency"] = {
        "gold": int(currency.get("gold") or 0),
        "silver": int(currency.get("silver") or 0),
        "copper": int(currency.get("copper") or 0),
    }

    if loaded_location_id:
        simulation_state["location_id"] = loaded_location_id
        simulation_state["current_location_id"] = loaded_location_id
        player_state["location_id"] = loaded_location_id
        player_state["current_location_id"] = loaded_location_id
    if loaded_location_state:
        simulation_state["location_state"] = loaded_location_state
    if loaded_present_npcs:
        simulation_state["present_npcs"] = loaded_present_npcs

    _sync_manual_simulation_state(session, simulation_state)

    try:
        save_session(session)
        return True
    except Exception:
        return False


def _extract_narration(result: Dict[str, Any]) -> str:
    # Check direct keys
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in result subdict
    result_sub = _safe_dict(result.get("result"))
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in session runtime_state
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    for key in ("last_narration", "last_turn_narration"):
        value = runtime_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check authoritative
    authoritative = _safe_dict(result.get("authoritative"))
    for key in ("summary", "deterministic_fallback_narration"):
        value = authoritative.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _one_line_text(value: Any, *, max_chars: int = 1200) -> str:
    text = "" if value is None else str(value)
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def _extract_raw_llm_text(result: Dict[str, Any]) -> str:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    raw_text = (
        raw_payload.get("raw_llm_narrative")
        or raw_payload.get("raw_llm_text")
        or result_sub.get("raw_llm_narrative")
        or result_sub.get("raw_llm_text")
    )
    if isinstance(raw_text, dict):
        return _compact_json(raw_text)
    return _safe_str(raw_text)


def _extract_raw_llm_request(result: Dict[str, Any]) -> str:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    raw_request = (
        raw_payload.get("raw_llm_request")
        or result_sub.get("raw_llm_request")
    )
    if isinstance(raw_request, dict):
        return _compact_json(raw_request)
    return _safe_str(raw_request)


def _extract_llm_console_response(result: Dict[str, Any]) -> Dict[str, Any]:
    result_sub = _safe_dict(_safe_dict(result).get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    narration_json = _safe_dict(raw_payload.get("narration_json"))
    npc = _safe_dict(narration_json.get("npc"))

    final_narration = _extract_narration(result)
    json_narration = _safe_str(narration_json.get("narration"))
    json_action = _safe_str(narration_json.get("action"))
    npc_speaker = _safe_str(npc.get("speaker"))
    npc_line = _safe_str(npc.get("line"))
    raw_text = _extract_raw_llm_text(result)
    raw_request = _extract_raw_llm_request(result)

    return {
        "final": final_narration,
        "json_narration": json_narration,
        "json_action": json_action,
        "npc_speaker": npc_speaker,
        "npc_line": npc_line,
        "raw": raw_text,
        "raw_request": raw_request,
        "used_llm": result_sub.get("used_llm"),
        "narration_status": result_sub.get("narration_status"),
    }


def _log_llm_response(
    *,
    scope: str,
    label: str,
    turn: int,
    player_input: str,
    result: Dict[str, Any],
    show_raw: bool = False,
    max_chars: int = 1200,
) -> None:
    payload = _extract_llm_console_response(result)
    final_text = _one_line_text(payload.get("final"), max_chars=max_chars)
    json_narration = _one_line_text(payload.get("json_narration"), max_chars=max_chars)
    json_action = _one_line_text(payload.get("json_action"), max_chars=max_chars)
    npc_speaker = _safe_str(payload.get("npc_speaker"))
    npc_line = _one_line_text(payload.get("npc_line"), max_chars=max_chars)
    raw_text = _one_line_text(payload.get("raw"), max_chars=max_chars)
    raw_request = _one_line_text(payload.get("raw_request"), max_chars=max_chars)

    prefix = f"[manual][llm][{scope}:{label}][turn {turn}]"
    print("", flush=True)
    print(f"{prefix} PLAYER: {player_input}", flush=True)
    print(
        f"{prefix} used_llm={payload.get('used_llm')} "
        f"narration_status={payload.get('narration_status')}",
        flush=True,
    )
    if show_raw and raw_request:
        print(f"{prefix} RAW LLM REQUEST:", flush=True)
        print(raw_request, flush=True)
    if final_text:
        print(f"{prefix} FINAL RESPONSE:", flush=True)
        print(final_text, flush=True)
    elif json_narration or json_action or npc_line:
        print(f"{prefix} STRUCTURED RESPONSE:", flush=True)
        if json_narration:
            print(json_narration, flush=True)
        if json_action:
            print(f"Result: {json_action}", flush=True)
        if npc_speaker and npc_line:
            print(f'{npc_speaker}: "{npc_line}"', flush=True)
    else:
        print(f"{prefix} FINAL RESPONSE: [no narration found]", flush=True)

    if show_raw and raw_text:
        print(f"{prefix} RAW LLM RESPONSE:", flush=True)
        print(raw_text, flush=True)
    print("", flush=True)
    print(f"{prefix} PLAYER: {player_input}", flush=True)
    print(
        f"{prefix} used_llm={payload.get('used_llm')} "
        f"narration_status={payload.get('narration_status')}",
        flush=True,
    )

    if final_text:
        print(f"{prefix} FINAL RESPONSE:", flush=True)
        print(final_text, flush=True)
    elif json_narration or json_action or npc_line:
        print(f"{prefix} STRUCTURED RESPONSE:", flush=True)
        if json_narration:
            print(json_narration, flush=True)
        if json_action:
            print(f"Result: {json_action}", flush=True)
        if npc_speaker and npc_line:
            print(f'{npc_speaker}: "{npc_line}"', flush=True)
    else:
        print(f"{prefix} FINAL RESPONSE: [no narration found]", flush=True)

    if show_raw and raw_text:
        print(f"{prefix} RAW LLM RESPONSE:", flush=True)
        print(raw_text, flush=True)
    print("", flush=True)


def _extract_turn_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    payload = _safe_dict(result.get("result") or result)
    contract = _safe_dict(payload.get("turn_contract"))
    if contract:
        return contract

    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    return _safe_dict(runtime_state.get("last_turn_contract"))


def _extract_service_debug(result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _extract_turn_contract(result)
    contract_service_result = _safe_dict(contract.get("service_result"))
    resolved = _safe_dict(contract.get("resolved_result") or contract.get("resolved_action"))
    resolved_service_result = _safe_dict(resolved.get("service_result"))
    presentation = _safe_dict(contract.get("presentation"))

    service = resolved_service_result or contract_service_result
    purchase = _safe_dict(service.get("purchase"))
    resource_changes = _safe_dict(purchase.get("resource_changes"))
    applied_effects = _safe_dict(purchase.get("applied_effects"))
    effects = _safe_dict(purchase.get("effects"))
    service_application = _safe_dict(resolved.get("service_application"))

    return {
        "resolved_result": resolved,
        "service_result": service,
        "available_actions": _safe_list(
            presentation.get("available_actions") or service.get("available_actions")
        ),
        "resource_changes": resource_changes,
        "purchase": purchase,
        "service_application": service_application,
        "transaction_record": _safe_dict(
            resolved.get("transaction_record")
            or service_application.get("transaction_record")
        ),
        "memory_entry": _safe_dict(
            resolved.get("memory_entry")
            or service_application.get("memory_entry")
        ),
        "social_effects": _safe_dict(
            resolved.get("social_effects")
            or service_application.get("social_effects")
        ),
        "stock_update": _safe_dict(
            resolved.get("stock_update")
            or service_application.get("stock_update")
        ),
        "rumor_added": _safe_dict(
            resolved.get("rumor_added")
            or service_application.get("rumor_added")
        ),
        "journal_entry": _safe_dict(
            resolved.get("journal_entry")
            or service_application.get("journal_entry")
        ),
        "service_world_event": _safe_dict(
            resolved.get("service_world_event")
            or service_application.get("service_world_event")
        ),
        "rumor_world_event": _safe_dict(
            resolved.get("rumor_world_event")
            or service_application.get("rumor_world_event")
        ),
        "inventory_changes": {
            "items_added": _safe_list(
                applied_effects.get("items_added") or effects.get("items_added")
            ),
            "items_removed": _safe_list(
                applied_effects.get("items_removed") or effects.get("items_removed")
            ),
        },
    }


def _effective_player_currency_after(result: Dict[str, Any]) -> Dict[str, Any]:
    service_debug = _extract_service_debug(result)
    service_application = _safe_dict(service_debug.get("service_application"))
    if service_application.get("currency_after"):
        return _safe_dict(service_application.get("currency_after"))

    service_result = _safe_dict(service_debug.get("service_result"))
    if service_result.get("player_currency"):
        return _safe_dict(service_result.get("player_currency"))

    return _extract_player_currency(result)


def _turn_applied_currency_mutation(result: Dict[str, Any]) -> bool:
    """True only when the turn actually mutates player currency.

    Service inquiry turns can expose stale/default player_currency values.
    The scenario harness must not treat those as authoritative currency
    changes, or seeded scenario currency gets wiped before the purchase turn.
    """
    service_debug = _extract_service_debug(result)
    service_result = _safe_dict(service_debug.get("service_result"))
    service_application = _safe_dict(service_debug.get("service_application"))
    purchase = _safe_dict(service_debug.get("purchase"))
    transaction_record = _safe_dict(service_debug.get("transaction_record"))

    if _safe_str(service_result.get("kind")) != "service_purchase":
        return False

    return bool(
        service_application.get("applied")
        or purchase.get("applied")
        or _safe_str(transaction_record.get("status")) == "purchased"
    )


def _print_turn(
    index: int,
    player_input: str,
    result: Dict[str, Any],
    before_currency: Dict[str, Any] | None = None,
    before_items: List[Any] | None = None,
    channel: str = "main",
) -> None:
    result_sub = _safe_dict(result.get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    narration_json = _safe_dict(raw_payload.get("narration_json"))
    raw_llm_text = raw_payload.get("raw_llm_narrative")
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    narration = _extract_narration(result)
    turn_contract = _extract_turn_contract(result)
    service_debug = _extract_service_debug(result)

    _emit("=" * 80, channel=channel)
    _emit(f"TURN {index}", channel=channel)
    _emit(f"PLAYER: {player_input}", channel=channel)
    _emit("", channel=channel)

    if result.get("error"):
        _emit("ERROR:", channel=channel)
        _emit(result["error"], channel=channel)
        _emit("", channel=channel)
        _emit("TRACEBACK:", channel=channel)
        _emit(result.get("traceback", "")[:2000], channel=channel)
        _emit("", channel=channel)

    _emit("NARRATION:", channel=channel)
    _emit(narration or "[no narration found]", channel=channel)
    _emit("", channel=channel)
    _emit("TURN CONTRACT:", channel=channel)
    _emit(_compact_json(turn_contract), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE RESULT:", channel=channel)
    _emit(_compact_json(service_debug.get("service_result")), channel=channel)
    _emit("", channel=channel)
    _emit("AVAILABLE ACTIONS:", channel=channel)
    _emit(_compact_json(service_debug.get("available_actions")), channel=channel)
    _emit("", channel=channel)
    _emit("RESOURCE CHANGES:", channel=channel)
    _emit(_compact_json(service_debug.get("resource_changes")), channel=channel)
    _emit("", channel=channel)
    _emit("INVENTORY CHANGES:", channel=channel)
    _emit(_compact_json(service_debug.get("inventory_changes")), channel=channel)
    _emit("", channel=channel)
    _emit("PLAYER CURRENCY BEFORE:", channel=channel)
    _emit(_compact_json(before_currency or {}), channel=channel)
    _emit("", channel=channel)
    _emit("PLAYER CURRENCY AFTER:", channel=channel)
    _emit(_compact_json(_effective_player_currency_after(result)), channel=channel)
    _emit("", channel=channel)
    _emit("PLAYER ITEMS BEFORE:", channel=channel)
    _emit(_compact_json(before_items or []), channel=channel)
    _emit("", channel=channel)
    _emit("PLAYER ITEMS AFTER:", channel=channel)
    _emit(_compact_json(_extract_player_items(result)), channel=channel)
    _emit("", channel=channel)
    _emit("ACTIVE SERVICES:", channel=channel)
    _emit(_compact_json(_extract_active_services(result)), channel=channel)
    _emit("", channel=channel)
    _emit("MEMORY RUMORS:", channel=channel)
    _emit(_compact_json(_extract_memory_rumors(result)), channel=channel)
    _emit("", channel=channel)
    _emit("TRANSACTION RECORD:", channel=channel)
    _emit(_compact_json(service_debug.get("transaction_record")), channel=channel)
    _emit("", channel=channel)
    _emit("TRANSACTION HISTORY:", channel=channel)
    _emit(_compact_json(_extract_transaction_history(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE MEMORIES:", channel=channel)
    _emit(_compact_json(_extract_service_memories(result)), channel=channel)
    _emit("", channel=channel)
    _emit("RECALLED SERVICE MEMORIES:", channel=channel)
    _emit(_compact_json(_extract_recalled_service_memories(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE MEMORY RECALL DEBUG:", channel=channel)
    _emit(_compact_json(_extract_service_memory_recall_debug(result)), channel=channel)
    _emit("", channel=channel)
    _emit("RECALLED NPC MEMORIES:", channel=channel)
    _emit(_compact_json(_extract_recalled_npc_memories(result)), channel=channel)
    _emit("", channel=channel)
    _emit("NPC MEMORY RECALL DEBUG:", channel=channel)
    _emit(_compact_json(_extract_npc_memory_recall_debug(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SOCIAL LIVING WORLD EFFECTS:", channel=channel)
    _emit(_compact_json(_extract_social_living_world_effects(result)), channel=channel)
    _emit("", channel=channel)
    _emit("RELATIONSHIP STATE:", channel=channel)
    _emit(_compact_json(_extract_relationship_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("NPC EMOTION STATE:", channel=channel)
    _emit(_compact_json(_extract_npc_emotion_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE OFFER STATE:", channel=channel)
    _emit(_compact_json(_extract_service_offer_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("JOURNAL STATE:", channel=channel)
    _emit(_compact_json(_extract_journal_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("WORLD EVENT STATE:", channel=channel)
    _emit(_compact_json(_extract_world_event_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("LOCATION STATE:", channel=channel)
    _emit(_compact_json(_extract_location_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("TRAVEL RESULT:", channel=channel)
    _emit(_compact_json(_extract_travel_result(result)), channel=channel)
    _emit("", channel=channel)
    _emit("CONVERSATION RESULT:", channel=channel)
    _emit(_compact_json(_extract_conversation_result(result)), channel=channel)
    _emit("", channel=channel)
    _emit("AMBIENT TICK RESULT:", channel=channel)
    _emit(_compact_json(_extract_ambient_tick_result(result)), channel=channel)
    _emit("", channel=channel)
    _emit("CONVERSATION THREAD STATE:", channel=channel)
    _emit(_compact_json(_extract_conversation_thread_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE LIVING WORLD APPLICATION:", channel=channel)
    _emit(_compact_json({
        "memory_entry": service_debug.get("memory_entry"),
        "social_effects": service_debug.get("social_effects"),
        "stock_update": service_debug.get("stock_update"),
        "living_world_debug": _extract_living_world_debug(result),
    }), channel=channel)
    _emit("", channel=channel)
    _emit("RESULT SUBDICT:", channel=channel)
    _emit(_compact_json(result_sub), channel=channel)
    _emit("", channel=channel)
    _emit("NARRATION DEBUG:", channel=channel)
    _emit(_compact_json({
        "final_narration": result_sub.get("narration"),
        "used_llm": result_sub.get("used_llm"),
        "narration_status": result_sub.get("narration_status"),
        "raw_llm_text": raw_llm_text,
        "raw_payload_narration": raw_payload.get("narration"),
        "narration_json": narration_json,
        "json_narration": narration_json.get("narration"),
        "json_action": narration_json.get("action"),
        "json_npc": narration_json.get("npc"),
        "turn_contract_action": _safe_dict(turn_contract.get("action")),
        "turn_contract_resolved": _safe_dict(turn_contract.get("resolved_result")),
    }), channel=channel)
    _emit("", channel=channel)
    _emit("RUNTIME STATE KEYS:", channel=channel)
    _emit(", ".join(sorted(runtime_state.keys())), channel=channel)
    _emit("", channel=channel)
    _emit("RAW RESULT:", channel=channel)
    _emit(_compact_json(result), channel=channel)
    _emit("", channel=channel)


def run_manual_transcript(
    turns: List[str],
    session_id: str = "manual_test_session",
    *,
    split_files: bool = True,
    run_id: str = "",
    stable_session_ids: bool = False,
    reset_session_state: bool = True,
    reset_output: bool = True,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
) -> List[str]:
    if reset_output:
        _reset_output()

    effective_session_id = _scoped_session_id(
        session_id,
        run_id or _new_manual_run_id(),
        stable=stable_session_ids,
    )
    if reset_session_state:
        _reset_manual_session_artifacts(effective_session_id)

    if not _bootstrap_flat_manual_session(effective_session_id):
        summary_channel = "flat_summary"
        legacy_channel = "flat_legacy"
        _emit("Manual RPG LLM Transcript Summary", channel=summary_channel)
        _emit("", channel=summary_channel)
        _emit(f"session_id: {effective_session_id}", channel=summary_channel)
        _emit(f"base_session_id: {session_id}", channel=summary_channel)
        _emit(f"manual_run_id: {run_id}", channel=summary_channel)
        _emit("", channel=summary_channel)
        _emit("ERROR:", channel=summary_channel)
        _emit(f"Could not create or load flat manual session: {effective_session_id}", channel=summary_channel)
        _emit("", channel=summary_channel)

        if not split_files:
            _emit("Manual RPG LLM Transcript", channel=legacy_channel)
            _emit("", channel=legacy_channel)
            _emit(f"session_id: {effective_session_id}", channel=legacy_channel)
            _emit("ERROR:", channel=legacy_channel)
            _emit(f"Could not create or load flat manual session: {effective_session_id}", channel=legacy_channel)
        return

    summary_channel = "flat_summary"
    legacy_channel = "flat_legacy"
    output_map: Dict[str, Path] = {}
    summary_rows: List[Dict[str, Any]] = []
    html_turns: List[str] = []

    _emit("Manual RPG LLM Transcript Summary", channel=summary_channel)
    _emit("", channel=summary_channel)
    _emit(f"session_id: {effective_session_id}", channel=summary_channel)
    _emit(f"base_session_id: {session_id}", channel=summary_channel)
    _emit(f"manual_run_id: {run_id}", channel=summary_channel)
    _emit("", channel=summary_channel)

    if not split_files:
        _emit("Manual RPG LLM Transcript", channel=legacy_channel)
        _emit("", channel=legacy_channel)
        _emit(f"session_id: {effective_session_id}", channel=legacy_channel)

    last_result: Dict[str, Any] = {}

    for index, player_input in enumerate(turns, start=1):
        print(f"[manual] flat turn {index}/{len(turns)}: {player_input}", flush=True)

        before_currency = _extract_player_currency(last_result) if last_result else {}
        before_items = _extract_player_items(last_result) if last_result else []
        result = apply_turn(session_id=effective_session_id, player_input=player_input)
        last_result = result

        # Collect conversation HTML for later writing
        narration = _extract_narration(result)
        turn_html = f"""    <div class="turn">
        <p class="player">PLAYER: {player_input}</p>
        <p class="ai">AI: {narration}</p>
    </div>
"""
        html_turns.append(turn_html)
        if console_llm:
            _log_llm_response(
                scope="flat",
                label=session_id,
                turn=index,
                player_input=player_input,
                result=result,
                show_raw=console_llm_raw,
                max_chars=console_llm_max_chars,
            )
        _record_token_usage(
            scope="flat",
            label=session_id,
            turn=index,
            player_input=player_input,
            result=result,
        )

        summary_row = _compact_turn_summary(
            index=index,
            player_input=player_input,
            result=result,
            before_currency=before_currency,
            before_items=before_items,
        )
        _record_regression_warnings(summary_row)
        summary_rows.append(summary_row)

        if split_files:
            turn_channel = f"flat_turn_{index:02d}"
            _emit("Manual RPG LLM Transcript", channel=turn_channel)
            _emit("", channel=turn_channel)
            _emit(f"session_id: {effective_session_id}", channel=turn_channel)
            _emit(f"base_session_id: {session_id}", channel=turn_channel)
            _emit(f"manual_run_id: {run_id}", channel=turn_channel)
            _print_turn(
                index,
                player_input,
                result,
                before_currency,
                before_items,
                channel=turn_channel,
            )
            output_map[turn_channel] = OUTPUT_DIR / f"manual_rpg_llm_transcript__turn_{index:02d}.txt"
        else:
            _print_turn(
                index,
                player_input,
                result,
                before_currency,
                before_items,
                channel=legacy_channel,
            )

    _emit_summary_block("Flat Manual Transcript Summary", summary_rows, summary_channel)

    if split_files:
        output_map[summary_channel] = OUTPUT_DIR / "manual_rpg_llm_transcript__summary.txt"
        _write_all_outputs(output_map)
    else:
        _write_output(OUTPUT_PATH, channel=legacy_channel)

    return html_turns


def _run_one_service_scenario(
    *,
    scenario_name: str,
    scenario: Dict[str, Any],
    run_id: str,
    split_files: bool,
    legacy_channel: str,
    stable_session_ids: bool,
    reset_session_state: bool,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
    fail_on_regression_warnings: bool = False,
) -> Dict[str, Any]:
    scenario_channel = f"service_{scenario_name}"
    target_channel = scenario_channel if split_files else legacy_channel
    session_id = _manual_service_session_id(
        scenario_name,
        run_id or _new_manual_run_id(),
        stable=stable_session_ids,
    )
    currency = _safe_dict(scenario.get("currency"))
    turns = _safe_list(scenario.get("turns"))

    print(
        f"[manual][worker {_thread_label()}] scenario {scenario_name}: "
        f"{len(turns)} turns session_id={session_id}",
        flush=True,
    )

    if reset_session_state:
        _reset_manual_session_artifacts(session_id)

    _emit("", channel=target_channel)
    _emit("#" * 80, channel=target_channel)
    _emit(f"SCENARIO: {scenario_name}", channel=target_channel)
    _emit(f"session_id: {session_id}", channel=target_channel)
    _emit(f"manual_run_id: {run_id}", channel=target_channel)
    _emit("SEEDED CURRENCY:", channel=target_channel)
    _emit(_compact_json(currency), channel=target_channel)
    _emit("#" * 80, channel=target_channel)

    seeded = _seed_session_currency(session_id, currency)
    setup_applied = _apply_manual_scenario_setup(session_id, scenario)
    if not seeded or not setup_applied:
        _record_scenario_error(
            scenario_name=scenario_name,
            session_id=session_id,
            error="scenario_session_seed_failed",
        )
        _emit("ERROR:", channel=target_channel)
        _emit(f"Could not create or seed scenario session: {session_id}", channel=target_channel)
        _emit(
            "Make sure manual_test_session exists, or update _ensure_manual_session to use your session creation API.",
            channel=target_channel,
        )
        return {
            "scenario": scenario_name,
            "session_id": session_id,
            "seeded_currency": currency,
            "error": "scenario_session_seed_failed",
            "turns": [],
            "_channel": scenario_channel,
        }

    last_result: Dict[str, Any] = {}
    scenario_results: List[Dict[str, Any]] = []
    html_turns: List[str] = []
    current_currency = currency
    current_location_id = ""

    for index, player_input in enumerate(turns, start=1):
        print(
            f"[manual][worker {_thread_label()}] scenario {scenario_name} "
            f"turn {index}/{len(turns)}: {player_input}",
            flush=True,
        )

        before_currency = current_currency or (
            _extract_player_currency(last_result) if last_result else currency
        )
        before_items = _extract_player_items(last_result) if last_result else []

        # Compute pre-turn contamination snapshot
        if index == 1:
            # For turn 1, get the seeded simulation state
            try:
                from app.rpg.session.service import load_session
                session = _safe_dict(load_session(session_id))
                simulation_state = _extract_simulation_state({"session": session})
            except Exception:
                simulation_state = {}
        else:
            # For later turns, use the previous result's simulation state
            simulation_state = _extract_simulation_state(last_result)
        pre_turn_snapshot = _pre_turn_contamination_snapshot(simulation_state)

        result = apply_turn(session_id=session_id, player_input=player_input)
        extracted_location_id = _extract_current_location_id(result)
        if extracted_location_id:
            current_location_id = extracted_location_id

        # Collect conversation HTML for later writing
        narration = _extract_narration(result)
        turn_html = f"""    <div class="turn">
        <p class="player">PLAYER: {player_input}</p>
        <p class="ai">AI: {narration}</p>
    </div>
"""
        html_turns.append(turn_html)

        if console_llm:
            _log_llm_response(
                scope="scenario",
                label=scenario_name,
                turn=index,
                player_input=player_input,
                result=result,
                show_raw=console_llm_raw,
                max_chars=console_llm_max_chars,
            )
        _record_token_usage(
            scope="service_scenario",
            label=scenario_name,
            turn=index,
            player_input=player_input,
            result=result,
        )
        _print_turn(
            index,
            player_input,
            result,
            before_currency,
            before_items,
            channel=target_channel,
        )

        summary_row = _compact_turn_summary(
            index=index,
            player_input=player_input,
            result=result,
            before_currency=before_currency,
            before_items=before_items,
        )
        summary_row["scenario_current_location_id"] = current_location_id

        summary_row["scenario_warnings"] = _scenario_contamination_warnings(
            scenario_name=scenario_name,
            turn_index=index,
            before_currency=before_currency,
            before_items=before_items,
            result=result,
            pre_turn_snapshot=pre_turn_snapshot,
            allows_seeded_world_events=bool(_safe_list(scenario.get("setup_world_events"))),
            allows_seeded_journal_entries=bool(_safe_list(scenario.get("setup_journal_entries"))),
            allows_seeded_quest_state=bool(_safe_dict(scenario.get("setup_quest_state"))),
        )
        summary_row["regression_warnings"] = _manual_regression_warnings(
            scenario_name=scenario_name,
            turn_index=index,
            player_input=player_input,
            result=result,
        )
        if fail_on_regression_warnings:
            for warning in summary_row["regression_warnings"]:
                _add_regression_warning(
                    scenario=scenario_name,
                    turn=index,
                    warning=warning,
                )
            for warning in summary_row["scenario_warnings"]:
                _add_regression_warning(
                    scenario=scenario_name,
                    turn=index,
                    warning=f"scenario_warning:{warning}",
                )
        _record_regression_warnings(summary_row)
        scenario_results.append(summary_row)

        if _turn_applied_currency_mutation(result):
            next_currency = _effective_player_currency_after(result)
            if next_currency:
                current_currency = next_currency
        last_result = result

    return {
        "scenario": scenario_name,
        "session_id": session_id,
        "seeded_currency": currency,
        "turns": scenario_results,
        "html_turns": html_turns,
        "_channel": scenario_channel,
    }


def _write_scenario_html(scenario_name: str, summary: Dict[str, Any]) -> None:
    html_turns = summary.get("html_turns", [])
    if not html_turns:
        return
    with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
        f.write(f"    <h3>Scenario: {scenario_name}</h3>\n")
        for turn_html in html_turns:
            f.write(turn_html)
        f.write("\n")


def run_service_scenarios(
    selected: str = "all",
    *,
    split_files: bool = True,
    run_id: str = "",
    stable_session_ids: bool = False,
    reset_session_state: bool = True,
    parallel_scenarios: bool = True,
    scenario_workers: int = 4,
    reset_output: bool = True,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
    fail_on_regression_warnings: bool = False,
) -> None:
    if reset_output:
        _reset_output()

    if selected == "all":
        scenario_items = list(SERVICE_SCENARIOS.items())
    else:
        scenario_items = [(selected, SERVICE_SCENARIOS[selected])]

    summary_channel = "service_summary"
    legacy_channel = "service_legacy"
    output_map: Dict[str, Path] = {}
    scenario_summaries: List[Dict[str, Any]] = []

    _emit("Manual RPG Service Scenario Summary", channel=summary_channel)
    _emit("", channel=summary_channel)
    _emit(f"scenario_filter: {selected}", channel=summary_channel)
    _emit(f"scenario_count: {len(scenario_items)}", channel=summary_channel)
    _emit(f"manual_run_id: {run_id}", channel=summary_channel)
    _emit("", channel=summary_channel)

    if not split_files:
        _emit("Manual RPG Service Scenario Transcript", channel=legacy_channel)
        _emit("", channel=legacy_channel)
        _emit(f"scenario_filter: {selected}", channel=legacy_channel)
        _emit(f"scenario_count: {len(scenario_items)}", channel=legacy_channel)
        _emit("", channel=legacy_channel)

    workers = _effective_scenario_workers(
        scenario_workers,
        len(scenario_items),
        parallel=parallel_scenarios,
    )
    _emit(f"requested_parallel_scenarios: {parallel_scenarios}", channel=summary_channel)
    _emit(f"requested_scenario_workers: {scenario_workers}", channel=summary_channel)
    _emit(f"scenario_workers_source: {_scenario_workers_source()}", channel=summary_channel)
    _emit(f"scenario_count: {len(scenario_items)}", channel=summary_channel)
    _emit(f"parallel_scenarios: {bool(workers > 1)}", channel=summary_channel)
    _emit(f"scenario_workers: {workers}", channel=summary_channel)
    if parallel_scenarios and workers <= 1:
        _emit(
            "parallel_note: parallel requested but effective workers is 1; "
            "this usually means only one scenario was selected or scenario-workers/env is 1.",
            channel=summary_channel,
        )
    _emit("", channel=summary_channel)

    def run_item(item: tuple[str, Dict[str, Any]]) -> Dict[str, Any]:
        scenario_name, scenario = item
        return _run_one_service_scenario(
            scenario_name=scenario_name,
            scenario=scenario,
            run_id=run_id,
            split_files=split_files,
            legacy_channel=legacy_channel,
            stable_session_ids=stable_session_ids,
            reset_session_state=reset_session_state,
            console_llm=console_llm,
            console_llm_raw=console_llm_raw,
            console_llm_max_chars=console_llm_max_chars,
            fail_on_regression_warnings=fail_on_regression_warnings,
        )

    if workers > 1:
        print(
            f"[manual][parallel] starting ThreadPoolExecutor max_workers={workers} "
            f"scenario_count={len(scenario_items)}",
            flush=True,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_name = {
                executor.submit(run_item, item): item[0]
                for item in scenario_items
            }
            completed: Dict[str, Dict[str, Any]] = {}
            for future in concurrent.futures.as_completed(future_to_name):
                scenario_name = future_to_name[future]
                try:
                    completed[scenario_name] = future.result()
                except Exception as exc:
                    _record_scenario_error(
                        scenario_name=scenario_name,
                        session_id="",
                        error=f"{type(exc).__name__}:{exc}",
                    )
                    error_channel = f"service_{scenario_name}"
                    _emit("", channel=error_channel)
                    _emit("#" * 80, channel=error_channel)
                    _emit(f"SCENARIO: {scenario_name}", channel=error_channel)
                    _emit("ERROR:", channel=error_channel)
                    _emit(f"{type(exc).__name__}: {exc}", channel=error_channel)
                    _emit("#" * 80, channel=error_channel)
                    completed[scenario_name] = {
                        "scenario": scenario_name,
                        "session_id": "",
                        "seeded_currency": {},
                        "error": f"{type(exc).__name__}: {exc}",
                        "turns": [],
                        "_channel": error_channel,
                    }

            for scenario_name, _scenario in scenario_items:
                summary = completed.get(scenario_name) or {}
                scenario_summaries.append({
                    key: value
                    for key, value in summary.items()
                    if key != "_channel"
                })
                if split_files:
                    output_map[f"service_{scenario_name}"] = (
                        OUTPUT_DIR / f"manual_rpg_service_scenarios__{scenario_name}.txt"
                    )
                # Write HTML for this scenario
                _write_scenario_html(scenario_name, summary)
    else:
        for item in scenario_items:
            scenario_name = item[0]
            try:
                summary = run_item(item)
            except Exception as exc:
                _record_scenario_error(
                    scenario_name=scenario_name,
                    session_id="",
                    error=f"{type(exc).__name__}:{exc}",
                )
                error_channel = f"service_{scenario_name}"
                _emit("", channel=error_channel)
                _emit("#" * 80, channel=error_channel)
                _emit(f"SCENARIO: {scenario_name}", channel=error_channel)
                _emit("ERROR:", channel=error_channel)
                _emit(f"{type(exc).__name__}: {exc}", channel=error_channel)
                _emit("#" * 80, channel=error_channel)
                summary = {
                    "scenario": scenario_name,
                    "session_id": "",
                    "seeded_currency": {},
                    "error": f"{type(exc).__name__}: {exc}",
                    "turns": [],
                    "_channel": error_channel,
                }
            scenario_summaries.append({
                key: value
                for key, value in summary.items()
                if key != "_channel"
            })
            if split_files:
                output_map[f"service_{scenario_name}"] = (
                    OUTPUT_DIR / f"manual_rpg_service_scenarios__{scenario_name}.txt"
                )
            # Write HTML for this scenario
            _write_scenario_html(scenario_name, summary)

    _emit_summary_block("Service Scenario Summary", scenario_summaries, summary_channel)

    if split_files:
        output_map[summary_channel] = OUTPUT_DIR / "manual_rpg_service_scenarios__summary.txt"
        _write_all_outputs(output_map)
    else:
        suffix = selected if selected != "all" else "all"
        _write_output(
            OUTPUT_DIR / f"manual_rpg_service_scenarios_{suffix}.txt",
            channel=legacy_channel,
        )


def run_requested_transcripts(args: argparse.Namespace) -> None:
    _reset_output()
    _reset_token_usage()
    _reset_regression_warnings()
    # Write HTML header
    html_header = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RPG Conversation</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .turn { margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: white; }
        .player { color: blue; font-weight: bold; }
        .ai { color: green; margin-top: 10px; }
        h1 { text-align: center; }
    </style>
</head>
<body>
    <h1>RPG Conversation Transcript</h1>
"""
    CONVERSATION_PATH.write_text(html_header)
    turns = args.turn or MANUAL_TEST_TURNS
    run_id = args.run_id or _new_manual_run_id()
    args._manual_run_id = run_id

    if args.all:
        # Run service scenarios first so parallel execution is visible early.
        # Flat transcript remains sequential because its turns depend on state.
        with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
            f.write("    <h2>Service Scenarios</h2>\n")
        run_service_scenarios(
            "all",
            split_files=not args.single_file,
            run_id=run_id,
            stable_session_ids=args.stable_session_ids,
            reset_session_state=not args.no_reset_session_state,
            parallel_scenarios=not args.no_parallel_scenarios,
            scenario_workers=args.scenario_workers,
            reset_output=False,
            console_llm=not args.no_console_llm,
            console_llm_raw=args.console_llm_raw,
            console_llm_max_chars=args.console_llm_max_chars,
            fail_on_regression_warnings=args.fail_on_regression_warnings,
        )
        with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
            f.write("    <h2>Flat Manual Transcript</h2>\n")

    flat_html_turns = run_manual_transcript(
        turns,
        session_id=args.session_id,
        split_files=not args.single_file,
        run_id=run_id,
        stable_session_ids=args.stable_session_ids,
        reset_session_state=not args.no_reset_session_state,
        reset_output=False,
        console_llm=not args.no_console_llm,
        console_llm_raw=args.console_llm_raw,
        console_llm_max_chars=args.console_llm_max_chars,
    )

    # Write flat transcript HTML turns
    with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
        for turn_html in flat_html_turns:
            f.write(turn_html)

    # Write HTML footer
    html_footer = "</body>\n</html>"
    with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
        f.write(html_footer)
    return

    if args.service_scenarios:
        with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
            f.write("    <h2>Service Scenarios</h2>\n")
        run_service_scenarios(
            args.scenario,
            split_files=not args.single_file,
            run_id=run_id,
            stable_session_ids=args.stable_session_ids,
            reset_session_state=not args.no_reset_session_state,
            parallel_scenarios=not args.no_parallel_scenarios,
            scenario_workers=args.scenario_workers,
            reset_output=False,
            console_llm=not args.no_console_llm,
            console_llm_raw=args.console_llm_raw,
            console_llm_max_chars=args.console_llm_max_chars,
            fail_on_regression_warnings=args.fail_on_regression_warnings,
        )
        # Write HTML footer
        html_footer = "</body>\n</html>"
        with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
            f.write(html_footer)
        return

    flat_html_turns = run_manual_transcript(
        turns,
        session_id=args.session_id,
        split_files=not args.single_file,
        run_id=run_id,
        stable_session_ids=args.stable_session_ids,
        reset_session_state=not args.no_reset_session_state,
        reset_output=False,
        console_llm=not args.no_console_llm,
        console_llm_raw=args.console_llm_raw,
        console_llm_max_chars=args.console_llm_max_chars,
    )

    # Write flat transcript HTML turns
    with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
        for turn_html in flat_html_turns:
            f.write(turn_html)

    # Write HTML footer
    html_footer = "</body>\n</html>"
    with open(CONVERSATION_PATH, "a", encoding="utf-8") as f:
        f.write(html_footer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default="manual_test_session")
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run id for generated manual session ids. Defaults to timestamp_uuid.",
    )
    parser.add_argument(
        "--stable-session-ids",
        action="store_true",
        help="Use legacy fixed manual session ids instead of run-scoped fresh ids.",
    )
    parser.add_argument(
        "--no-reset-session-state",
        action="store_true",
        help="Do not delete known saved session artifacts before using a manual session id.",
    )
    parser.add_argument(
        "--scenario-workers",
        type=int,
        default=_default_scenario_workers(),
        help=(
            "Maximum number of service scenarios to run in parallel. "
            "Only turns within each scenario remain sequential. "
            "Default: 4, or env OMNIX_MANUAL_SCENARIO_WORKERS if set."
        ),
    )
    parser.add_argument(
        "--no-parallel-scenarios",
        action="store_true",
        help="Run service scenarios sequentially.",
    )
    parser.add_argument(
        "--no-console-llm",
        action="store_true",
        help="Do not print concise readable LLM responses to console.",
    )
    parser.add_argument(
        "--console-llm-raw",
        action="store_true",
        help="Also print raw provider/LLM text in console response logs.",
    )
    parser.add_argument(
        "--console-llm-max-chars",
        type=int,
        default=1200,
        help="Maximum characters to print per console LLM response block.",
    )
    parser.add_argument(
        "--fail-on-regression-warnings",
        action="store_true",
        help="Exit non-zero if manual transcript summary contains regression_warnings or scenario_warnings.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run the flat manual transcript and all service scenarios.",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Write legacy giant transcript files instead of split summary/detail files.",
    )
    parser.add_argument(
        "--service-scenarios",
        action="store_true",
        help="Run deterministic service purchase scenarios.",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", *sorted(SERVICE_SCENARIOS.keys())],
        help="Run one named service scenario.",
    )
    parser.add_argument(
        "--turn",
        action="append",
        default=[],
        help="Override scripted turns. Can be passed multiple times.",
    )
    parser.add_argument(
        "--manage-servers",
        action="store_true",
        help=(
            "Start configured server subprocesses before the transcript run and "
            "stop them at the end. Commands come from --server-command or "
            "OMNIX_MANUAL_SERVER_COMMANDS."
        ),
    )
    parser.add_argument(
        "--server-command",
        action="append",
        default=[],
        help=(
            "Server command to start before running. Can be passed multiple times. "
            "Example: --server-command \"python -m uvicorn app.tts_server:app --host 127.0.0.1 --port 5101\""
        ),
    )
    parser.add_argument(
        "--server-health-url",
        action="append",
        default=[],
        help=(
            "Health URL to wait for after starting managed servers. "
            "Can be passed multiple times. Example: http://127.0.0.1:5101/health"
        ),
    )
    parser.add_argument(
        "--server-startup-timeout",
        type=float,
        default=90.0,
        help="Seconds to wait for each configured server health URL.",
    )
    parser.add_argument(
        "--no-code-diff",
        action="store_true",
        help="Do not write resources/test-results/code-diff.txt.",
    )
    parser.add_argument(
        "--no-results-zip",
        action="store_true",
        help="Do not write resources/test-results/manual-rpg-test-results.zip.",
    )
    parser.add_argument(
        "--no-token-usage",
        action="store_true",
        help="Do not write resources/test-results/token-usage.txt.",
    )
    parser.add_argument(
        "--code-diff-root",
        action="append",
        default=[],
        help="Path root to include in code-diff.txt. Defaults to src. Can be passed multiple times.",
    )

    args = parser.parse_args()

    server_commands = list(args.server_command or [])
    server_commands.extend(_split_env_list(os.environ.get("OMNIX_MANUAL_SERVER_COMMANDS", "")))

    health_urls = list(args.server_health_url or [])
    health_urls.extend(_split_env_list(os.environ.get("OMNIX_MANUAL_SERVER_HEALTH_URLS", "")))
    if not health_urls:
        health_urls = DEFAULT_MANAGED_SERVER_HEALTH_URLS

    code_diff_roots = args.code_diff_root or DEFAULT_CODE_DIFF_ROOTS

    servers = ManagedServerGroup(
        commands=server_commands,
        health_urls=health_urls,
        startup_timeout_seconds=args.server_startup_timeout,
        enabled=args.manage_servers,
    )

    exit_code = 0
    try:
        servers.start()
        run_requested_transcripts(args)
    except KeyboardInterrupt:
        exit_code = 130
        raise
    except Exception:
        exit_code = 1
        raise
    finally:
        try:
            _write_current_transcript_outputs()
            if not args.no_token_usage:
                write_token_usage_report()
            if not args.no_code_diff:
                write_code_diff_snapshot(roots=code_diff_roots)
            if not args.no_results_zip:
                write_results_zip()
            with _REGRESSION_WARNING_LOCK:
                warning_rows = list(_REGRESSION_WARNING_ROWS)
                regression_warnings = list(_REGRESSION_WARNINGS)
            if args.fail_on_regression_warnings and warning_rows:
                print("[manual][regression] warnings detected:", flush=True)
                print(_compact_json(warning_rows), flush=True)
                raise SystemExit(2)
            if args.fail_on_regression_warnings and regression_warnings:
                raise SystemExit(
                    "manual regression warnings found:\n"
                    + "\n".join(f"- {warning}" for warning in regression_warnings)
                )
        finally:
            servers.stop()

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
