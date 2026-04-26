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

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "test-results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "manual_rpg_llm_transcript.txt"
SERVICE_OUTPUT_PATH = OUTPUT_DIR / "manual_rpg_service_scenarios_all.txt"
CODE_DIFF_PATH = OUTPUT_DIR / "code-diff.txt"
RESULTS_ZIP_PATH = OUTPUT_DIR / "manual-rpg-test-results.zip"
TOKEN_USAGE_PATH = OUTPUT_DIR / "token-usage.txt"
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
_OUTPUT_LOCK = threading.RLock()
_TOKEN_USAGE_LOCK = threading.RLock()


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
    _REGRESSION_WARNING_ROWS.clear()


def _record_regression_warnings(row: Dict[str, Any]) -> None:
    warnings = _safe_list(row.get("regression_warnings")) + _safe_list(row.get("scenario_warnings"))
    if warnings:
        _REGRESSION_WARNING_ROWS.append(row)


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


def _run_git(args: Sequence[str]) -> str:
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
    roots: Sequence[str] = DEFAULT_CODE_DIFF_ROOTS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tracked_diff = _run_git([
        "--no-pager",
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--",
        *roots,
    ])
    untracked_paths = _git_untracked_files(roots)
    untracked_diff = "\n".join(_untracked_file_diff(p) for p in untracked_paths)

    header = [
        "Manual RPG transcript code diff snapshot",
        f"repo_root: {REPO_ROOT}",
        f"roots: {', '.join(roots)}",
        f"generated_at_unix: {time.time():.3f}",
        "",
        "Tracked diff:",
        "=" * 80,
        "",
    ]

    body = tracked_diff.strip()
    if not body:
        body = "[no tracked changes]"

    footer = [
        "",
        "",
        "Untracked new files:",
        "=" * 80,
        "",
    ]
    if untracked_diff.strip():
        footer.append(untracked_diff.rstrip())
    else:
        footer.append("[no untracked source files]")

    path.write_text("\n".join(header) + body + "\n".join(footer) + "\n", encoding="utf-8")
    print(f"Wrote code diff to: {path.resolve()}", flush=True)


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


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


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
        "conversation_thread_state": _extract_conversation_thread_state(result),
        "conversation_thread_count": len(_safe_list(_extract_conversation_thread_state(result).get("threads"))),
        "conversation_world_signal_count": len(_safe_list(_extract_conversation_thread_state(result).get("world_signals"))),
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
        if _safe_list(journal_state.get("entries")):
            warnings.append("scenario_started_with_journal_entries")
        # Turn 1 may legitimately emit its own current world event, such as a
        # service inquiry event. That is not pre-existing contamination. More
        # than one event on turn 1 is still suspicious for the manual scenarios.
        # Exception: ambient_conversation may emit 2 turn-1 events: one
        # service_inquiry (because "wait and listen" can match a lodging
        # presentation) AND one npc_conversation (from the conversation thread
        # system). Both are generated by turn 1 itself, not contamination.
        events = _safe_list(world_event_state.get("events"))
        event_limit = 2 if scenario_name == "ambient_conversation" else 1
        if len(events) > event_limit:
            warnings.append("scenario_started_with_world_events")

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
    player_lower = _safe_str(player_input).lower()

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
        if _safe_dict(service_debug.get("memory_entry")):
            warnings.append("ambient_conversation_unexpected_service_memory")
        world_events = _safe_list(_extract_world_event_state(result).get("events"))
        if any(_safe_str(_safe_dict(event).get("kind")).startswith("service_") for event in world_events):
            warnings.append("ambient_conversation_unexpected_service_world_event")
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
) -> None:
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
    if not seeded:
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

        result = apply_turn(session_id=session_id, player_input=player_input)
        extracted_location_id = _extract_current_location_id(result)
        if extracted_location_id:
            current_location_id = extracted_location_id

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
        )
        summary_row["regression_warnings"] = _manual_regression_warnings(
            scenario_name=scenario_name,
            turn_index=index,
            player_input=player_input,
            result=result,
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
        "_channel": scenario_channel,
    }


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
    else:
        for item in scenario_items:
            summary = run_item(item)
            scenario_name = item[0]
            scenario_summaries.append({
                key: value
                for key, value in summary.items()
                if key != "_channel"
            })
            if split_files:
                output_map[f"service_{scenario_name}"] = (
                    OUTPUT_DIR / f"manual_rpg_service_scenarios__{scenario_name}.txt"
                )

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
    turns = args.turn or MANUAL_TEST_TURNS
    run_id = args.run_id or _new_manual_run_id()
    args._manual_run_id = run_id

    if args.all:
        # Run service scenarios first so parallel execution is visible early.
        # Flat transcript remains sequential because its turns depend on state.
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
        )
        run_manual_transcript(
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
        return

    if args.service_scenarios:
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
        )
        return

    run_manual_transcript(
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
            if args.fail_on_regression_warnings and _REGRESSION_WARNING_ROWS:
                print("[manual][regression] warnings detected:", flush=True)
                print(_compact_json(_REGRESSION_WARNING_ROWS), flush=True)
                raise SystemExit(2)
        finally:
            servers.stop()

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
