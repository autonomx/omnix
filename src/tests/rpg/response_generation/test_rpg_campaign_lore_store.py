from __future__ import annotations

from app.rpg.session.genesis.campaign_lore_store import (
    LoreRegenerationUnavailable,
    _generated_lore_text,
    _merge_published_world_canon,
    current_location_identity,
    ensure_current_location_document,
    regenerate_campaign_lore_document,
)
from app.rpg.session.genesis.campaign_lore_api import campaign_lore_payload
from app.rpg.worlds.published_canon_projection import project_published_canon


class _Gateway:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt, *, context, timeout_s):
        self.calls += 1
        assert "Campaign Bible entry" in prompt
        assert context["location"]["name"] == "Rusty Flagon Tavern"
        assert timeout_s == 20.0
        return (
            "The Rusty Flagon Tavern stands at a busy meeting point for travelers and local workers. "
            "Its warm common room smells of hearth smoke, bread, and rain-damp wool, while regulars trade news beneath scarred beams. "
            "Rooms, meals, and conversation make it both a refuge and a practical source of information about the surrounding roads."
        )


def _session() -> dict:
    return {
        "manifest": {"session_id": "campaign:elara", "title": "Elara"},
        "state": {
            "current_location": "Rusty Flagon Tavern",
            "metadata": {"genre": "classic_fantasy", "tone": "grounded"},
        },
    }


def test_current_location_identity_normalizes_legacy_location_strings() -> None:
    assert current_location_identity(_session()) == {
        "id": "location:rusty-flagon-tavern",
        "name": "Rusty Flagon Tavern",
    }


def test_missing_current_location_lore_is_generated_once_and_made_public() -> None:
    gateway = _Gateway()
    bible = {
        "canon_revision": 0,
        "documents": [],
        "entities": {},
        "discovery_state": {"pages": {}, "entities": {}, "discoveries": []},
    }

    updated, document_id, generated = ensure_current_location_document(
        bible,
        _session(),
        canon_revision=1,
        llm_gateway=gateway,
    )

    assert generated is True
    assert document_id == "lore:location:rusty-flagon-tavern"
    assert gateway.calls == 1
    document = updated["documents"][0]
    assert document["title"] == "Rusty Flagon Tavern"
    assert document["topic_id"] == "locations"
    assert document["visibility"] == "public"
    assert updated["discovery_state"]["pages"][document_id] == "public_at_campaign_start"
    assert updated["entities"]["location:rusty-flagon-tavern"]["kind"] == "location"

    unchanged, repeated_id, repeated = ensure_current_location_document(
        updated,
        _session(),
        canon_revision=2,
        llm_gateway=gateway,
    )
    assert repeated is False
    assert repeated_id == document_id
    assert len(unchanged["documents"]) == 1
    assert gateway.calls == 1


def test_published_world_backfill_preserves_campaign_lore_and_discoveries() -> None:
    world = {
        "campaign_id": "world-publication:one:1",
        "documents": [
            {
                "document_id": "lore:realm",
                "title": "The Realm",
                "visibility": "public",
            }
        ],
        "entities": {"location:capital": {"kind": "location", "name": "Capital"}},
        "discovery_state": {
            "pages": {"lore:realm": "public_at_campaign_start"},
            "entities": {"location:capital": "public_at_campaign_start"},
            "discoveries": [],
        },
    }
    campaign = {
        "documents": [
            {
                "document_id": "lore:location:rusty-flagon-tavern",
                "title": "Rusty Flagon Tavern",
                "visibility": "public",
            }
        ],
        "entities": {
            "location:rusty-flagon-tavern": {
                "kind": "location",
                "name": "Rusty Flagon Tavern",
            }
        },
        "discovery_state": {
            "pages": {
                "lore:realm": "learned",
                "lore:location:rusty-flagon-tavern": "public_at_campaign_start",
            },
            "entities": {},
            "discoveries": [{"document_id": "lore:realm", "status": "learned"}],
        },
    }

    merged = _merge_published_world_canon(
        world,
        campaign,
        campaign_id="campaign:elara",
    )

    assert merged["campaign_id"] == "campaign:elara"
    assert {row["document_id"] for row in merged["documents"]} == {
        "lore:realm",
        "lore:location:rusty-flagon-tavern",
    }
    assert merged["discovery_state"]["pages"]["lore:realm"] == "learned"
    assert merged["discovery_state"]["discoveries"] == [
        {"document_id": "lore:realm", "status": "learned"}
    ]


