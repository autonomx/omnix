"""GPU engine swap coordination: live-speech leases, the swap lease, and swap requests (migration 0164).

Swap, don't stack: a job that needs a TTS engine other than the loaded one asks
for a swap and waits; one controller at a time holds the swap lease (fenced and
expiring), swaps the engine in, and restores the selected engine afterwards. A
swap never starts while a live-session lease exists, and recovery reads the
swap state to restore the selected engine after a crash.

The GPU is one device shared by every workspace, so these rows are not tenant
data; every function here works the same in any tenant scope.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .unit_of_work import unit_of_work

logger = logging.getLogger(__name__)

LIVE_KINDS = frozenset({"live_call", "read_aloud", "realtime"})


@dataclass(frozen=True)
class SwapState:
    fence_token: int
    phase: str
    holder_id: str | None
    engine: str | None
    restore_engine: str | None
    lease_expires_at: datetime | None
    group_started_at: datetime | None
    interrupted: bool
    detail: str
    lease_expired: bool

    @property
    def idle(self) -> bool:
        return self.phase == "idle"


class SwapFenceLost(RuntimeError):
    """Another controller took the swap lease (ours expired); stop acting on this swap."""


# --- Live-speech leases ----------------------------------------------------------------------


def acquire_live_session(kind: str, holder_id: str, *, ttl_seconds: float = 30.0, session_id: str | None = None) -> str:
    """Start (or renew) a live-speech lease; returns its id. Renew it while the call lasts."""
    if kind not in LIVE_KINDS:
        raise ValueError(f"unknown live session kind: {kind}")
    session = session_id or f"live:{uuid.uuid4().hex}"
    with unit_of_work() as work:
        work.connection.execute(
            """INSERT INTO omnix_tts_live_sessions (session_id, holder_id, kind, expires_at)
               VALUES (%s, %s, %s, clock_timestamp() + (%s * INTERVAL '1 second'))
               ON CONFLICT (session_id) DO UPDATE
                  SET expires_at = EXCLUDED.expires_at, holder_id = EXCLUDED.holder_id""",
            (session, holder_id[:255], kind, max(1.0, float(ttl_seconds))),
        )
        work.commit()
    return session


def release_live_session(session_id: str) -> None:
    with unit_of_work() as work:
        work.connection.execute("DELETE FROM omnix_tts_live_sessions WHERE session_id = %s", (session_id,))
        work.commit()


def live_session_active() -> bool:
    """Whether any live call or read-aloud holds an unexpired lease (expired rows are swept)."""
    with unit_of_work() as work:
        work.connection.execute("DELETE FROM omnix_tts_live_sessions WHERE expires_at <= clock_timestamp()")
        row = work.connection.execute(
            "SELECT 1 FROM omnix_tts_live_sessions WHERE expires_at > clock_timestamp() LIMIT 1"
        ).fetchone()
        work.commit()
    return row is not None


class LiveSpeechLease:
    """Hold a live-speech lease for as long as a call or read-aloud lasts, renewing it in the background.

    Live speech must never wait on bookkeeping: when the lease cannot be
    written (no PostgreSQL in this process, a transient error) the call goes
    on, and the swap controller simply cannot see it.
    """

    def __init__(self, kind: str, holder_id: str, *, ttl_seconds: float = 30.0, renew_seconds: float = 10.0) -> None:
        import threading

        self.kind = kind
        self.holder_id = holder_id
        self.ttl_seconds = ttl_seconds
        self.renew_seconds = renew_seconds
        self.session_id: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> LiveSpeechLease:
        import threading

        from .runtime import uses_postgresql_runtime

        try:
            if not uses_postgresql_runtime():
                return self
            self.session_id = acquire_live_session(self.kind, self.holder_id, ttl_seconds=self.ttl_seconds)
        except Exception:
            self.session_id = None
            return self
        self._thread = threading.Thread(target=self._renew, name="omnix-live-speech-lease", daemon=True)
        self._thread.start()
        return self

    def _renew(self) -> None:
        while not self._stop.wait(self.renew_seconds):
            try:
                acquire_live_session(self.kind, self.holder_id, ttl_seconds=self.ttl_seconds,
                                     session_id=self.session_id)
            except Exception:
                # The next renewal retries; a lapsed lease only lets a swap start early.
                logger.warning("Live-speech lease renewal failed", exc_info=True)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self.session_id:
            try:
                release_live_session(self.session_id)
            except Exception:
                # It expires on its own within the TTL.
                logger.warning("Live-speech lease release failed", exc_info=True)
            self.session_id = None

    def __enter__(self) -> LiveSpeechLease:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()


# --- Swap requests ---------------------------------------------------------------------------


def request_swap(engine: str, job_id: str) -> None:
    """Ask for ``engine`` on behalf of a waiting job (one pending request per job)."""
    with unit_of_work() as work:
        work.connection.execute(
            """INSERT INTO omnix_tts_swap_requests (id, engine, job_id)
               VALUES (%s, %s, %s)
               ON CONFLICT (job_id) WHERE status = 'pending' DO UPDATE
                  SET engine = EXCLUDED.engine, updated_at = clock_timestamp()""",
            (f"swapreq:{uuid.uuid4().hex}", engine, job_id),
        )
        work.commit()


def pending_swap_requests() -> list[dict[str, Any]]:
    """Pending requests in arrival order."""
    with unit_of_work() as work:
        rows = work.connection.execute(
            """SELECT id, engine, job_id, requested_at FROM omnix_tts_swap_requests
                WHERE status = 'pending' ORDER BY requested_at, id"""
        ).fetchall()
    return [{"id": row[0], "engine": row[1], "job_id": row[2], "requested_at": row[3]} for row in rows]


def swap_requests_pending() -> bool:
    with unit_of_work() as work:
        row = work.connection.execute("SELECT 1 FROM omnix_tts_swap_requests WHERE status = 'pending' LIMIT 1").fetchone()
    return row is not None


def resolve_swap_requests(engine: str, status: str, detail: str = "") -> int:
    """Mark every pending request for ``engine`` served (it is loaded) or failed (it cannot be)."""
    if status not in {"served", "failed"}:
        raise ValueError("status must be served or failed")
    with unit_of_work() as work:
        rows = work.connection.execute(
            """UPDATE omnix_tts_swap_requests SET status = %s, detail = %s, updated_at = clock_timestamp()
                WHERE status = 'pending' AND engine = %s RETURNING id""",
            (status, detail[:1000], engine),
        ).fetchall()
        work.commit()
    return len(rows)


def finish_swap_request(job_id: str) -> None:
    """The job that waited for a swap is done with the engine (it finished or failed)."""
    with unit_of_work() as work:
        work.connection.execute(
            """UPDATE omnix_tts_swap_requests SET status = 'done', updated_at = clock_timestamp()
                WHERE job_id = %s AND status IN ('pending', 'served')""",
            (job_id,),
        )
        work.commit()


def close_finished_requests() -> int:
    """Close the requests of jobs that ended without closing them.

    A job cancelled while it waited never runs again, and other modules' jobs
    (dubbing) do not close theirs; either would keep an engine requested or in
    use. Requests of jobs this database does not know are left alone.
    """
    from .tenant_scope import system_scope

    with system_scope("voice.swap"), unit_of_work() as work:
        rows = work.connection.execute(
            """UPDATE omnix_tts_swap_requests AS request SET status = 'done', updated_at = clock_timestamp()
                 FROM omnix_jobs AS job
                WHERE job.id = request.job_id AND request.status IN ('pending', 'served')
                  AND job.status IN ('completed', 'failed', 'canceled', 'stale')
               RETURNING request.id"""
        ).fetchall()
        work.commit()
    return len(rows)


def tts_jobs_running() -> bool:
    """Whether a TTS job of any workspace is running under a live lease (on the loaded engine).

    Jobs waiting for a swap are queued, so they do not count; a job whose
    worker died stops counting when its lease expires.
    """
    from .tenant_scope import system_scope

    with system_scope("voice.swap"), unit_of_work() as work:
        row = work.connection.execute(
            """SELECT 1 FROM omnix_jobs
                WHERE status IN ('leased', 'running', 'cancel_requested')
                  AND (resource_class = 'gpu:tts' OR resource_class LIKE 'gpu:tts:%')
                  AND lease_expires_at > clock_timestamp()
                LIMIT 1"""
        ).fetchone()
    return row is not None


def engine_in_use(engine: str, *, stale_after_seconds: float = 900.0, linger_seconds: float = 0.0) -> bool:
    """Whether a job still waits for, or runs on, ``engine`` under a swap.

    A served request older than ``stale_after_seconds`` counts as finished (its
    job crashed without saying so), so a lost job never pins the swap forever.
    With ``linger_seconds`` a job that finished that recently still counts: an
    interactive tool (voice design) sends its next preview within moments, and
    the engine should not be swapped out and back in between.
    """
    with unit_of_work() as work:
        row = work.connection.execute(
            """SELECT 1 FROM omnix_tts_swap_requests
                WHERE engine = %s
                  AND (status = 'pending'
                       OR (status = 'served' AND updated_at > clock_timestamp() - (%s * INTERVAL '1 second'))
                       OR (status = 'done' AND updated_at > clock_timestamp() - (%s * INTERVAL '1 second')))
                LIMIT 1""",
            (engine, max(1.0, float(stale_after_seconds)), max(0.0, float(linger_seconds))),
        ).fetchone()
    return row is not None


def swap_wait_seconds(job_id: str) -> float:
    """How long the job's pending swap request has been waiting (0 without one)."""
    with unit_of_work() as work:
        row = work.connection.execute(
            """SELECT EXTRACT(EPOCH FROM clock_timestamp() - requested_at) FROM omnix_tts_swap_requests
                WHERE job_id = %s AND status = 'pending'""",
            (job_id,),
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def swap_request_failure(job_id: str) -> str | None:
    """The reason a job's latest swap request failed, if it did and nothing is pending for it."""
    with unit_of_work() as work:
        row = work.connection.execute(
            """SELECT status, detail FROM omnix_tts_swap_requests WHERE job_id = %s
                ORDER BY updated_at DESC, requested_at DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
    if row is None or row[0] != "failed":
        return None
    return str(row[1] or "the engine could not be loaded")


# --- The swap lease ---------------------------------------------------------------------------


_STATE_COLUMNS = ("fence_token, phase, holder_id, engine, restore_engine, lease_expires_at, group_started_at, "
                  "interrupted, detail, (lease_expires_at IS NOT NULL AND lease_expires_at <= clock_timestamp())")


def _state(row: Any) -> SwapState:
    return SwapState(int(row[0]), str(row[1]), row[2], row[3], row[4], row[5], row[6], bool(row[7]),
                     str(row[8] or ""), bool(row[9]))


def swap_state() -> SwapState:
    with unit_of_work() as work:
        row = work.connection.execute(
            f"SELECT {_STATE_COLUMNS} FROM omnix_tts_swap_state WHERE model_class = 'tts'"
        ).fetchone()
    if row is None:
        return SwapState(0, "idle", None, None, None, None, None, False, "", False)
    return _state(row)


def begin_swap(holder_id: str, *, engine: str, restore_engine: str, lease_seconds: float) -> int | None:
    """Take the swap lease if no live swap holds it; returns the new fence token, or ``None``."""
    with unit_of_work() as work:
        row = work.connection.execute(
            """UPDATE omnix_tts_swap_state
                  SET fence_token = fence_token + 1, phase = 'swapping', holder_id = %s, engine = %s,
                      restore_engine = %s, interrupted = FALSE, detail = '',
                      lease_expires_at = clock_timestamp() + (%s * INTERVAL '1 second'),
                      group_started_at = clock_timestamp(), updated_at = clock_timestamp()
                WHERE model_class = 'tts'
                  AND (phase = 'idle' OR lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp())
                RETURNING fence_token""",
            (holder_id[:255], engine, restore_engine, max(5.0, float(lease_seconds))),
        ).fetchone()
        work.commit()
    return int(row[0]) if row else None


def update_swap(fence_token: int, *, phase: str | None = None, lease_seconds: float | None = None,
                detail: str | None = None, interrupted: bool | None = None) -> SwapState:
    """Change the swap under our fence; ``SwapFenceLost`` when another controller holds it."""
    assignments: list[str] = ["updated_at = clock_timestamp()"]
    values: list[Any] = []
    if phase is not None:
        if phase not in {"swapping", "active", "restoring"}:
            raise ValueError(f"bad swap phase: {phase}")
        assignments.append("phase = %s")
        values.append(phase)
    if lease_seconds is not None:
        assignments.append("lease_expires_at = clock_timestamp() + (%s * INTERVAL '1 second')")
        values.append(max(5.0, float(lease_seconds)))
    if detail is not None:
        assignments.append("detail = %s")
        values.append(detail[:1000])
    if interrupted is not None:
        assignments.append("interrupted = %s")
        values.append(bool(interrupted))
    with unit_of_work() as work:
        row = work.connection.execute(
            f"""UPDATE omnix_tts_swap_state SET {', '.join(assignments)}
                 WHERE model_class = 'tts' AND fence_token = %s AND phase <> 'idle'
                RETURNING {_STATE_COLUMNS}""",
            (*values, fence_token),
        ).fetchone()
        work.commit()
    if row is None:
        raise SwapFenceLost(f"swap fence {fence_token} is no longer held")
    return _state(row)


def end_swap(fence_token: int, *, detail: str = "", interrupted: bool = False) -> bool:
    """Release the swap lease (the selected engine is back, or the swap was interrupted)."""
    with unit_of_work() as work:
        row = work.connection.execute(
            """UPDATE omnix_tts_swap_state
                  SET phase = 'idle', holder_id = NULL, lease_expires_at = NULL, group_started_at = NULL,
                      interrupted = %s, detail = %s, updated_at = clock_timestamp()
                WHERE model_class = 'tts' AND fence_token = %s
                RETURNING fence_token""",
            (bool(interrupted), detail[:1000], fence_token),
        ).fetchone()
        work.commit()
    return row is not None


__all__ = [
    "LIVE_KINDS",
    "LiveSpeechLease",
    "SwapFenceLost",
    "SwapState",
    "acquire_live_session",
    "begin_swap",
    "close_finished_requests",
    "end_swap",
    "engine_in_use",
    "finish_swap_request",
    "live_session_active",
    "pending_swap_requests",
    "release_live_session",
    "request_swap",
    "resolve_swap_requests",
    "swap_request_failure",
    "swap_wait_seconds",
    "swap_requests_pending",
    "swap_state",
    "tts_jobs_running",
    "update_swap",
]
