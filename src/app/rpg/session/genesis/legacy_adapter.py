"""Bridge Campaign Genesis v2 payloads into the current new-game creator."""

from __future__ import annotations

from typing import Any

from .contract import (
    CAMPAIGN_GENESIS_CONTRACT_VERSION,
    DEFAULT_GENESIS_CREATED_BY,
    CampaignGenesisContract,
    canonical_genesis_payload,
    genesis_contract_hash,
)

_CURRENT_WIZARD_BUILD = "636"
_ARCHETYPE_TO_BUILD = {
    "balanced_adventurer": "balanced_adventurer",
    "warrior": "warrior",
    "ranger": "ranger",
    "scout": "ranger",
    "silver_tongue": "silver_tongue",
    "face": "silver_tongue",
}
_GEAR_TAG_LABELS = {
    "melee_weapon": "Iron dagger",
    "ranged_weapon": "Shortbow",
    "survival_tool": "Rope coil",
    "travel_supplies": "Trail rations x3",
    "light_source": "Torch x2",
    "field_notes": "Field journal",
    "starting_coin": "10 gold",
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normal_key(value: object, fallback: str = "custom") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text or fallback


def _title_from_key(value: object, fallback: str = "Adventurer") -> str:
    text = str(value or fallback).strip().replace("_", " ")
    return " ".join(part.capitalize() for part in text.split()) or fallback


def _gear_labels(tags: list[str]) -> list[str]:
    labels = [_GEAR_TAG_LABELS[key] for tag in tags if (key := _normal_key(tag, "")) in _GEAR_TAG_LABELS]
    return labels or ["Iron dagger", "Trail rations x2", "10 gold"]


def _render_genesis_summary(contract: CampaignGenesisContract) -> str:
    stats = contract.initial_stats.model_dump(mode="json")
    stat_text = ", ".join(f"{key} {value}" for key, value in stats.items())
    gear_text = ", ".join(_gear_labels(contract.starter_gear_tags))
    story = contract.story_options
    parts = [
        f"Archetype: {_title_from_key(contract.drivers.archetype)}",
        f"Origin: {contract.identity.origin}",
        f"Motivation: {contract.drivers.motivation.primary}",
        f"Starter gear: {gear_text}",
        f"Stats: {stat_text}",
        f"Opening: {story.opening_hook or 'Tavern Rumor'}",
        f"Pace: {story.opening_pace or 'Balanced'}",
        f"Relationship: {story.relationship_preset or 'Unknown Outsider'}",
    ]
    if contract.drivers.flaw:
        parts.insert(3, f"Flaw: {contract.drivers.flaw}")
    return ". ".join(parts) + "."


def adapt_genesis_payload_to_new_game_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _safe_dict(payload.get("request") or payload)
    contract = CampaignGenesisContract.model_validate(raw.get("genesis") or raw)
    talent_ids = [_normal_key(talent.id, "") for talent in contract.drivers.talents]
    talent_ids = [key for key in talent_ids if key]
    build = _ARCHETYPE_TO_BUILD.get(_normal_key(contract.drivers.archetype), "balanced_adventurer")
    primary = talent_ids[0] if talent_ids else _normal_key(contract.drivers.archetype, "custom")
    world = contract.world_options
    system = contract.system_options
    identity = contract.identity
    return {
        "campaign_template": contract.campaign_template,
        "genre": contract.genre,
        "tone": contract.tone,
        "background": identity.background,
        "starting_location": world.starting_location,
        "player": {
            "name": identity.name,
            "pronouns": identity.pronouns,
            "background": identity.background,
            "build": build,
        },
        "primary_capability": primary,
        "secondary_capabilities": talent_ids[1:],
        "power_source": identity.power_source,
        "generated_class_name": _title_from_key(contract.drivers.archetype),
        "generated_class_summary": _render_genesis_summary(contract),
        "difficulty": world.difficulty,
        "world_activity": world.world_activity,
        "economy_pressure": world.economy_pressure,
        "combat_lethality": world.combat_lethality,
        "companions_enabled": system.companions,
        "permadeath": system.permadeath,
        "seed": world.seed,
        "features": {
            "autosave": system.autosave,
            "validator": system.validator,
            "background_soft_audit": system.background_soft_audit,
            "llm_narration": system.llm_narration,
            "image_generation": system.image_generation,
            "tts": system.tts,
            "stt": system.stt,
        },
    }


def _provenance(contract: CampaignGenesisContract) -> dict[str, Any]:
    return {
        "created_by": DEFAULT_GENESIS_CREATED_BY,
        "contract_version": CAMPAIGN_GENESIS_CONTRACT_VERSION,
        "compiler_version": None,
        "creation_seed": contract.world_options.seed,
        "contract_hash": genesis_contract_hash(contract),
        "wizard_build": _CURRENT_WIZARD_BUILD,
        "created_from": "rpg_create_campaign_wizard",
    }


def attach_genesis_to_created_session(result: dict[str, Any], contract: CampaignGenesisContract) -> dict[str, Any]:
    if result.get("ok") is not True:
        return result
    session_id = str(result.get("session_id") or "")
    if not session_id:
        return result
    from app.rpg.session.service import load_session, save_session

    session = load_session(session_id)
    if not session:
        return result
    genesis = canonical_genesis_payload(contract)
    provenance = _provenance(contract)
    state = _safe_dict(session.get("state"))
    metadata = _safe_dict(state.get("metadata"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    setup_payload = _safe_dict(session.get("setup_payload"))
    manifest = _safe_dict(session.get("manifest"))

    state["contract_version"] = CAMPAIGN_GENESIS_CONTRACT_VERSION
    state["genesis_snapshot"] = genesis
    state["creation_provenance"] = provenance
    state["character_genesis"] = {
        "identity": genesis.get("identity", {}),
        "starting_archetype": contract.drivers.archetype,
        "starting_motivation": contract.drivers.motivation.model_dump(mode="json"),
        "starting_flaw": contract.drivers.flaw,
        "starting_talents": [talent.model_dump(mode="json") for talent in contract.drivers.talents],
        "starting_values": list(contract.drivers.values),
    }
    state["character_state"] = {
        "current_motivation": contract.drivers.motivation.model_dump(mode="json"),
        "current_flaw": contract.drivers.flaw,
        "current_talents": [talent.model_dump(mode="json") for talent in contract.drivers.talents],
        "current_values": list(contract.drivers.values),
    }
    metadata.update(
        {
            "contract_version": CAMPAIGN_GENESIS_CONTRACT_VERSION,
            "created_by": provenance["created_by"],
            "contract_hash": provenance["contract_hash"],
            "origin": contract.identity.origin,
            "motivation": contract.drivers.motivation.model_dump(mode="json"),
            "flaw": contract.drivers.flaw,
            "talents": [talent.model_dump(mode="json") for talent in contract.drivers.talents],
            "values": list(contract.drivers.values),
        }
    )
    state["metadata"] = metadata
    setup_payload["genesis"] = genesis
    setup_payload["creation_provenance"] = provenance
    runtime_state["creation_provenance"] = provenance
    manifest["contract_version"] = CAMPAIGN_GENESIS_CONTRACT_VERSION
    manifest["contract_hash"] = provenance["contract_hash"]
    manifest["created_by"] = provenance["created_by"]
    session.update({"state": state, "setup_payload": setup_payload, "runtime_state": runtime_state, "manifest": manifest})
    saved = save_session(session, compact=False)
    return {**result, "session": saved, "game": saved.get("state", result.get("game", {}))}


def create_new_game_from_genesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _safe_dict(payload.get("request") or payload)
    contract = CampaignGenesisContract.model_validate(raw.get("genesis") or raw)
    legacy = adapt_genesis_payload_to_new_game_payload({"request": {"genesis": contract.model_dump(mode="json")}})
    from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

    result = create_new_game_session(RpgNewGameRequest.model_validate(legacy))
    return attach_genesis_to_created_session(result, contract)
