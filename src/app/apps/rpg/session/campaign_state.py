"""The saved RPG campaign document: its typed envelope and the upcasters from older versions (WP-5.6).

A campaign's state (``omnix_rpg_campaigns.state_jsonb``, or a legacy session
file) is one document whose version is ``manifest.schema_version``. Loading
an older document runs the upcasters in order, each raising the version to
its target, then validates the envelope, so every saved session loads in the
current shape. The engine's sections (``state``, ``simulation_state``,
``runtime_state``, ``setup_payload``) stay free-form mappings: the envelope
types what every reader relies on, not the whole engine.

To change the shape: raise ``CURRENT_SCHEMA_VERSION`` and append an upcaster
whose target is the new version; never edit an existing one.
"""
from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict
from app.errors import DependencyUnavailable
from app.apps.rpg.foundation.state import access as _sections

CURRENT_SCHEMA_VERSION = 10


class NewerCampaignDocumentError(DependencyUnavailable):
    """The campaign was saved by a newer Omnix; this one refuses to load it rather than misread it (RQ-1.7)."""

    code = "rpg_campaign_requires_newer_omnix"

    def __init__(self, version: int) -> None:
        super().__init__(
            f"This campaign was saved by a newer version of Omnix (campaign format {version}; "
            f"this version reads up to {CURRENT_SCHEMA_VERSION}).",
            hint="Update Omnix to open this campaign.",
        )
        self.version = version


class CampaignManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    session_id: str = ""
    schema_version: int = Field(ge=1)
    title: str = ""


class CampaignState(BaseModel):
    """The envelope every saved campaign has once upcast."""

    model_config = ConfigDict(extra="allow")

    manifest: CampaignManifest
    state: dict[str, Any] = Field(default_factory=dict)
    simulation_state: dict[str, Any]
    runtime_state: dict[str, Any]
    setup_payload: dict[str, Any] = Field(default_factory=dict)


def schema_version(document: Any) -> int:
    """The document's ``manifest.schema_version``; 1 when it has none."""
    value = _safe_dict(_safe_dict(document).get("manifest")).get("schema_version")
    if value is None or isinstance(value, bool):
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _to_v4_ambient_runtime(document: dict[str, Any]) -> dict[str, Any]:
    """Versions 1-3 predate ambient narration: give the runtime its queue and counters."""
    runtime = _safe_dict(_sections.runtime_state_of(document))
    runtime.setdefault("ambient_queue", [])
    runtime.setdefault("ambient_seq", 0)
    runtime.setdefault("last_idle_tick_at", "")
    runtime.setdefault("last_player_turn_at", "")
    runtime.setdefault("idle_streak", 0)
    runtime.setdefault("ambient_cooldowns", {})
    runtime.setdefault("recent_ambient_ids", [])
    runtime.setdefault("pending_interrupt", None)
    runtime.setdefault("subscription_state", {"last_polled_seq": 0})
    runtime.setdefault("ambient_metrics", {"emitted": 0, "suppressed": 0, "coalesced": 0})
    document["runtime_state"] = runtime
    return document


# What a campaign's creation produced and no turn reads, by kind, at every place v5 kept a copy (RQ-1.1). A v6
# document keeps none of them: the upgrade stores each once, outside the document (omnix_rpg_campaign_artifacts).
CREATION_ARTIFACT_PATHS: dict[str, tuple[tuple[str, str], ...]] = {
    "compiled_genesis": (
        ("setup_payload", "compiled_genesis"),
        ("state", "compiled_genesis_snapshot"),
        ("runtime_state", "compiled_genesis_snapshot"),
    ),
    "bootstrap_snapshot": (
        ("setup_payload", "bootstrap_snapshot"),
        ("state", "bootstrap_snapshot"),
        ("runtime_state", "bootstrap_snapshot"),
    ),
}


def creation_artifacts(document: Any) -> dict[str, dict[str, Any]]:
    """The creation artifacts a document carries, one per kind (the first copy found)."""
    found: dict[str, dict[str, Any]] = {}
    for kind, paths in CREATION_ARTIFACT_PATHS.items():
        for section, key in paths:
            value = _safe_dict(_safe_dict(document).get(section)).get(key)
            if isinstance(value, dict) and value:
                found[kind] = value
                break
    return found


