"""JSONB inventory classification (WP-5.9)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/jsonb_inventory.py"
spec = importlib.util.spec_from_file_location("jsonb_inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(inventory)


def test_usage_is_classified_per_table() -> None:
    columns = {"omnix_things": {"payload", "settings", "notes"}, "omnix_other": {"payload"}}
    literals = [
        "SELECT id FROM omnix_things WHERE payload->>'kind' = %s",
        "UPDATE omnix_things SET settings = settings || %s::jsonb WHERE id = %s",
        "SELECT payload FROM omnix_other WHERE id = %s",
    ]

    usage = inventory.classify(columns, literals)

    assert usage[("omnix_things", "payload")] == "queried"
    assert usage[("omnix_things", "settings")] == "partial_update"
    assert usage[("omnix_things", "notes")] == "opaque"
    assert usage[("omnix_other", "payload")] == "opaque"


def test_table_bodies_split_at_top_level_commas() -> None:
    parts = inventory._top_level_parts("a JSONB DEFAULT '{\"x\":1,\"y\":2}'::jsonb, b JSONB, c NUMERIC(10, 2)")
    assert [part.strip().split()[0] for part in parts] == ["a", "b", "c"]