def test_structured_published_canon_becomes_player_safe_lore_pages() -> None:
    bible = project_published_canon(
        {
            "summary": "A luminous realm connected to Earth by unstable gates.",
            "themes": ["found family", "memory as power"],
            "cosmology": {"moons": ["Luma", "Veyr"]},
            "magic": {
                "name": "Resonance",
                "premise": "Memory and conviction shape aether.",
            },
            "regions": [
                {
                    "id": "region:starfall",
                    "name": "Starfall March",
                    "summary": "A frontier marked by gate scars.",
                }
            ],
            "factions": [
                {
                    "id": "faction:wayfarers",
                    "name": "Wayfarers' Guild",
                    "agenda": "Keep the roads open.",
                }
            ],
            "characters": [
                {
                    "id": "npc:guide",
                    "name": "The Guide",
                    "secrets": ["A hidden spoiler that must not be projected."],
                }
            ],
        },
        campaign_id="campaign:published",
        canon_revision=1,
    )
    session = {
        "campaign_bible_projection": bible,
        "state": {
            "campaign_bible": {
                "canon_revision": 1,
                "discovery_state": bible["discovery_state"],
            }
        },
    }

    payload = campaign_lore_payload(session)

    assert payload["visible_count"] == 5
    assert {row["category"] for row in payload["documents"]} == {
        "World Lore",
        "Regions",
        "Factions",
    }
    assert [row["name"] for row in payload["dossiers"]["factions"]] == [
        "Wayfarers' Guild"
    ]
    assert "hidden spoiler" not in str(
        {"documents": bible["documents"], "entities": bible["entities"]}
    ).casefold()


def test_page_regeneration_uses_direction_and_commits_a_new_revision(monkeypatch) -> None:
    document = {
        "document_id": "lore:cosmology",
        "topic_id": "cosmology",
        "title": "Cosmology",
        "full_text": "Two moons cross the sky above Aurelia.",
        "summary_500": "Two moons cross the sky above Aurelia.",
        "summary_120": "Two moons cross the sky.",
        "keywords": ["moons"],
        "visibility": "public",
        "canon_revision": 1,
    }
    bible = {
        "schema_version": "rpg_campaign_bible_v2",
        "campaign_id": "campaign:regen",
        "canon_revision": 1,
        "documents": [document],
        "entities": {},
        "retrieval_cards": [
            {
                "id": "card:lore:cosmology:medium",
                "document_id": "lore:cosmology",
                "summary_size": "medium",
                "content": document["summary_500"],
            }
        ],
        "discovery_state": {
            "pages": {"lore:cosmology": "public_at_campaign_start"},
            "entities": {},
            "discoveries": [],
        },
    }
    session = {
        "manifest": {"session_id": "campaign:regen", "title": "Aurelia"},
        "state": {"campaign_bible": {"discovery_state": bible["discovery_state"]}},
        "campaign_bible_projection": bible,
    }
    rich_text = "\n\n".join(
        " ".join(
            [
                "Moonlight settles across Aurelia in silver and violet layers, shaping the hours by which ordinary people travel, work, and gather.",
                *["Its familiar glow carries memory, custom, weathered beauty, and quiet meaning."] * 10,
            ]
        )
        for _ in range(5)
    )

    class Gateway:
        context = None

        def generate(self, _prompt, *, context, timeout_s):
            self.context = context
            assert timeout_s == 60.0
            return rich_text

    class CampaignBibles:
        def __init__(self):
            self.current = {
                "revision": 1,
                "document": bible,
                "content_hash": "old-hash",
                "provenance": {},
                "consistency_report": {},
                "completeness": {},
            }
            self.put_payload = None

        def get(self, *_args, **_kwargs):
            return self.current

        def put(self, _context, **kwargs):
            self.put_payload = kwargs
            return {
                **self.current,
                "revision": 2,
                "document": kwargs["document"],
                "content_hash": "new-hash",
            }

    campaign_bibles = CampaignBibles()

    class Work:
        def __init__(self):
            self.campaign_bibles = campaign_bibles
            self.world_scenarios = type(
                "WorldScenarios",
                (),
                {
                    "get_campaign_binding": lambda *_args, **_kwargs: None,
                },
            )()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

    gateway = Gateway()
    monkeypatch.setattr(
        "app.rpg.session.genesis.campaign_lore_store.load_campaign_lore",
        lambda *_args, **_kwargs: (session, {"persisted": True}),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.campaign_lore_store.default_database",
        lambda: object(),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.campaign_lore_store.bootstrap_local_tenant",
        lambda _database: object(),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.campaign_lore_store.unit_of_work",
        lambda _database: Work(),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.campaign_lore_store._save_portable_projection",
        lambda value: value,
    )

    updated, storage = regenerate_campaign_lore_document(
        "campaign:regen",
        session,
        document_id="lore:cosmology",
        direction="Focus on everyday rituals under both moons.",
        llm_gateway=gateway,
    )

    regenerated = updated["campaign_bible_projection"]["documents"][0]
    assert regenerated["full_text"] == rich_text
    assert regenerated["canon_revision"] == 2
    assert storage["revision"] == 2
    assert gateway.context["user_direction"] == (
        "Focus on everyday rituals under both moons."
    )
    assert campaign_bibles.put_payload["expected_revision"] == 1
    assert campaign_bibles.put_payload["document"]["retrieval_cards"][0][
        "content"
    ] == rich_text[:500].rstrip()


def test_named_page_regeneration_rejects_output_about_the_wrong_subject() -> None:
    tavern_text = "\n\n".join(
        " ".join(
            [
                "The Rusty Flagon Tavern is built from dark oak beside the river.",
                *["Its crowded common room smells of hearth smoke and rain."] * 14,
            ]
        )
        for _ in range(4)
    )

    try:
        _generated_lore_text(
            tavern_text,
            target={"title": "Echo Wolf", "topic_id": "monsters"},
        )
    except LoreRegenerationUnavailable as exc:
        assert "Echo Wolf" in str(exc)
    else:
        raise AssertionError("Off-topic lore must not replace the selected page")