def split_creation_artifacts(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The document without its creation artifacts, and the artifacts (stored once, outside it)."""
    artifacts = creation_artifacts(document)
    for paths in CREATION_ARTIFACT_PATHS.values():
        for section, key in paths:
            holder = document.get(section)
            if isinstance(holder, dict) and key in holder:
                document[section] = {name: value for name, value in holder.items() if name != key}
    return document, artifacts


def _copper(purse: Any) -> int | None:
    if not isinstance(purse, dict):
        return None
    try:
        return int(purse.get("gold") or 0) * 100 + int(purse.get("silver") or 0) * 10 + int(purse.get("copper") or 0)
    except (TypeError, ValueError):
        return None


def _quantity(item: dict[str, Any]) -> int:
    try:
        return int(item.get("quantity", item.get("qty", 1)) or 0)
    except (TypeError, ValueError):
        return 0


def merge_inventories(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Make the sheet's inventory and every purse agree with the simulation's store; the differences found.

    The simulation's store (``player_state.inventory_state``) wins (owner decision Q-2). The purse it keeps
    is the one the turns write and the play screen shows, ``player_state.currency``; the store's own copy
    and the sheet's follow it. Before the first turn there is no store yet and nothing is merged.
    """
    simulation = _safe_dict(_sections.simulation_state_of(document))
    player_state = _safe_dict(_sections.player_state_of(simulation))
    store = _safe_dict(_sections.inventory_state_of(player_state))
    if not isinstance(store.get("items"), list):
        return document, []
    state = _safe_dict(document.get("state"))
    sheet = _safe_dict(state.get("player"))
    diffs: list[dict[str, Any]] = []

    sheet_items = [item for item in sheet.get("inventory") or () if isinstance(item, dict)]
    by_id = {str(item.get("item_id") or item.get("id") or item.get("name") or ""): item for item in sheet_items}
    projected = []
    for item in store["items"]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("item_id") or item.get("id") or item.get("name") or "")
        previous = by_id.pop(key, None)
        quantity = _quantity(item)
        if previous is None:
            diffs.append({"field": "inventory", "item": str(item.get("name") or key), "sheet": 0, "simulation": quantity})
        elif _quantity(previous) != quantity:
            diffs.append({"field": "inventory", "item": str(item.get("name") or key),
                          "sheet": _quantity(previous), "simulation": quantity})
        public = dict(previous or {})
        public.update({name: value for name, value in item.items() if name != "qty"})
        public.setdefault("id", key)
        public.setdefault("type", item.get("category"))
        public["quantity"] = quantity
        projected.append(public)
    for key, item in by_id.items():
        diffs.append({"field": "inventory", "item": str(item.get("name") or key), "sheet": _quantity(item), "simulation": 0})
    if sheet or projected:
        sheet["inventory"] = projected

    purse = player_state.get("currency") if isinstance(player_state.get("currency"), dict) else store.get("currency")
    if isinstance(purse, dict):
        for name, holder in (("simulation_store", store), ("sheet", sheet), ("simulation", player_state)):
            if _copper(holder.get("currency")) != _copper(purse):
                diffs.append({"field": "purse", "copy": name, "was": _copper(holder.get("currency")), "now": _copper(purse)})
            holder["currency"] = dict(purse)

    player_state["inventory_state"] = store
    simulation["player_state"] = player_state
    document["simulation_state"] = simulation
    if sheet:
        state["player"] = sheet
        document["state"] = state
    return document, diffs


def stored_setup_payload(setup: Any) -> dict[str, Any]:
    """The setup as a v6 document keeps it: without the copy of the simulation the world step is handed."""
    stored = dict(setup) if isinstance(setup, dict) else {}
    metadata = stored.get("metadata")
    if isinstance(metadata, dict) and "simulation_state" in metadata:
        stored["metadata"] = {key: value for key, value in metadata.items() if key != "simulation_state"}
    return stored


def _to_v6_sections(document: dict[str, Any]) -> dict[str, Any]:
    """Version 6 (RQ-1.1): one inventory, no copies of creation artifacts, every campaign bound to a world.

    - The sheet's inventory and every purse are made to agree with the simulation's store
      (``merge_inventories``).
    - The simulation's copy inside ``setup_payload.metadata`` (refreshed before each world step and saved with
      the session) is dropped: the step is handed the current simulation each time.
    - The compiled genesis and bootstrap snapshot leave the document where it is stored, not here: saving
      and the upgrade turn store each once outside it (``split_creation_artifacts``), so an upcast in memory
      loses nothing.
    - A campaign with no published world is bound to the starter town or the demo (``state.world_binding``);
      version 7 binds the starter town's to the starter world.
    """
    document, _ = merge_inventories(document)
    document["setup_payload"] = stored_setup_payload(document.get("setup_payload"))
    state = _safe_dict(document.get("state"))
    binding = _safe_dict(state.get("world_binding"))
    if not binding.get("world_id") and not binding.get("kind"):
        from app.apps.rpg.genesis.worlds.builtin_worlds import LEGACY_DEMO_PRESET_ID

        manifest = _safe_dict(document.get("manifest"))
        demo = LEGACY_DEMO_PRESET_ID in (manifest.get("created_from_preset"), manifest.get("source_template_id"))
        state["world_binding"] = {"kind": "demo" if demo else "starter"}
        document["state"] = state
    return document


def _to_v7_starter_world(document: dict[str, Any]) -> dict[str, Any]:
    """Version 7 (RQ-2.8): a campaign of the starter town plays from the starter world, The Market Road (its ids
    rewritten to the world's, its world model attached; ``genesis/worlds/builtin_worlds.py``)."""
    from app.apps.rpg.genesis.worlds.builtin_worlds import bind_to_starter_world

    return bind_to_starter_world(document)


