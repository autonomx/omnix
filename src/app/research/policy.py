"""Central limits, privacy, and retention policy for web research."""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.runtime_paths import resources_data_root


class ResearchRateLimitError(RuntimeError):
    def __init__(self, action: str, retry_after_seconds: int) -> None:
        super().__init__(f"research rate limit exceeded for {action}")
        self.action = action
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(frozen=True, slots=True)
class ResearchPolicy:
    search_cache_ttl_seconds: int = 300
    extraction_cache_ttl_seconds: int = 3_600
    quick_requests_per_minute: int = 12
    deep_requests_per_hour: int = 4
    provider_requests_per_minute: int = 30
    raw_snapshot_retention_days: int = 7
    source_manifest_retention_days: int = 30
    max_active_deep_jobs_per_session: int = 1
    planner_receives_conversation_history: bool = False
    synthesis_receives_raw_page_bodies: bool = False


def research_policy_from_env() -> ResearchPolicy:
    return ResearchPolicy(
        search_cache_ttl_seconds=_env_int("OMNIX_RESEARCH_SEARCH_CACHE_TTL_SECONDS", 300, 1, 86_400),
        extraction_cache_ttl_seconds=_env_int(
            "OMNIX_RESEARCH_EXTRACTION_CACHE_TTL_SECONDS", 3_600, 1, 604_800
        ),
        quick_requests_per_minute=_env_int("OMNIX_RESEARCH_QUICK_PER_MINUTE", 12, 1, 600),
        deep_requests_per_hour=_env_int("OMNIX_RESEARCH_DEEP_PER_HOUR", 4, 1, 100),
        provider_requests_per_minute=_env_int(
            "OMNIX_RESEARCH_PROVIDER_PER_MINUTE", 30, 1, 1_000
        ),
        raw_snapshot_retention_days=_env_int(
            "OMNIX_RESEARCH_RAW_RETENTION_DAYS", 7, 0, 365
        ),
        source_manifest_retention_days=_env_int(
            "OMNIX_RESEARCH_MANIFEST_RETENTION_DAYS", 30, 1, 3_650
        ),
        max_active_deep_jobs_per_session=1,
    )


def default_research_policy_db_path() -> Path:
    override = os.environ.get("OMNIX_RESEARCH_POLICY_DB_PATH")
    return Path(override) if override else resources_data_root() / "research_policy.sqlite"


class ResearchRateLimiter:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path) if path is not None else default_research_policy_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_rate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_rate_window "
                "ON research_rate_events(action, identity_key, provider, occurred_at)"
            )

    def check_and_record(
        self,
        *,
        action: str,
        identity: str,
        provider: str = "",
        limit: int,
        window_seconds: int,
    ) -> None:
        normalized_identity = _bounded_identity(identity)
        normalized_provider = str(provider or "").strip().lower()
        now = self.clock()
        cutoff = now - max(1, int(window_seconds))
        with self._connect() as connection:
            connection.execute("DELETE FROM research_rate_events WHERE occurred_at < ?", (cutoff - 86_400,))
            rows = connection.execute(
                """
                SELECT occurred_at FROM research_rate_events
                WHERE action = ? AND identity_key = ? AND provider = ? AND occurred_at >= ?
                ORDER BY occurred_at ASC
                """,
                (action, normalized_identity, normalized_provider, cutoff),
            ).fetchall()
            if len(rows) >= max(1, int(limit)):
                oldest = float(rows[0]["occurred_at"])
                retry_after = max(1, int(window_seconds - (now - oldest)))
                raise ResearchRateLimitError(action, retry_after)
            connection.execute(
                """
                INSERT INTO research_rate_events(action, identity_key, provider, occurred_at)
                VALUES(?,?,?,?)
                """,
                (action, normalized_identity, normalized_provider, now),
            )

    def quick_request(self, identity: str, policy: ResearchPolicy) -> None:
        self.check_and_record(
            action="quick_request",
            identity=identity,
            limit=policy.quick_requests_per_minute,
            window_seconds=60,
        )

    def deep_request(self, identity: str, policy: ResearchPolicy) -> None:
        self.check_and_record(
            action="deep_request",
            identity=identity,
            limit=policy.deep_requests_per_hour,
            window_seconds=3_600,
        )

    def provider_request(self, identity: str, provider: str, policy: ResearchPolicy) -> None:
        self.check_and_record(
            action="provider_request",
            identity=identity,
            provider=provider,
            limit=policy.provider_requests_per_minute,
            window_seconds=60,
        )


def privacy_contract(policy: ResearchPolicy | None = None) -> dict[str, object]:
    resolved = policy or research_policy_from_env()
    return {
        "planner_input": ["question", "budgets", "source_preferences", "compact_evidence_summary"],
        "planner_receives_conversation_history": resolved.planner_receives_conversation_history,
        "synthesis_input": ["question", "objective", "structured_evidence", "source_metadata", "conflicts", "limitations"],
        "synthesis_receives_raw_page_bodies": resolved.synthesis_receives_raw_page_bodies,
        "credentials_browser_readable": False,
        "unrelated_connected_data_included": False,
    }


def expiry_iso(days: int, *, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return datetime.fromtimestamp(
        current.timestamp() + max(0, days) * 86_400,
        tz=timezone.utc,
    ).isoformat()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _bounded_identity(value: str) -> str:
    text = " ".join(str(value or "anonymous").split()).strip()
    return text[:256] or "anonymous"
