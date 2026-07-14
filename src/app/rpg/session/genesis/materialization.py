"""Materialize approved Campaign Genesis into PostgreSQL and playable session state."""
from __future__ import annotations

import os
from typing import Any, Mapping

from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.world_forge_pipeline import CampaignWorldForgeResult


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _progress_payload(result: CampaignWorldForgeResult) -> dict[str, Any]:
    jobs = [job.as_dict() for job in result.generation.jobs]
    completed = sum(1 for job in jobs if job.get("status") == "completed")
    total = len(jobs)
    return {
        "status": "ready" if result.launch_ready else "failed",
        "stage": "launch_ready" if result.launch_ready else "consistency_failed",
        "completed_jobs": completed,
        "total_jobs": total,
        "percent": 100 if total == 0 else round(completed / total * 100),
        "launch_ready": result.launch_ready,
        "failed_topic_ids": list(result.generation.failed_topic_ids),
        "missing_requirements": list(result.compilation.missing_requirements),
    }


def materialize_world_forge_into_session(
    session: dict[str, Any],
    contract: CampaignGenesisContract,
    world_forge: CampaignWorldForgeResult,
) -> dict[str, Any]:
    """Attach portable projections and rich dossiers without changing canon authority."""

    bible = dict(world_forge.compilation.document)
    entities = _mapping(bible.get("entities"))
    state = _mapping(session.get("state"))
    runtime = _mapping(session.get("runtime_state"))
    setup = _mapping(session.get("setup_payload"))
    manifest = _mapping(session.get("manifest"))
    player_lore = {
        document_id: document
        for document_id, document in (
            (str(row.get("document_id") or ""), dict(row))
            for row in bible.get("documents") or ()
            if isinstance(row, Mapping)
        )
        if document_id and str(document.get("visibility") or "") in {"public", "player_known", "learned", "partially_known", "disputed"}
    }
    npc_dossiers = {
        entity_id: dict(entity)
        for entity_id, entity in entities.items()
        if isinstance(entity, Mapping) and entity.get("kind") == "npc"
    }
    location_dossiers = {
        entity_id: dict(entity)
        for entity_id, entity in entities.items()
        if isinstance(entity, Mapping) and entity.get("kind") == "location"
    }
    faction_dossiers = {
        entity_id: dict(entity)
        for entity_id, entity in entities.items()
        if isinstance(entity, Mapping) and entity.get("kind") == "faction"
    }
    state["campaign_bible"] = {
        "schema_version": bible.get("schema_version"),
        "canon_revision": bible.get("canon_revision"),
        "content_hash": bible.get("content_hash"),
        "manifest": dict(bible.get("manifest") or {}),
        "completeness": dict(bible.get("completeness") or {}),
        "discovery_state": dict(bible.get("discovery_state") or {}),
        "lore_pages": player_lore,
    }
    state["npc_dossiers"] = npc_dossiers
    state["location_dossiers"] = location_dossiers
    state["faction_dossiers"] = faction_dossiers
    state["opening_story_threads"] = list(bible.get("story_threads") or ())
    runtime["campaign_generation"] = _progress_payload(world_forge)
    runtime["campaign_bible_revision"] = bible.get("canon_revision")
    runtime["campaign_bible_content_hash"] = bible.get("content_hash")
    runtime["campaign_launch_gate"] = {
        "ready": world_forge.launch_ready,
        "required_before_first_turn": True,
        "missing_requirements": list(world_forge.compilation.missing_requirements),
    }
    setup["world_forge"] = {
        "depth": contract.world_forge.depth,
        "topic_graph": world_forge.graph.as_dict(),
        "generation_jobs": [job.as_dict() for job in world_forge.generation.jobs],
        "audit": world_forge.audit.as_dict(),
        "compilation": {
            "launch_ready": world_forge.compilation.launch_ready,
            "completeness": dict(world_forge.compilation.completeness),
            "content_hash": bible.get("content_hash"),
        },
    }
    manifest["campaign_bible_revision"] = bible.get("canon_revision")
    manifest["campaign_bible_content_hash"] = bible.get("content_hash")
    manifest["campaign_generation_status"] = "ready" if world_forge.launch_ready else "failed"
    session["state"] = state
    session["runtime_state"] = runtime
    session["setup_payload"] = setup
    session["manifest"] = manifest
    session["campaign_bible_projection"] = {
        "documents": list(bible.get("documents") or ()),
        "retrieval_cards": list(bible.get("retrieval_cards") or ()),
        "relationships": list(bible.get("relationships") or ()),
        "knowledge_rules": list(bible.get("knowledge_rules") or ()),
        "indexes": dict(bible.get("indexes") or {}),
        "discovery_state": dict(bible.get("discovery_state") or {}),
        "content_hash": bible.get("content_hash"),
        "canon_revision": bible.get("canon_revision"),
    }
    return session


