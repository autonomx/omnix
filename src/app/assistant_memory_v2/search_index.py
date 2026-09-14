from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.persistence.database import PostgresDatabase, default_database

from .contracts import MemorySpaceKey, VisibilityScope


@dataclass(frozen=True, slots=True)
class SearchIndexState:
    index_graph_revision: int
    source_observation_watermark: int
    governance_digest: str
    projection_digest: str
    entry_count: int
    built_at: datetime | None


@dataclass(frozen=True, slots=True)
class SearchIndexStatus:
    state: SearchIndexState
    graph_revision: int
    observation_watermark: int
    governance_digest: str
    stale: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchIndexHit:
    ref_id: str
    item_type: str
    domain: str
    content: str
    rank: float
    evidence_observation_ids: tuple[str, ...]


def _space_values(space: MemorySpaceKey) -> tuple[str, str, str]:
    return space.principal_id, space.owner_type, space.owner_id


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _object_text(object_value: dict[str, Any]) -> str:
    if object_value.get("kind") == "entity":
        entity = object_value.get("entity") or {}
        return str(entity.get("entity_id") or "")
    return str(object_value.get("literal"))


class PostgresMemoryV2SearchIndex:
    """Rebuildable PostgreSQL search projection over active graph assertions.

    Canonical truth remains Observation Log -> Memory Graph. Search rows can be deleted and
    deterministically rebuilt at any time. Governance is checked again on every search so a
    revocation is fail-closed even before the next rebuild.
    """

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()

    @staticmethod
    def _governance_digest(connection: Any, space: MemorySpaceKey) -> str:
        rows = connection.execute(
            """
            SELECT observation_id, state, revision
              FROM omnix_memory_v2_observation_dispositions
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             ORDER BY observation_id
            """,
            _space_values(space),
        ).fetchall()
        return _digest([(str(row[0]), str(row[1]), int(row[2])) for row in rows])

    @staticmethod
    def _empty_state() -> SearchIndexState:
        empty = _digest([])
        return SearchIndexState(0, 0, empty, empty, 0, None)

    def state(self, space: MemorySpaceKey) -> SearchIndexState:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT index_graph_revision, source_observation_watermark,
                       governance_digest, projection_digest, entry_count, built_at
                  FROM omnix_memory_v2_search_index_state
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                _space_values(space),
            ).fetchone()
        if row is None:
            return self._empty_state()
        return SearchIndexState(
            index_graph_revision=int(row[0]),
            source_observation_watermark=int(row[1]),
            governance_digest=str(row[2]),
            projection_digest=str(row[3]),
            entry_count=int(row[4]),
            built_at=row[5],
        )

    def index_graph_revision(self, space: MemorySpaceKey) -> int:
        return self.state(space).index_graph_revision

    def status(self, space: MemorySpaceKey) -> SearchIndexStatus:
        state = self.state(space)
        with self.database.transaction() as connection:
            graph_row = connection.execute(
                """
                SELECT graph_revision
                  FROM omnix_memory_v2_graph_state
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                _space_values(space),
            ).fetchone()
            observation_row = connection.execute(
                """
                SELECT observation_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                _space_values(space),
            ).fetchone()
            governance_digest = self._governance_digest(connection, space)
        graph_revision = int(graph_row[0]) if graph_row is not None else 0
        observation_watermark = int(observation_row[0]) if observation_row is not None else 0
        reasons = []
        if state.index_graph_revision != graph_revision:
            reasons.append("graph_revision_mismatch")
        if state.source_observation_watermark != observation_watermark:
            reasons.append("observation_watermark_mismatch")
        if state.governance_digest != governance_digest:
            reasons.append("governance_changed")
        return SearchIndexStatus(
            state=state,
            graph_revision=graph_revision,
            observation_watermark=observation_watermark,
            governance_digest=governance_digest,
            stale=bool(reasons),
            reasons=tuple(reasons),
        )

    def rebuild(self, space: MemorySpaceKey) -> SearchIndexState:
        values = _space_values(space)
        with self.database.transaction() as connection:
            graph_row = connection.execute(
                """
                SELECT graph_revision, source_observation_watermark
                  FROM omnix_memory_v2_graph_state
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                 FOR UPDATE
                """,
                values,
            ).fetchone()
            authority_row = connection.execute(
                """
                SELECT observation_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                 FOR UPDATE
                """,
                values,
            ).fetchone()
            graph_revision = int(graph_row[0]) if graph_row is not None else 0
            graph_observation_watermark = int(graph_row[1]) if graph_row is not None else 0
            observation_watermark = int(authority_row[0]) if authority_row is not None else 0
            governance_digest = self._governance_digest(connection, space)

            rows = connection.execute(
                """
                SELECT a.assertion_id, a.visibility_scopes, a.subject_entity_id,
                       a.predicate, a.object_value, a.domain, a.revision,
                       COALESCE(
                           jsonb_agg(e.observation_id ORDER BY e.observation_id)
                               FILTER (WHERE e.observation_id IS NOT NULL),
                           '[]'::jsonb
                       ) AS evidence_ids,
                       BOOL_AND(COALESCE(d.state, 'active') = 'active') AS evidence_active
                  FROM omnix_memory_v2_graph_assertions a
                  LEFT JOIN omnix_memory_v2_assertion_observation_evidence e
                    ON e.assertion_id = a.assertion_id
                  LEFT JOIN omnix_memory_v2_observation_dispositions d
                    ON d.observation_id = e.observation_id
                 WHERE a.principal_id = %s AND a.owner_type = %s AND a.owner_id = %s
                   AND a.status = 'active'
                 GROUP BY a.assertion_id, a.visibility_scopes, a.subject_entity_id,
                          a.predicate, a.object_value, a.domain, a.revision
                 ORDER BY a.assertion_id
                """,
                values,
            ).fetchall()
            entries = []
            for row in rows:
                if row[8] is False:
                    continue
                object_value = dict(row[4])
                content = (
                    f"{row[2]!s} {str(row[3]).replace('_', ' ')} "
                    f"{_object_text(object_value)}"
                )
                entries.append(
                    {
                        "ref_id": str(row[0]),
                        "item_type": "assertion",
                        "domain": str(row[5]),
                        "content": content,
                        "visibility_scopes": list(row[1]),
                        "evidence_ids": [str(item) for item in row[7]],
                        "source_revision": int(row[6]),
                    }
                )
            projection_digest = _digest(entries)

            connection.execute(
                """
                INSERT INTO omnix_memory_v2_search_index_state (
                    principal_id, owner_type, owner_id, index_graph_revision,
                    source_observation_watermark, governance_digest,
                    projection_digest, entry_count, built_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (principal_id, owner_type, owner_id) DO UPDATE SET
                    index_graph_revision = EXCLUDED.index_graph_revision,
                    source_observation_watermark = EXCLUDED.source_observation_watermark,
                    governance_digest = EXCLUDED.governance_digest,
                    projection_digest = EXCLUDED.projection_digest,
                    entry_count = EXCLUDED.entry_count,
                    built_at = CURRENT_TIMESTAMP
                """,
                (
                    *values,
                    graph_revision,
                    observation_watermark,
                    governance_digest,
                    projection_digest,
                    len(entries),
                ),
            )
            connection.execute(
                """
                DELETE FROM omnix_memory_v2_search_index_entries
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                values,
            )
            for entry in entries:
                connection.execute(
                    """
                    INSERT INTO omnix_memory_v2_search_index_entries (
                        principal_id, owner_type, owner_id, item_type, ref_id,
                        domain, content, visibility_scopes, evidence_observation_ids,
                        source_revision, graph_revision
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
                    )
                    """,
                    (
                        *values,
                        entry["item_type"],
                        entry["ref_id"],
                        entry["domain"],
                        entry["content"],
                        _json(entry["visibility_scopes"]),
                        _json(entry["evidence_ids"]),
                        entry["source_revision"],
                        graph_revision,
                    ),
                )
            if graph_observation_watermark > observation_watermark:
                raise RuntimeError("graph source watermark exceeds Observation authority watermark")
        return self.state(space)

    def search(
        self,
        space: MemorySpaceKey,
        text: str,
        *,
        visible_scopes: tuple[VisibilityScope, ...],
        domains: tuple[str, ...] = (),
        limit: int = 20,
    ) -> list[SearchIndexHit]:
        active_evidence_sql = (
            "NOT EXISTS ("
            " SELECT 1 FROM jsonb_array_elements_text(i.evidence_observation_ids) evidence_id"
            " LEFT JOIN omnix_memory_v2_observation_dispositions d"
            "   ON d.observation_id = evidence_id"
            " WHERE COALESCE(d.state, 'active') <> 'active'"
            ")"
        )
        conditions = [
            "i.principal_id = %s",
            "i.owner_type = %s",
            "i.owner_id = %s",
            "i.search_vector @@ plainto_tsquery('simple', %s)",
            active_evidence_sql,
        ]
        where_params: list[Any] = [*_space_values(space), text]
        if domains:
            conditions.append("i.domain = ANY(%s)")
            where_params.append(list(domains))
        if visible_scopes:
            scope_conditions = []
            for scope in visible_scopes:
                scope_conditions.append("i.visibility_scopes @> %s::jsonb")
                where_params.append(_json([scope.model_dump(mode="json")]))
            conditions.append("(" + " OR ".join(scope_conditions) + ")")
        else:
            return []
        params = [text, *where_params, max(1, min(int(limit), 1000))]
        with self.database.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT i.ref_id, i.item_type, i.domain, i.content,
                       ts_rank_cd(i.search_vector, plainto_tsquery('simple', %s)) AS rank,
                       i.evidence_observation_ids
                  FROM omnix_memory_v2_search_index_entries i
                 WHERE {' AND '.join(conditions)}
                 ORDER BY rank DESC, i.item_type, i.ref_id
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        return [
            SearchIndexHit(
                ref_id=str(row[0]),
                item_type=str(row[1]),
                domain=str(row[2]),
                content=str(row[3]),
                rank=float(row[4]),
                evidence_observation_ids=tuple(str(item) for item in row[5]),
            )
            for row in rows
        ]
