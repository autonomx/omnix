-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-6: the world editor adds an entry to a topic, not only edits, regenerates or restores one; its
-- history records the addition ("manual_add") as it does the others.
ALTER TABLE omnix_rpg_world_entity_history
    DROP CONSTRAINT IF EXISTS omnix_rpg_world_entity_history_operation_check;

ALTER TABLE omnix_rpg_world_entity_history
    ADD CONSTRAINT omnix_rpg_world_entity_history_operation_check
    CHECK (operation IN ('manual_edit', 'manual_add', 'regenerate', 'restore'));
