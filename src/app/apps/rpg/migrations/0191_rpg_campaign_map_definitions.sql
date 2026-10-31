-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-10: a site the game master filled in for one campaign has rooms with grids of its own. Map
-- definitions belonged to a world only; a campaign's own are kept beside them, under map ids that name the campaign,
-- and go with it. The world's definitions keep campaign_id NULL.
ALTER TABLE omnix_rpg_map_definitions
    ADD COLUMN IF NOT EXISTS campaign_id TEXT REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_map_definitions_campaign
    ON omnix_rpg_map_definitions (workspace_id, campaign_id) WHERE campaign_id IS NOT NULL;
