-- omnix-migration: phase=expand transactional=true
-- RQ-1.4 (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md §4.1 "Maps get their own hash"): each turn row records the hash
-- of the map-instance snapshots the turn moved anyone on, in id order, beside state_hash_after (the document's
-- hash, whose chain is unchanged). Replay rebuilds those instances from omnix_rpg_campaign_map_events and checks
-- both. NULL when the turn touched no map.
ALTER TABLE omnix_rpg_turns
    ADD COLUMN IF NOT EXISTS maps_hash_after TEXT
        CHECK (maps_hash_after IS NULL OR length(maps_hash_after) = 64);
