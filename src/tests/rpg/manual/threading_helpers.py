import os
import threading

def _default_scenario_workers() -> int:
    raw = os.environ.get("OMNIX_MANUAL_SCENARIO_WORKERS", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            print(
                f"[manual][parallel] invalid OMNIX_MANUAL_SCENARIO_WORKERS={raw!r}; using 8",
                flush=True,
            )
            return 8
    return 8

def _scenario_workers_source() -> str:
    raw = os.environ.get("OMNIX_MANUAL_SCENARIO_WORKERS", "").strip()
    if raw:
        return f"env:OMNIX_MANUAL_SCENARIO_WORKERS={raw}"
    return "default:8"

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

def _thread_label() -> str:
    current = threading.current_thread()
    return f"{current.name}:{current.ident}"