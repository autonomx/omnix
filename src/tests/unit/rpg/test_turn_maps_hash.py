"""A turn row records the hash of the map instances the turn moved anyone on, in id order (RQ-1.4)."""
from __future__ import annotations

import hashlib

from app.apps.rpg.foundation.persistence.rpg_repository import PostgresRpgRepository, canonical_json
from app.runtime.tenant_context import TenantContext


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        return _Rows(self.rows)


def test_the_maps_hash_covers_the_instances_this_transaction_touched_in_id_order() -> None:
    context = TenantContext(user_id="user:test", workspace_id="workspace:test", membership_id="member:test",
                            roles=frozenset({"owner"}))
    rows = [("instance:a", {"actors": [{"cell": [1, 2]}]}), ("instance:b", {"actors": []})]
    connection = _Connection(rows)
    digest = PostgresRpgRepository(connection).touched_maps_hash(context, "campaign:1")
    assert digest == hashlib.sha256(canonical_json([["instance:a", rows[0][1]], ["instance:b", rows[1][1]]])
                                    .encode("utf-8")).hexdigest()
    sql, params = connection.queries[0]
    assert "updated_at = CURRENT_TIMESTAMP" in sql and "ORDER BY map_instance_id" in sql
    assert params == ("workspace:test", "campaign:1")
    assert PostgresRpgRepository(_Connection([])).touched_maps_hash(context, "campaign:1") is None
