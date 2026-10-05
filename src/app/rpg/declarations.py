"""What the kernel reads about the RPG module without loading it (ADR-0016, PA-2.2): kernel imports only."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.declarations import CapacityCount, RetentionDeclaration, SettingsSection


def _delete_narration_events(connection: Any, retention_days: int, batch_size: int) -> int:
    return int(connection.execute(
        """
        DELETE FROM omnix_rpg_narration_events
         WHERE event_id IN (
             SELECT event_id
               FROM omnix_rpg_narration_events
              WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY created_at, event_id
              LIMIT %s
         )
        """,
        (max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)


def _count(table: str) -> Any:
    def count(connection: Any) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    return count


RETENTION = (
    RetentionDeclaration("rpg_narration_events", delete=_delete_narration_events, capacity_cleanup=True),
)
CAPACITY = (
    CapacityCount("rpg_turns", count=_count("omnix_rpg_turns")),
    CapacityCount("rpg_narration_events", count=_count("omnix_rpg_narration_events")),
)


class RpgSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    difficulty: str = "normal"
    world_activity: str = Field("standard", alias="worldActivity")
    economy_pressure: str = Field("normal", alias="economyPressure")
    combat_lethality: str = Field("normal", alias="combatLethality")
    companions: bool = True
    permadeath: bool = False
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = Field(True, alias="backgroundSoftAudit")
    llm_narration: bool = Field(True, alias="llmNarration")
    image_generation: bool = Field(False, alias="imageGeneration")
    tts: bool = False
    stt: bool = False
    campaign_defaults: dict[str, Any] = Field(default_factory=dict, alias="campaignDefaults")
    hermes_assist_mode: str = Field("review_each_step", alias="hermesAssistMode")


SETTINGS = (SettingsSection("rpg", RpgSettingsProfile, order=40),)
