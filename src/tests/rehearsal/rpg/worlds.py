"""Launch the three reference worlds for the RPG harnesses (RQ-0.4, RQ-0.5, RQ-0.6).

The harnesses play against a disposable PostgreSQL database: Aurelia and
Vesper-9 are imported from their committed bundles, adopted and launched from
their default opening scenario, and the starter town is a seeded new game.
Model calls are either answered by :class:`ScriptedModel` (by the call's role:
dialogue speaker, narration, canon dossier, intent) or go to the provider of
RPG's settings route (``rpg_llm_route``), which is Claude Haiku through the
Claude CLI on this install.

Nothing here is used by the application; it is test and measurement support.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[4]
BUNDLES = ROOT / "resources/examples/rpg/world-bundles"
WORLDS = ("aurelia", "vesper-9", "starter")
BUNDLE_DIRS = {
    "aurelia": "aurelia-echoes-beyond-the-gate",
    "vesper-9": "vesper-9-city-of-borrowed-minds",
}
DISPOSABLE_MARKERS = ("test", "bench")
LIVE_PORT = 5432


def require_disposable_database(allow: str = "") -> str:
    """The database URL, refused unless it names a disposable database and is not the live port.

    A disposable database's name contains ``test`` or ``bench``; ``allow`` names one more that the operator vouches
    for (``--allow-database``). Port 5432 is the live database and is always refused.
    """
    url = os.environ.get("OMNIX_DATABASE_URL", "")
    parsed = urlparse(url)
    name = (parsed.path or "").lstrip("/")
    if not url or not name:
        raise SystemExit("OMNIX_DATABASE_URL must name a disposable PostgreSQL database")
    if (parsed.port or LIVE_PORT) == LIVE_PORT:
        raise SystemExit("refusing port 5432: that is the live database")
    if not (any(marker in name for marker in DISPOSABLE_MARKERS) or (allow and name == allow)):
        raise SystemExit(
            f"database {name!r} is not marked disposable (name containing 'test' or 'bench', or --allow-database {name})"
        )
    return name


def bootstrap(resources_dir: Path | None = None) -> Path:
    """Sign-in off, a scratch resources folder, the PostgreSQL runtime and its job store."""
    os.environ.setdefault("OMNIX_AUTH_MODE", "disabled")
    resources = resources_dir or Path(tempfile.mkdtemp(prefix="omnix-rpg-harness-"))
    os.environ["OMNIX_RESOURCES_DIR"] = str(resources)
    from app.composition.runtime_composition import shared_service_repository_specs
    from app.jobs import store as job_store
    from app.persistence.repository_registry import install_repository_specs
    from app.persistence.shared_repository_specs import shared_repository_specs
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.runtime.feature_catalog import load_feature

    # The unit of work's repositories, as gateway composition registers them (tests/persistence/conftest.py).
    install_repository_specs(shared_repository_specs())
    install_repository_specs(shared_service_repository_specs())
    for feature_id in ("chat", "rpg"):
        install_repository_specs(tuple(load_feature(feature_id).repositories))
    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    return resources


# --- the scripted model -------------------------------------------------------------------------------------------

def _context_after(text: str) -> dict[str, Any]:
    try:
        return json.loads(text.rsplit("CONTEXT: ", 1)[1])
    except (IndexError, ValueError):
        return {}


class ScriptedModel:
    """Answers each model call by its role, so a harness can play without a provider.

    The dialogue call names the present NPC whose name the player used (else the first present NPC); narration
    answers with a fixed line; a canon dossier adds nothing; the intent router answers "{}" (no advice), so the
    deterministic engine decides.
    """

    name = "scripted"
    provider_id = "scripted"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def classify(self, text: str) -> str:
        if "decide which one present NPC" in text:
            return "dialogue"
        if "rpg_narration_candidates_v1" in text:
            return "narration_candidates"
        if "materializes durable, player-safe RPG canon" in text:
            return "canon_dossier"
        if "first-call semantic intent router" in text or "Read what the player means" in text:
            return "semantic_intent"  # the intent call (session/turn/intent.py), when the grammar is unsure
        if "Omnix RPG Narrative Writer" in text:
            return "narrative_writer"
        if "CONTEXT:" in text:
            return "turn_narration"
        return "unscripted"

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        from app.providers.base import ChatResponse

        text = "\n".join(str(getattr(message, "content", "")) for message in messages)
        kind = self.classify(text)
        answer = "{}"
        if kind == "dialogue":
            context = _context_after(text)
            present = context.get("present_npcs") or []
            said = json.dumps(context).lower()
            chosen = next((npc for npc in present if str(npc.get("name") or "").lower().split(" ")[0] in said), None)
            chosen = chosen or (present[0] if present else {})
            answer = json.dumps({"speaker_id": chosen.get("id") or "", "line": "Well met. Ask what you need."})
        elif kind == "narration_candidates":
            narration = {"format_version": "rpg_narration_v2", "narration": "The moment passes.", "action": "You take it in.",
                         "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": []}
            answer = json.dumps({"format_version": "rpg_narration_candidates_v1", "primary": narration, "safe_fallback": narration})
        elif kind == "canon_dossier":
            answer = json.dumps({"entities": [], "documents": [], "facts": [], "relationships": []})
        elif kind == "turn_narration":
            answer = "The moment passes."
        self.calls.append(kind)
        response = ChatResponse(content=answer, model="scripted")
        return iter([response]) if stream else response

    def supports_streaming(self) -> bool:
        return False

    def get_capabilities(self) -> list:
        return []


def scripted_narrative(payload: dict[str, Any]) -> dict[str, Any]:
    """The narrative engine's scripted writer: each beat says its first piece of approved evidence."""
    blocks = []
    for beat in payload.get("beats") or []:
        text = next(
            (str(record.get("text") or record.get("summary") or "").strip()
             for record in beat.get("approved_evidence") or []
             if str(record.get("text") or record.get("summary") or "").strip()),
            "",
        )
        blocks.append({"beat_id": beat["beat_id"], "sequence": beat["sequence"], "kind": beat["kind"],
                       "purpose": beat["purpose"], "speaker_id": beat.get("speaker_id") or "",
                       "text": text or "You take in your surroundings."})
    return {"blocks": blocks}