def persist_campaign_genesis(
    session: Mapping[str, Any],
    contract: CampaignGenesisContract,
    world_forge: CampaignWorldForgeResult,
    *,
    database: Any | None = None,
    required: bool | None = None,
) -> dict[str, Any]:
    """Create campaign, Campaign Bible, and ready gate in one PostgreSQL transaction."""

    required = (
        os.environ.get("OMNIX_REQUIRE_POSTGRESQL_GENESIS", "").strip().casefold()
        in {"1", "true", "yes", "on"}
        if required is None
        else required
    )
    manifest = _mapping(session.get("manifest"))
    state = _mapping(session.get("state"))
    campaign_id = str(manifest.get("session_id") or manifest.get("id") or "")
    bible = dict(world_forge.compilation.document)
    if not campaign_id:
        raise ValueError("campaign genesis persistence requires a session id")
    try:
        from app.persistence.identity_service import bootstrap_local_tenant
        from app.persistence.unit_of_work import unit_of_work

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            campaign = work.rpg.get_campaign(context, campaign_id, for_update=True)
            if campaign is None:
                work.rpg.create_campaign(
                    context,
                    campaign_id=campaign_id,
                    title=str(state.get("title") or manifest.get("title") or campaign_id),
                    state=state,
                    engine_version="rne-campaign-genesis-v1",
                    schema_version=str(manifest.get("schema_version") or "rpg-session-v1"),
                    seed=str(contract.world_options.seed or 0),
                    metadata={
                        "campaign_template": contract.campaign_template,
                        "world_forge_depth": contract.world_forge.depth,
                    },
                )
            progress = _progress_payload(world_forge)
            work.campaign_genesis.start(
                context,
                genesis_run_id=f"genesis:{campaign_id}:1",
                campaign_id=campaign_id,
                depth=contract.world_forge.depth,
                topic_graph=world_forge.graph.as_dict(),
                progress={**progress, "status": "materializing", "stage": "materializing"},
            )
            stored_bible = work.campaign_bibles.put(
                context,
                campaign_id=campaign_id,
                document=bible,
                expected_revision=0,
                provenance={
                    "source": "campaign_genesis_world_forge",
                    "contract_version": contract.contract_version,
                    "depth": contract.world_forge.depth,
                },
                consistency_report=world_forge.audit.as_dict(),
                completeness=world_forge.compilation.completeness,
            )
            genesis = work.campaign_genesis.update(
                context,
                campaign_id=campaign_id,
                status="ready" if world_forge.launch_ready else "failed",
                jobs=[job.as_dict() for job in world_forge.generation.jobs],
                progress=progress,
                audit=world_forge.audit.as_dict(),
                bible_revision=int(stored_bible["revision"]),
                bible_content_hash=str(stored_bible["content_hash"]),
                error={} if world_forge.launch_ready else {
                    "missing_requirements": list(world_forge.compilation.missing_requirements)
                },
            )
            work.commit()
        return {
            "persisted": True,
            "mode": "postgresql_authority",
            "campaign_id": campaign_id,
            "campaign_bible": stored_bible,
            "genesis": genesis,
        }
    except Exception as exc:
        if required:
            raise
        return {
            "persisted": False,
            "mode": "portable_projection_only",
            "campaign_id": campaign_id,
            "error": type(exc).__name__,
            "detail": str(exc),
        }
