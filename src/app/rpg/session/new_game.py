"""RPG new-game and playable demo preset session creation.

These helpers intentionally do not call LLM, image, TTS, or worker queues. They
create deterministic disk-backed session payloads synchronously so the browser can
switch sessions immediately and then continue through the normal RPG turn queue.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.rpg.session.service import archive_session, load_session, save_session

DEMO_PRESET_ID = "demo_glimmerdeep_pass_lvl14"
NEW_GAME_CONTRACT_VERSION = "rpg_new_game_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_session_id(prefix: str = "rpg") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{secrets.token_hex(4)}"


class RpgPlayerOptions(BaseModel):
    name: str = "Alyndra"
    pronouns: str = "she/her"
    background: str = "Wanderer"
    build: Literal["balanced_adventurer", "warrior", "ranger", "silver_tongue"] = "balanced_adventurer"
    portrait_seed: int | None = None


class RpgFeatureOptions(BaseModel):
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = True
    llm_narration: bool = True
    image_generation: bool = False
    tts: bool = False
    stt: bool = False


class RpgNewGameRequest(BaseModel):
    campaign_template: str = "classic_fantasy"
    starting_location: str = "rusty_flagon_tavern"
    player: RpgPlayerOptions = Field(default_factory=RpgPlayerOptions)
    difficulty: Literal["story", "normal", "harsh"] = "normal"
    world_activity: Literal["quiet", "standard", "living_world"] = "standard"
    companions_enabled: bool = True
    permadeath: bool = False
    seed: int | None = None
    features: RpgFeatureOptions = Field(default_factory=RpgFeatureOptions)


class RpgRenameSessionRequest(BaseModel):
    name: str


STARTING_BUILDS: dict[str, dict[str, Any]] = {
    "balanced_adventurer": {
        "label": "Balanced Adventurer",
        "role": "Adventurer",
        "stats": {"strength": 10, "dexterity": 10, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 10},
        "hp": {"current": 100, "max": 100},
        "stamina": {"current": 100, "max": 100},
        "mana": {"current": 40, "max": 40},
    },
    "warrior": {
        "label": "Warrior",
        "role": "Warrior",
        "stats": {"strength": 14, "dexterity": 10, "constitution": 13, "intelligence": 8, "wisdom": 10, "charisma": 9},
        "hp": {"current": 120, "max": 120},
        "stamina": {"current": 110, "max": 110},
        "mana": {"current": 20, "max": 20},
    },
    "ranger": {
        "label": "Ranger",
        "role": "Ranger",
        "stats": {"strength": 10, "dexterity": 14, "constitution": 11, "intelligence": 9, "wisdom": 13, "charisma": 9},
        "hp": {"current": 105, "max": 105},
        "stamina": {"current": 115, "max": 115},
        "mana": {"current": 30, "max": 30},
    },
    "silver_tongue": {
        "label": "Silver Tongue",
        "role": "Face",
        "stats": {"strength": 8, "dexterity": 10, "constitution": 10, "intelligence": 11, "wisdom": 11, "charisma": 14},
        "hp": {"current": 95, "max": 95},
        "stamina": {"current": 95, "max": 95},
        "mana": {"current": 50, "max": 50},
    },
}


STARTING_LOCATIONS: dict[str, dict[str, Any]] = {
    "rusty_flagon_tavern": {
        "title": "Rusty Flagon Tavern",
        "region": "Market Road",
        "location": "Rusty Flagon Tavern",
        "time_label": "Day 1 • 08:00",
        "weather": "Rainy",
        "summary": (
            "You sit near the hearth of the Rusty Flagon Tavern as rain taps against the shutters. "
            "Bran, the innkeeper, polishes a cup behind the counter while Elara the merchant argues quietly "
            "with a road-worn guard near the door. A notice board beside the stairs lists work for caravan guards, "
            "rat catchers, and anyone willing to investigate strange lights near the old quarry."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 08:00", "title": "New campaign started", "detail": "You arrived at the Rusty Flagon Tavern.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 08:00", "title": "Services available", "detail": "Bran is available for rooms, food, and rumors.", "kind": "service"},
            {"turn": 0, "time": "Day 1 • 08:00", "title": "Merchant nearby", "detail": "Elara is available for trade.", "kind": "economy"},
        ],
        "quick_actions": ["Talk to Bran", "Check the notice board", "Buy supplies", "Rent a room", "Leave for the market"],
    },
    "market_district": {
        "title": "Market District",
        "region": "Town",
        "location": "Market District",
        "time_label": "Day 1 • 09:00",
        "weather": "Cloudy",
        "summary": "Market stalls crowd the square, and voices rise over the smell of bread, rain, and horse leather.",
        "timeline": [
            {"turn": 0, "time": "Day 1 • 09:00", "title": "New campaign started", "detail": "You arrived at the Market District.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 09:00", "title": "Open market", "detail": "Merchants are setting out supplies, tools, and caravan notices.", "kind": "economy"},
        ],
        "quick_actions": ["Browse the stalls", "Talk to a merchant", "Look for rumors", "Check caravan notices", "Travel to the tavern"],
    },
    "northern_road": {
        "title": "Northern Road",
        "region": "Trade Road",
        "location": "Northern Road",
        "time_label": "Day 1 • 10:15",
        "weather": "Overcast",
        "summary": (
            "The Northern Road cuts between wet pines and wagon-rutted mud. A broken milestone leans beside the ditch, "
            "and fresh hoofprints lead toward the pass while older tracks vanish into the brush."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 10:15", "title": "New campaign started", "detail": "You started on the Northern Road.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 10:15", "title": "Road signs", "detail": "Fresh hoofprints and a damaged milestone point toward recent trouble.", "kind": "discovery"},
        ],
        "quick_actions": ["Inspect the hoofprints", "Follow the road north", "Search the brush", "Check supplies", "Return to town"],
    },
    "glimmerdeep_pass": {
        "title": "Glimmerdeep Pass",
        "region": "Mountain Pass",
        "location": "Glimmerdeep Pass",
        "time_label": "Day 1 • 09:42",
        "weather": "Cold, Windy",
        "temperature": -12,
        "summary": "The mountain winds howl through the narrow pass, carrying the scent of pine and snow. Jagged cliffs rise on both sides, and an ancient stone archway stands ahead, half-buried in drifts.",
        "timeline": [
            {"turn": 0, "time": "Day 1 • 09:42", "title": "New campaign started", "detail": "You arrived at Glimmerdeep Pass.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 09:42", "title": "Ancient archway", "detail": "A half-buried stone archway blocks part of the pass.", "kind": "discovery"},
        ],
        "quick_actions": ["Inspect the archway", "Look for tracks", "Listen to the wind", "Check your gear", "Travel back down the pass"],
    },
    "old_quarry": {
        "title": "Old Quarry",
        "region": "Abandoned Works",
        "location": "Old Quarry",
        "time_label": "Day 1 • 16:20",
        "weather": "Grey and still",
        "summary": (
            "The old quarry yawns open beneath a rim of cracked stone. Rusted pulleys creak in the breeze, and pale light "
            "glows from a fissure that should have gone dark years ago."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 16:20", "title": "New campaign started", "detail": "You arrived at the Old Quarry.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 16:20", "title": "Strange lights", "detail": "A pale glow seeps from a deep quarry fissure.", "kind": "mystery"},
        ],
        "quick_actions": ["Inspect the fissure", "Search the quarry floor", "Check the old pulley", "Light a torch", "Return to the road"],
    },
}


DEFAULT_INVENTORY: list[dict[str, Any]] = [
    {"id": "travelers_cloak", "name": "Traveler's cloak", "quantity": 1, "type": "clothing"},
    {"id": "bedroll", "name": "Bedroll", "quantity": 1, "type": "camping"},
    {"id": "waterskin", "name": "Waterskin", "quantity": 1, "type": "supply"},
    {"id": "ration", "name": "Ration", "quantity": 3, "type": "food"},
    {"id": "torch", "name": "Torch", "quantity": 2, "type": "tool"},
    {"id": "iron_dagger", "name": "Iron dagger", "quantity": 1, "type": "weapon"},
    {"id": "simple_bow", "name": "Simple bow", "quantity": 1, "type": "weapon"},
    {"id": "arrow", "name": "Arrow", "quantity": 20, "type": "ammo"},
    {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"},
]


def _simulation_state_stub(seed: int) -> dict[str, Any]:
    return {
        "seed": seed,
        "presentation_state": {"visual_state": {"image_requests": [], "visual_assets": []}},
        "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
        "survival": {"enabled": False, "events": []},
    }


def _base_manifest(session_id: str, title: str, now: str, *, source_template_id: str, kind: str) -> dict[str, Any]:
    return {
        "id": session_id,
        "session_id": session_id,
        "schema_version": 2,
        "title": title,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "source_pack_id": "rpg-core",
        "source_template_id": source_template_id,
        "archived": False,
        "kind": kind,
    }


def _new_game_state(request: RpgNewGameRequest, session_id: str, now: str) -> dict[str, Any]:
    build = STARTING_BUILDS.get(request.player.build, STARTING_BUILDS["balanced_adventurer"])
    location = STARTING_LOCATIONS.get(request.starting_location, STARTING_LOCATIONS["rusty_flagon_tavern"])
    features = request.features.model_dump(mode="json")
    seed = int(request.seed or secrets.randbits(31))
    return {
        "contract_version": NEW_GAME_CONTRACT_VERSION,
        "session_id": session_id,
        "title": f"{request.player.name} — {location['title']}",
        "location": location["location"],
        "current_location": location["location"],
        "summary": location["summary"],
        "current_turn": 0,
        "turn_count": 0,
        "updated_at": now,
        "metadata": {
            "kind": "new_game",
            "campaign_template": request.campaign_template,
            "difficulty": request.difficulty,
            "world_activity": request.world_activity,
            "seed": seed,
            "created_from_preset": None,
        },
        "player": {
            "name": request.player.name,
            "pronouns": request.player.pronouns,
            "background": request.player.background,
            "class": build["role"],
            "build": request.player.build,
            "level": 1,
            "xp": {"current": 0, "max": 100},
            "stats": build["stats"],
            "resources": {"hp": build["hp"], "stamina": build["stamina"], "mana": build["mana"]},
            "currency": {"gold": 10, "silver": 25, "copper": 50},
            "renown": "Unknown (0)",
            "equipment": [
                {"slot": "Weapon", "name": "Iron dagger"},
                {"slot": "Ranged", "name": "Simple bow"},
                {"slot": "Cloak", "name": "Traveler's cloak"},
            ],
            "inventory": DEFAULT_INVENTORY,
        },
        "world": {
            "time": location["time_label"],
            "weather": location["weather"],
            "temperature": location.get("temperature"),
            "reputation": {"label": "Unknown", "score": 0},
        },
        "party": [],
        "quests": [
            {"id": "notice_board_work", "title": "Work on the Notice Board", "status": "active", "objective": "Read the tavern notice board for available work."}
        ],
        "relationships": [],
        "encounter": {"status": "inactive", "title": "No active combat", "summary": "All quiet for now."},
        "timeline": location["timeline"],
        "journal": {"entries": location["timeline"]},
        "quick_actions": location.get("quick_actions", ["Look around", "Talk to someone nearby", "Check supplies", "Travel onward"]),
        "features": {**features, "companions_enabled": request.companions_enabled, "permadeath": request.permadeath},
    }


def _demo_state(session_id: str, now: str) -> dict[str, Any]:
    return {
        "contract_version": NEW_GAME_CONTRACT_VERSION,
        "session_id": session_id,
        "title": "Demo: Glimmerdeep Pass",
        "location": "Glimmerdeep Pass",
        "current_location": "Glimmerdeep Pass",
        "summary": "Faint tracks—large, clawed, and fresh—mar the snow near the archway. A torn banner from the Northern Watch flutters in the wind. Something big passed through here not long ago.",
        "current_turn": 73,
        "turn_count": 73,
        "updated_at": now,
        "metadata": {"kind": "playable_demo_clone", "created_from_preset": DEMO_PRESET_ID, "seed": 140914},
        "player": {
            "name": "Alyndra",
            "pronouns": "she/her",
            "background": "Wanderer of the North",
            "class": "Ranger",
            "level": 14,
            "xp": {"current": 7450, "max": 12000},
            "resources": {
                "hp": {"current": 86, "max": 110},
                "stamina": {"current": 72, "max": 100},
                "mana": {"current": 64, "max": 120},
            },
            "currency": {"gold": 1248},
            "renown": "Honored (35)",
            "equipment": [
                {"slot": "Weapon", "name": "Longbow of the Boreal Wind"},
                {"slot": "Armor", "name": "Shadow Leather Armor +2"},
                {"slot": "Cloak", "name": "Cloak of the Owl"},
                {"slot": "Ring", "name": "Band of Keen Senses"},
            ],
            "inventory": [
                {"name": "Health Potion", "quantity": 12},
                {"name": "Mana Potion", "quantity": 7},
                {"name": "Trail Rations", "quantity": 5},
                {"name": "Focus Crystal", "quantity": 3},
                {"name": "Rope Coil", "quantity": 2},
                {"name": "Torch", "quantity": 9},
                {"name": "Keenleaf", "quantity": 4},
                {"name": "Ancient Scroll", "quantity": 6},
            ],
        },
        "world": {"time": "Day 18 • 09:42", "weather": "Cold, Windy", "temperature": -12, "reputation": {"label": "Honored", "score": 35}},
        "party": [
            {"name": "Thorin Ironfist", "class": "Warrior", "level": 14, "resources": {"hp": {"current": 112, "max": 140}}},
            {"name": "Elandra", "class": "Mage", "level": 13, "resources": {"hp": {"current": 78, "max": 90}}},
            {"name": "Kael", "class": "Rogue", "level": 12, "resources": {"hp": {"current": 68, "max": 85}}},
        ],
        "quests": [
            {"id": "frostbound_relic", "title": "The Frostbound Relic", "status": "active", "objective": "Find the relic in Glimmerdeep."},
            {"id": "secrets_in_snow", "title": "Secrets in the Snow", "status": "active", "objective": "Investigate the old watchtower."},
            {"id": "icefang_alpha", "title": "Bounty: Icefang Alpha", "status": "active", "objective": "Track down the alpha beast."},
        ],
        "relationships": [
            {"name": "Thorin Ironfist", "stance": "Ally", "score": 78},
            {"name": "Elandra", "stance": "Ally", "score": 64},
            {"name": "Kael", "stance": "Ally", "score": 52},
            {"name": "Captain Bryn", "stance": "Neutral", "score": 10},
        ],
        "encounter": {"status": "inactive", "title": "No active combat", "summary": "All quiet for now."},
        "timeline": [
            {"turn": 73, "time": "Day 18 • 09:42", "title": "Arrived at Glimmerdeep Pass", "detail": "The party makes its way through the winding mountain trail and reaches the ancient pass.", "kind": "travel"},
            {"turn": 73, "time": "Day 18 • 09:42", "title": "Thorin watches the pass", "actor": "Thorin Ironfist", "detail": "Best keep our eyes open. This place gives me the chills.", "kind": "dialogue"},
            {"turn": 72, "time": "Day 18 • 09:40", "title": "Trail sign found", "detail": "Detected tracks near the northern archway.", "kind": "discovery"},
            {"turn": 69, "time": "Day 18 • 08:15", "title": "Left Frostpine Hollow", "detail": "Followed the northern trail.", "kind": "travel"},
            {"turn": 61, "time": "Day 17 • 21:30", "title": "Long Rest at Frostpine", "detail": "Recovered after the Icefang fight.", "kind": "rest"},
        ],
        "journal": {"entries": []},
        "features": {"autosave": True, "validator": True, "background_soft_audit": True, "llm_narration": True, "image_generation": False, "tts": False, "stt": False, "companions_enabled": True, "permadeath": False},
    }


def _save_created_session(session: dict[str, Any]) -> dict[str, Any]:
    saved = save_session(session, compact=False)
    manifest = saved.get("manifest", {})
    return {"ok": True, "session_id": manifest.get("session_id") or manifest.get("id"), "status": "ready", "session": saved, "game": saved.get("state", {})}


def create_new_game_session(request: RpgNewGameRequest) -> dict[str, Any]:
    now = _utc_now()
    session_id = _new_session_id("rpg")
    state = _new_game_state(request, session_id, now)
    seed = int(request.seed or state.get("metadata", {}).get("seed") or 0)
    session = {
        "manifest": _base_manifest(session_id, state["title"], now, source_template_id=request.campaign_template, kind="new_game"),
        "state": state,
        "setup_payload": request.model_dump(mode="json"),
        "simulation_state": _simulation_state_stub(seed),
        "runtime_state": {"active_job_id": None, "last_error": None, "created_from": "new_game"},
    }
    return _save_created_session(session)


def list_rpg_presets() -> dict[str, Any]:
    return {
        "ok": True,
        "presets": [
            {
                "preset_id": DEMO_PRESET_ID,
                "name": "Demo: Glimmerdeep Pass",
                "description": "Level 14 ranger party at Glimmerdeep Pass with quests, equipment, journal, relationships, and world state preloaded.",
                "kind": "in_progress_demo",
                "level": 14,
                "location": "Glimmerdeep Pass",
                "clone_on_start": True,
            }
        ],
    }


def start_rpg_preset(preset_id: str) -> dict[str, Any]:
    if preset_id != DEMO_PRESET_ID:
        return {"ok": False, "error": "unknown_rpg_preset", "preset_id": preset_id}
    now = _utc_now()
    session_id = _new_session_id("rpg_demo")
    state = _demo_state(session_id, now)
    session = {
        "manifest": {
            **_base_manifest(session_id, "Demo: Glimmerdeep Pass", now, source_template_id=preset_id, kind="playable_demo_clone"),
            "created_from_preset": preset_id,
            "preset_name": "Demo: Glimmerdeep Pass",
        },
        "state": state,
        "setup_payload": {"preset_id": preset_id, "mode": "clone_on_start"},
        "simulation_state": _simulation_state_stub(140914),
        "runtime_state": {"active_job_id": None, "last_error": None, "created_from": preset_id},
    }
    return _save_created_session(session)


def continue_rpg_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    return {"ok": True, "session_id": session_id, "status": "ready", "session": session, "game": session.get("state", {})}


def delete_rpg_session(session_id: str) -> dict[str, Any]:
    return archive_session(session_id)


def rename_rpg_session(session_id: str, name: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    manifest = dict(session.get("manifest") or {})
    manifest["title"] = str(name or "").strip() or manifest.get("title") or session_id
    manifest["updated_at"] = _utc_now()
    session["manifest"] = manifest
    saved = save_session(session, compact=False)
    return {"ok": True, "session_id": session_id, "session": saved}