def _to_v8_one_gear_record(document: dict[str, Any]) -> dict[str, Any]:
    """Version 8 (RQ-2.4): the hero's gear and pack in the one store (``foundation/state/gear.py``)."""
    from app.apps.rpg.foundation.state.gear import gather_gear

    return gather_gear(document)


def _to_v9_given_once(document: dict[str, Any]) -> dict[str, Any]:
    """Version 9 (RQ-1.5): what every load used to add when it was missing, added once: the environment's seed state
    (``upgrades/environment_seed.py``) and a published opening's quest and first actions
    (``upgrades/opening_progress.py``). A current document loads as stored."""
    from app.apps.rpg.session.upgrades.environment_seed import ensure_session_environment_seed_state
    from app.apps.rpg.session.upgrades.opening_progress import ensure_published_opening_progress

    return ensure_published_opening_progress(ensure_session_environment_seed_state(document))


def _to_v10_as_a_turn_reads_it(document: dict[str, Any]) -> dict[str, Any]:
    """Version 10 (RQ-1.5): what each turn's load used to do, done once: the hero's simulation record filled from the
    sheet (``upgrades/hero_record.py``), and narrations still pending from before WP-5.6 retired, which every load used
    to queue again (``upgrades/legacy_narration.py``)."""
    from app.apps.rpg.session.upgrades.hero_record import hydrate_hero
    from app.apps.rpg.session.upgrades.legacy_narration import retire_pending_narration

    return retire_pending_narration(hydrate_hero(document))


# (target version, upcaster), in order. Version 5 marks the interaction
# timeline, which the normalization below keeps for every version.
UPCASTERS: tuple[tuple[int, Callable[[dict[str, Any]], dict[str, Any]]], ...] = (
    (4, _to_v4_ambient_runtime),
    (6, _to_v6_sections),
    (7, _to_v7_starter_world),
    (8, _to_v8_one_gear_record),
    (9, _to_v9_given_once),
    (10, _to_v10_as_a_turn_reads_it),
)


def _normalize(document: dict[str, Any]) -> dict[str, Any]:
    """What every load guarantees whatever the version: ids, state sections, the interaction timeline."""
    from app.apps.rpg.session.upgrades.interaction_timeline import migrate_legacy_interactions

    manifest = _safe_dict(document.get("manifest"))
    if not manifest.get("id"):
        manifest["id"] = str(manifest.get("session_id") or "session:unknown")
    if not manifest.get("session_id") and manifest.get("id") != "session:unknown":
        manifest["session_id"] = manifest.get("id")
    document["manifest"] = manifest
    simulation = _safe_dict(_sections.simulation_state_of(document))
    simulation["presentation_state"] = _safe_dict(simulation.get("presentation_state"))
    simulation["memory_state"] = _safe_dict(simulation.get("memory_state"))
    document["simulation_state"] = simulation
    document["runtime_state"] = _safe_dict(_sections.runtime_state_of(document))
    return migrate_legacy_interactions(document)


def upcast_campaign_document(document: Any) -> dict[str, Any]:
    """``document`` in the current shape, envelope validated (``pydantic.ValidationError`` if it cannot be).

    A document newer than this code raises ``NewerCampaignDocumentError``.
    """
    upcast = _safe_dict(document)
    version = schema_version(upcast)
    if version > CURRENT_SCHEMA_VERSION:
        raise NewerCampaignDocumentError(version)
    for target, upcaster in UPCASTERS:
        if version < target:
            upcast = upcaster(upcast)
            version = target
    upcast = _normalize(upcast)
    manifest = _safe_dict(upcast.get("manifest"))
    manifest["schema_version"] = CURRENT_SCHEMA_VERSION
    upcast["manifest"] = manifest
    CampaignState.model_validate(upcast)
    return upcast


def load_campaign_save_package(package: Any) -> dict[str, Any] | None:
    """The campaign document a save package carries (format 8), in the current shape; None when it has none.

    A document newer than this Omnix is refused (``NewerCampaignDocumentError``, RQ-1.7).
    """
    from app.apps.rpg.foundation.persistence.package_loader import campaign_document_from_package

    document = campaign_document_from_package(_safe_dict(package))
    return upcast_campaign_document(document) if document is not None else None


def upcast_if_outdated(document: dict[str, Any]) -> dict[str, Any]:
    """A stored document upcast only when it predates the current version; current documents load as stored.

    A newer document is refused (``NewerCampaignDocumentError``), never read as stored.
    """
    version = schema_version(document)
    if version > CURRENT_SCHEMA_VERSION:
        raise NewerCampaignDocumentError(version)
    if version == CURRENT_SCHEMA_VERSION:
        return document
    return upcast_campaign_document(document)


__all__ = [
    "CREATION_ARTIFACT_PATHS",
    "CURRENT_SCHEMA_VERSION",
    "CampaignManifest",
    "CampaignState",
    "NewerCampaignDocumentError",
    "UPCASTERS",
    "creation_artifacts",
    "load_campaign_save_package",
    "merge_inventories",
    "schema_version",
    "split_creation_artifacts",
    "stored_setup_payload",
    "upcast_campaign_document",
    "upcast_if_outdated",
]