def install_scripted_model() -> ScriptedModel:
    """Route every provider lookup and the narrative writer to the scripted model."""
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter
    from app.providers import service as provider_service

    model = ScriptedModel()
    setattr(provider_service, "get_provider", lambda *args, **kwargs: model)
    setattr(narrative_service, "_production_writer",
            lambda: StructuredNarrativeWriter(scripted_narrative, provider="scripted", model="scripted"))
    return model


class CountingProvider:
    """Wraps a real provider and records each call's role, wall time and model name."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = getattr(inner, "name", "provider")
        self.provider_id = getattr(inner, "provider_id", self.name)
        self.calls: list[dict[str, Any]] = []
        self.resolved_models: set[str] = set()
        self._roles = ScriptedModel()

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self.inner, attribute)

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        import time

        text = "\n".join(str(getattr(message, "content", "") if not isinstance(message, dict) else message.get("content", ""))
                         for message in messages)
        started = time.perf_counter()
        record = {"role": self._roles.classify(text), "started": started, "head": text[:160], "tail": text[-400:]}
        self.calls.append(record)

        def note(response: Any) -> None:
            resolved = getattr(response, "model", None)
            if isinstance(resolved, str) and resolved:
                record["model"] = resolved
                self.resolved_models.add(resolved)

        def finish() -> None:
            record["ms"] = round((time.perf_counter() - started) * 1000, 1)

        try:
            response = self.inner.chat_completion(messages, model=model, stream=stream, **kwargs)
        except Exception:
            finish()
            raise
        if not stream:
            note(response)
            finish()
            return response

        def streamed():
            # A streamed call lasts until its last chunk is read.
            try:
                for chunk in response:
                    note(chunk)
                    yield chunk
            finally:
                finish()

        return streamed()


# The live install's RPG route (settings model roles, commit 040af3192a): Claude Haiku through the Claude CLI.
LIVE_RPG_ROUTE = ("claude_cli", "haiku")


def install_counting_provider(route: tuple[str, str] | None = LIVE_RPG_ROUTE, *, model: str = "",
                              effort: str = "") -> CountingProvider:
    """RPG's model calls go to a real provider, and are counted.

    ``route`` pins RPG's route (``provider_access.rpg_llm_route``) to a provider and model, as the live install's
    settings do; a disposable database's settings name its own default instead. ``None`` keeps the database's
    settings route. The settings service is installed first (as gateway composition does): the provider's own
    configuration is read from it. ``model`` names another model of the route's provider. ``effort`` sets the
    provider's effort level (the Claude CLI's ``--effort``) for this process, as its settings would; empty keeps the
    configured one.
    """
    from app.apps.rpg.foundation import provider_access
    from app.persistence.database import default_database
    from app.providers import service as provider_service
    from app.settings.access import install_database_settings_service

    install_database_settings_service(default_database())
    if route is not None and model:
        route = (route[0], model)
    if route is not None:
        setattr(provider_access, "rpg_llm_route", lambda: route)
    inner = provider_access.routed_provider(counted=False)  # the game counts its calls itself (model_calls): once
    if inner is None:
        raise SystemExit("RPG's route names no provider")
    if effort:
        inner.config.extra_params["effort"] = effort
    counting = CountingProvider(inner)
    setattr(provider_service, "get_provider", lambda *args, **kwargs: counting)
    return counting


def provider_identity(provider: Any = None) -> dict[str, Any]:
    from app.apps.rpg.foundation.provider_access import rpg_llm_route

    route = rpg_llm_route()
    identity = {"provider": route[0] if route else None, "model": route[1] if route else None}
    effort = str(getattr(provider, "effort", "") or "") if provider is not None else ""
    return {**identity, "effort": effort} if effort else identity


# --- launching ---------------------------------------------------------------------------------------------------

def _materializer(world: str):
    directory = BUNDLES / BUNDLE_DIRS[world]
    spec = importlib.util.spec_from_file_location(f"rpg_harness_{world.replace('-', '_')}_materialize",
                                                  directory / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, directory


def world_bundle(world: str) -> bytes:
    module, directory = _materializer(world)
    build: Callable[[Path], bytes] = getattr(module, "_build_bundle", None) or getattr(module, "build_bundle")
    return build(directory)


def launch_published(world: str, *, player_name: str = "Wren", scenario_hint: str = "",
                     starter_gear: tuple[str, ...] = ()) -> str:
    """Import, adopt and launch a bundled world's opening scenario; the new campaign's session id. ``starter_gear``:
    the hero's own kit, as a player who chooses it ("Iron Dagger", "10 silver"), in place of the opening's."""
    from app.apps.rpg.edge.api.feature_routes.rpg_world_library_routes import SESSION_CAMPAIGN_SESSIONS
    from app.apps.rpg.genesis.worlds.published_launch import launch_published_scenario
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    bundle = world_bundle(world)
    # One import per bundle content: a world whose bundle changed is imported again, not played stale.
    prefix = f"world:{world}-harness-{hashlib.sha256(bundle).hexdigest()[:8]}-"
    with unit_of_work() as work:
        # Scenario ids are unique across worlds, so a world whose openings are prepared at launch (Vesper-9) is
        # imported once per database and reused.
        reusable = next((str(row["world_id"]) for row in work.world_library.iter_scenarios(current_tenant())
                         if str(row.get("world_id") or "").startswith(prefix)), "")
        work.rollback()
    world_id = reusable or f"{prefix}{uuid.uuid4().hex[:10]}"
    if not reusable:
        imported = import_world_bundle(bundle, target_world_id=world_id)
        adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"])
    with unit_of_work() as work:
        has_scenarios = any(True for _ in work.world_library.iter_scenarios(current_tenant(), world_id=world_id))
        work.rollback()
    if not has_scenarios:
        # A bundle that carries its openings only as lore (Vesper-9): the library's "prepare openings" action.
        from app.apps.rpg.genesis.worlds.launch_repair_service import prepare_opening_scenarios_for_launch

        prepare_opening_scenarios_for_launch(world_id)
    with unit_of_work() as work:
        context = current_tenant()
        scenarios = list(work.world_library.iter_scenarios(context, world_id=world_id))
        row = work.world_scenarios.get_world(context, world_id) or {}
        metadata = row.get("metadata") or row.get("metadata_jsonb") or {}
        default = str(metadata.get("default_scenario_id") or "")
        scenario = next((row for row in scenarios if scenario_hint and scenario_hint in str(row["id"])), None)
        scenario = scenario or next((row for row in scenarios if default and str(row["id"]).endswith(default.split(":")[-1])), None)
        scenario = scenario or sorted(scenarios, key=lambda row: str(row["id"]))[0]
        document = dict(work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]["document"])
        work.rollback()
    launched = launch_published_scenario(
        sessions=SESSION_CAMPAIGN_SESSIONS,
        world_id=world_id,
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player={"name": player_name, "pronouns": "they/them"},
        features={"llm_narration": True, "image_generation": False},
        new_game={"generated_class_summary": f"Starter gear: {', '.join(starter_gear)}"} if starter_gear else None,
    )
    return str(launched["session_id"])


def launch_starter(seed: int = 7) -> str:
    from app.apps.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

    created = create_new_game_session(RpgNewGameRequest(seed=seed))
    if created.get("ok") is not True:
        raise RuntimeError(f"starter town new game failed: {created.get('error')}")
    return str(created["session_id"])


def launch(world: str, *, starter_gear: tuple[str, ...] = ()) -> str:
    if world == "starter":
        return launch_starter()
    return launch_published(world, starter_gear=starter_gear)


def turn_client():
    """A test client on the session routes (the turn, its draft and the session read)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from tests.support.routers import include_router_registrar

    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    # A turn that raises is a failed turn the harness records (HTTP 500), not the end of the run.
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "rpg-harness"},
                      raise_server_exceptions=False)


def load(session_id: str) -> dict[str, Any]:
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

    return load_session_from_postgres(session_id)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
