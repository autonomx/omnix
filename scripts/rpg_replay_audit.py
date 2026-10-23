"""Audit how well each RPG campaign replays from its snapshots and turn patches (RQ-0.9).

    python scripts/rpg_replay_audit.py [--database-url URL] [--json PATH] [--campaign ID ...]

Read-only: the transaction is ``READ ONLY``. The URL defaults to ``OMNIX_DATABASE_URL``.
For every campaign it reports:

- revisions with no turn row (state written outside a turn, e.g. a deferred narration save);
- turns with no patch (``state_delta_jsonb`` is null: committed before migration 0158);
- hash-chain breaks (a turn whose ``state_hash_before`` is not the previous turn's ``state_hash_after``);
- replay: from each snapshot whose stored hash verifies, the turn patches are applied while the chain is
  unbroken, and each result is checked against the turn's ``state_hash_after``. Verification restarts at the
  next snapshot after a gap. ``verified_turns`` counts turns whose replayed state matched;
- whether a replay reached the campaign's current revision and matched its stored hash;
- document versions (RQ-1.1): each turn's and snapshot's ``document_version``; a replayed state is compared
  only with a hash recorded at the same document version (a turn row's ``state_hash_after`` is of its own
  version's document), and ``verified_turns_by_document_version`` counts each version's verified turns. The
  upgrade turn (``system`` document upgrade) carries the patch from one version to the next, so a replay
  continues across the boundary, and the pinned snapshots on both sides verify it;
- the document's size per section (canonical JSON bytes), and the size of NPC-related sections, for the v6
  ``npcs`` budget (roadmap §4.2, F2).

On a database with row-level security, run it with a role that can read every workspace's RPG rows (the
migration owner).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.apps.rpg.foundation.persistence.rpg_repository import (  # noqa: E402
    canonical_json,
    document_version,
    state_hash,
)
from app.apps.rpg.foundation.persistence.state_delta import apply_state_delta  # noqa: E402

TOP_SECTIONS = 15


def _size(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))


def section_sizes(state: dict[str, Any]) -> dict[str, Any]:
    """Bytes per top-level key, per child of the engine sections, and of NPC-related keys."""
    sizes: dict[str, int] = {}
    npc_bytes = 0
    for key, value in state.items():
        sizes[key] = _size(value)
        if isinstance(value, dict) and key in {"simulation_state", "runtime_state", "state"}:
            for child, child_value in value.items():
                child_size = _size(child_value)
                sizes[f"{key}.{child}"] = child_size
                if "npc" in child.lower():
                    npc_bytes += child_size
    largest = sorted(
        ((name, size) for name, size in sizes.items() if "." in name),
        key=lambda item: (-item[1], item[0]),
    )[:TOP_SECTIONS]
    return {
        "total_bytes": _size(state),
        "top_level": {key: sizes[key] for key in sorted(state)},
        "largest_sections": dict(largest),
        "npc_related_bytes": npc_bytes,
    }


def audit_campaign(
    campaign: dict[str, Any],
    turns: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure audit of one campaign's rows; ``turns`` and ``snapshots`` are ordered by revision."""
    revision = int(campaign["revision"])
    turn_revisions = {int(turn["resulting_revision"]) for turn in turns}
    missing_turn_rows = sorted(set(range(1, revision + 1)) - turn_revisions)
    without_patch = [int(turn["resulting_revision"]) for turn in turns if turn["state_delta"] is None]
    chain_breaks = [
        int(current["resulting_revision"])
        for previous, current in zip(turns, turns[1:])
        if current["state_hash_before"] != previous["state_hash_after"]
    ]

    by_revision = {int(turn["resulting_revision"]): turn for turn in turns}
    verified_snapshots: list[int] = []
    bad_snapshots: list[int] = []
    verified_turns: set[int] = set()
    mismatched_turns: list[int] = []
    version_mismatches: list[int] = []
    by_version: dict[str, set[int]] = defaultdict(set)
    reached_current = False
    current_matches = False
    for snapshot in snapshots:
        start = int(snapshot["revision"])
        state = snapshot["state"]
        if state is None or state_hash(state) != snapshot["state_hash"]:
            bad_snapshots.append(start)
            continue
        verified_snapshots.append(start)
        at = start
        digest = snapshot["state_hash"]
        while True:
            turn = by_revision.get(at + 1)
            if turn is None or turn["state_delta"] is None or turn["state_hash_before"] != digest:
                break
            state = apply_state_delta(state, list(turn["state_delta"]))
            digest = state_hash(state)
            recorded = turn.get("document_version")
            if recorded is not None and document_version(state) != recorded:
                version_mismatches.append(at + 1)  # the patch did not produce a document of the turn's version
                break
            if digest != turn["state_hash_after"]:
                mismatched_turns.append(at + 1)
                break
            at += 1
            verified_turns.add(at)
            by_version[str(recorded if recorded is not None else "unrecorded")].add(at)
        if at == revision:
            reached_current = True
            current_matches = digest == campaign["state_hash"]

    return {
        "campaign_id": campaign["id"],
        "revision": revision,
        "schema_version": campaign["schema_version"],
        "turn_rows": len(turns),
        "revisions_without_turn_row": len(missing_turn_rows),
        "turns_without_patch": len(without_patch),
        "hash_chain_breaks": len(chain_breaks),
        "snapshots": len(snapshots),
        "verified_snapshots": len(verified_snapshots),
        "snapshots_failing_hash": bad_snapshots,
        "verified_turns": len(verified_turns),
        "mismatched_turns": sorted(set(mismatched_turns)),
        "document_version_mismatches": sorted(set(version_mismatches)),
        "verified_turns_by_document_version": {version: len(revisions) for version, revisions in sorted(by_version.items())},
        "document_version_boundaries": [
            int(current["resulting_revision"])
            for previous, current in zip(turns, turns[1:])
            if current.get("document_version") is not None
            and current["document_version"] != previous.get("document_version")
        ],
        "pinned_snapshots": [int(snapshot["revision"]) for snapshot in snapshots if snapshot.get("pinned")],
        "replay_reaches_current": reached_current,
        "replay_matches_current": current_matches,
        "first_missing_turn_rows": missing_turn_rows[:20],
        "first_chain_breaks": chain_breaks[:20],
        "size": section_sizes(campaign["state"]),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    sizes = sorted(result["size"]["total_bytes"] for result in results)
    return {
        "campaigns": len(results),
        "campaigns_with_missing_turn_rows": sum(1 for r in results if r["revisions_without_turn_row"]),
        "campaigns_with_chain_breaks": sum(1 for r in results if r["hash_chain_breaks"]),
        "campaigns_with_unpatched_turns": sum(1 for r in results if r["turns_without_patch"]),
        "campaigns_replaying_to_current": sum(1 for r in results if r["replay_matches_current"]),
        "revisions_total": sum(r["revision"] for r in results),
        "revisions_without_turn_row_total": sum(r["revisions_without_turn_row"] for r in results),
        "verified_turns_total": sum(r["verified_turns"] for r in results),
        "mismatched_turns_total": sum(len(r["mismatched_turns"]) for r in results),
        "state_bytes_max": sizes[-1] if sizes else 0,
        "state_bytes_median": sizes[len(sizes) // 2] if sizes else 0,
        "npc_related_bytes_max": max((r["size"]["npc_related_bytes"] for r in results), default=0),
    }


def _load(connection: Any, campaign_ids: list[str]) -> list[dict[str, Any]]:
    where = "WHERE id = ANY(%s)" if campaign_ids else ""
    params: tuple[Any, ...] = (campaign_ids,) if campaign_ids else ()
    campaigns = connection.execute(
        f"SELECT id, revision, state_jsonb, state_hash, schema_version FROM omnix_rpg_campaigns {where} ORDER BY id",
        params,
    ).fetchall()
    results = []
    for campaign_id, revision, state, digest, schema_version in campaigns:
        turns = [
            {
                "resulting_revision": row[0],
                "state_delta": row[1],
                "state_hash_before": row[2],
                "state_hash_after": row[3],
                "document_version": row[4],
            }
            for row in connection.execute(
                "SELECT resulting_revision, state_delta_jsonb, state_hash_before, state_hash_after, document_version "
                "FROM omnix_rpg_turns WHERE campaign_id = %s ORDER BY sequence",
                (campaign_id,),
            ).fetchall()
        ]
        snapshots = [
            {"revision": row[0], "state": row[1], "state_hash": row[2], "pinned": row[3], "document_version": row[4]}
            for row in connection.execute(
                "SELECT revision, snapshot_jsonb, state_hash, pinned, document_version FROM omnix_rpg_snapshots "
                "WHERE campaign_id = %s ORDER BY revision",
                (campaign_id,),
            ).fetchall()
        ]
        campaign = {
            "id": str(campaign_id),
            "revision": int(revision),
            "state": dict(state),
            "state_hash": str(digest),
            "schema_version": str(schema_version),
        }
        results.append(audit_campaign(campaign, turns, snapshots))
    return results


def run(database_url: str, campaign_ids: list[str]) -> dict[str, Any]:
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase

    database = PostgresDatabase(
        DatabaseSettings(
            url=database_url,
            pool_min=1,
            pool_max=1,
            connect_timeout_seconds=10,
            statement_timeout_ms=600_000,
            application_name="omnix-rpg-replay-audit",
        )
    )
    try:
        with database.transaction() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            results = _load(connection, campaign_ids)
    finally:
        database.close()
    return {
        "schema_version": 1,
        "measurement": "RPG campaign replay and size audit (RQ-0.9)",
        "date": date.today().isoformat(),
        "summary": summarize(results),
        "campaigns": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("OMNIX_DATABASE_URL", ""))
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--campaign", action="append", default=[], help="audit only this campaign id")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or OMNIX_DATABASE_URL is required")
    report = run(args.database_url, args.campaign)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
