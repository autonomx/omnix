from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from copy import deepcopy
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
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"


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


def _emit(value: Any = "", channel: str = "main") -> None:
    text = "" if value is None else str(value)
    print(text, flush=True)
    _OUTPUTS.setdefault(channel, []).append(text)


def _reset_output(channel: str | None = None) -> None:
    if channel is None:
        _OUTPUTS.clear()
        return
    _OUTPUTS[channel] = []


def _write_output(path: Path, channel: str = "main") -> None:
    lines = _OUTPUTS.get(channel, [])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote transcript to: {path.resolve()}")


def _write_all_outputs(mapping: Dict[str, Path]) -> None:
    for channel, path in mapping.items():
        _write_output(path, channel=channel)


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


MANUAL_TEST_TURNS = [
    "I ask Bran for a room to rent",
    "I ask Bran for food",
    "I ask Bran if he has heard any rumors",
    "I ask Elara what she sells",
    "I buy a torch from Elara",
    "I try to buy a sword I cannot afford",
    "I ask Elara to repair my gear",
    "I ask Bran for directions to the market",
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
            "I ask Elara what she sells",
            "I buy a torch from Elara",
        ],
    },
    "blocked_purchase": {
        "currency": {"gold": 0, "silver": 1, "copper": 0},
        "turns": [
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

            runtime_state = _safe_dict(cloned.get("runtime_state"))
            runtime_state["tick"] = 0
            runtime_state["turn_history"] = []
            runtime_state["last_turn_contract"] = {}
            runtime_state["last_turn_result"] = {}
            cloned["runtime_state"] = runtime_state

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
    session = _extract_session(result)
    direct = _safe_dict(session.get("simulation_state"))
    if direct:
        return direct

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    return _safe_dict(metadata.get("simulation_state"))


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
        "action_type": resolved.get("action_type"),
        "semantic_action_type": semantic_action.get("action_type"),
        "semantic_family": semantic_action.get("semantic_family"),
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
        "relationship_state": _extract_relationship_state(result),
        "npc_emotion_state": _extract_npc_emotion_state(result),
        "social_effects": service_debug.get("social_effects"),
        "stock_update": service_debug.get("stock_update"),
        "service_offer_state": _extract_service_offer_state(result),
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


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    simulation_state = _extract_simulation_state({"session": session})
    if not simulation_state:
        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        simulation_state = _safe_dict(metadata.get("simulation_state"))
        if not simulation_state:
            simulation_state = {}
            metadata["simulation_state"] = simulation_state

    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {"items": [], "equipment": {}, "capacity": 50, "last_loot": []}
        player_state["inventory_state"] = inventory_state

    inventory_state["currency"] = {
        "gold": int(currency.get("gold") or 0),
        "silver": int(currency.get("silver") or 0),
        "copper": int(currency.get("copper") or 0),
    }

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    if metadata is not setup_payload.get("metadata"):
        setup_payload["metadata"] = metadata
    metadata["simulation_state"] = simulation_state

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

    session = load_session(session_id)
    if not session:
        return False

    simulation_state = _extract_simulation_state({"session": session})
    if not simulation_state:
        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        simulation_state = _safe_dict(metadata.get("simulation_state"))
        if not simulation_state:
            simulation_state = {}
            metadata["simulation_state"] = simulation_state
        setup_payload["metadata"] = metadata
        session["setup_payload"] = setup_payload

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

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload

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
    _emit("RELATIONSHIP STATE:", channel=channel)
    _emit(_compact_json(_extract_relationship_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("NPC EMOTION STATE:", channel=channel)
    _emit(_compact_json(_extract_npc_emotion_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE OFFER STATE:", channel=channel)
    _emit(_compact_json(_extract_service_offer_state(result)), channel=channel)
    _emit("", channel=channel)
    _emit("SERVICE LIVING WORLD APPLICATION:", channel=channel)
    _emit(_compact_json({
        "memory_entry": service_debug.get("memory_entry"),
        "social_effects": service_debug.get("social_effects"),
        "stock_update": service_debug.get("stock_update"),
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
) -> None:
    _reset_output()

    summary_channel = "flat_summary"
    legacy_channel = "flat_legacy"
    output_map: Dict[str, Path] = {}
    summary_rows: List[Dict[str, Any]] = []

    _emit("Manual RPG LLM Transcript Summary", channel=summary_channel)
    _emit("", channel=summary_channel)
    _emit(f"session_id: {session_id}", channel=summary_channel)
    _emit("", channel=summary_channel)

    if not split_files:
        _emit("Manual RPG LLM Transcript", channel=legacy_channel)
        _emit("", channel=legacy_channel)
        _emit(f"session_id: {session_id}", channel=legacy_channel)

    for index, player_input in enumerate(turns, start=1):
        print(f"[manual] flat turn {index}/{len(turns)}: {player_input}", flush=True)

        before_result = apply_turn(session_id=session_id, player_input="I wait")
        before_currency = _extract_player_currency(before_result)
        before_items = _extract_player_items(before_result)
        result = apply_turn(session_id=session_id, player_input=player_input)

        summary_rows.append(
            _compact_turn_summary(
                index=index,
                player_input=player_input,
                result=result,
                before_currency=before_currency,
                before_items=before_items,
            )
        )

        if split_files:
            turn_channel = f"flat_turn_{index:02d}"
            _emit("Manual RPG LLM Transcript", channel=turn_channel)
            _emit("", channel=turn_channel)
            _emit(f"session_id: {session_id}", channel=turn_channel)
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


def run_service_scenarios(selected: str = "all", *, split_files: bool = True) -> None:
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
    _emit("", channel=summary_channel)

    if not split_files:
        _emit("Manual RPG Service Scenario Transcript", channel=legacy_channel)
        _emit("", channel=legacy_channel)
        _emit(f"scenario_filter: {selected}", channel=legacy_channel)
        _emit(f"scenario_count: {len(scenario_items)}", channel=legacy_channel)
        _emit("", channel=legacy_channel)

    for scenario_name, scenario in scenario_items:
        scenario_channel = f"service_{scenario_name}"
        target_channel = scenario_channel if split_files else legacy_channel
        session_id = f"manual_service_{scenario_name}"
        currency = _safe_dict(scenario.get("currency"))
        turns = _safe_list(scenario.get("turns"))

        print(f"[manual] scenario {scenario_name}: {len(turns)} turns", flush=True)

        _emit("", channel=target_channel)
        _emit("#" * 80, channel=target_channel)
        _emit(f"SCENARIO: {scenario_name}", channel=target_channel)
        _emit(f"session_id: {session_id}", channel=target_channel)
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
            scenario_summaries.append(
                {
                    "scenario": scenario_name,
                    "session_id": session_id,
                    "seeded_currency": currency,
                    "error": "scenario_session_seed_failed",
                    "turns": [],
                }
            )
            continue

        last_result: Dict[str, Any] = {}
        scenario_results: List[Dict[str, Any]] = []
        current_currency = currency

        for index, player_input in enumerate(turns, start=1):
            print(f"[manual] scenario {scenario_name} turn {index}/{len(turns)}: {player_input}", flush=True)

            if current_currency:
                _write_session_currency(session_id, current_currency)

            before_currency = current_currency or (
                _extract_player_currency(last_result) if last_result else currency
            )
            before_items = _extract_player_items(last_result) if last_result else []

            result = apply_turn(session_id=session_id, player_input=player_input)
            _print_turn(
                index,
                player_input,
                result,
                before_currency,
                before_items,
                channel=target_channel,
            )

            scenario_results.append(
                _compact_turn_summary(
                    index=index,
                    player_input=player_input,
                    result=result,
                    before_currency=before_currency,
                    before_items=before_items,
                )
            )

            next_currency = _effective_player_currency_after(result)
            if next_currency:
                current_currency = next_currency
            last_result = result

        scenario_summaries.append(
            {
                "scenario": scenario_name,
                "session_id": session_id,
                "seeded_currency": currency,
                "turns": scenario_results,
            }
        )

        if split_files:
            output_map[scenario_channel] = OUTPUT_DIR / f"manual_rpg_service_scenarios__{scenario_name}.txt"

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
    turns = args.turn or MANUAL_TEST_TURNS

    if args.all:
        run_manual_transcript(
            turns,
            session_id=args.session_id,
            split_files=not args.single_file,
        )
        run_service_scenarios(
            "all",
            split_files=not args.single_file,
        )
        return

    if args.service_scenarios:
        run_service_scenarios(
            args.scenario,
            split_files=not args.single_file,
        )
        return

    run_manual_transcript(
        turns,
        session_id=args.session_id,
        split_files=not args.single_file,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default="manual_test_session")
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
            if not args.no_code_diff:
                write_code_diff_snapshot(roots=code_diff_roots)
        finally:
            servers.stop()

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
