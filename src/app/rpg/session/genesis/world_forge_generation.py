"""Parallel, dependency-aware World Forge topic generation.

Generation is provider-pluggable. Hosted tests use the deterministic generator;
production may inject a Hermes/model-backed generator that returns the same
structured topic contract.
"""
from __future__ import annotations

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .world_forge_contract import CampaignTopicGraph, CampaignTopicNode


@dataclass(frozen=True)
class GeneratedTopic:
    topic_id: str
    documents: tuple[Mapping[str, Any], ...] = ()
    entities: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    relationships: tuple[Mapping[str, Any], ...] = ()
    knowledge_rules: tuple[Mapping[str, Any], ...] = ()
    story_threads: tuple[Mapping[str, Any], ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "documents": [dict(row) for row in self.documents],
            "entities": [dict(row) for row in self.entities],
            "facts": [dict(row) for row in self.facts],
            "relationships": [dict(row) for row in self.relationships],
            "knowledge_rules": [dict(row) for row in self.knowledge_rules],
            "story_threads": [dict(row) for row in self.story_threads],
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class WorldForgeJobRecord:
    topic_id: str
    status: str
    dependency_ids: tuple[str, ...]
    generator_role: str
    output_counts: Mapping[str, int] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "status": self.status,
            "dependency_ids": list(self.dependency_ids),
            "generator_role": self.generator_role,
            "output_counts": dict(self.output_counts),
            "error": self.error,
        }


@dataclass(frozen=True)
class WorldForgeGenerationResult:
    topics: tuple[GeneratedTopic, ...]
    jobs: tuple[WorldForgeJobRecord, ...]
    failed_topic_ids: tuple[str, ...]
    generation_order: tuple[tuple[str, ...], ...]

    @property
    def passed(self) -> bool:
        return not self.failed_topic_ids

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "topics": [topic.as_dict() for topic in self.topics],
            "jobs": [job.as_dict() for job in self.jobs],
            "failed_topic_ids": list(self.failed_topic_ids),
            "generation_order": [list(batch) for batch in self.generation_order],
        }


class WorldForgeTopicGenerator(Protocol):
    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic: ...


_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


def _slug(value: str) -> str:
    return "_".join(part for part in "".join(ch.casefold() if ch.isalnum() else " " for ch in value).split() if part)


def _summary(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)].rstrip() + "…"


def _keywords(*values: str) -> list[str]:
    words: list[str] = []
    for value in values:
        for word in "".join(ch.casefold() if ch.isalnum() else " " for ch in value).split():
            if len(word) >= 4 and word not in words:
                words.append(word)
    return words[:24]


class DeterministicWorldForgeGenerator:
    """Provider-free structured fallback with campaign-specific rich seeds."""

    _KAVRIX_REGIONS = (
        ("aertos", "Aertos", "A tradition-bound kingdom of elemental academies, ancient forests, and living wards."),
        ("solara", "Solara", "An innovative kingdom of glass towers, brass machinery, and harnessed arcane power."),
        ("grimstone_hold", "Grimstone Hold", "A dwarven fortress-kingdom carved into the Spinebreaker Mountains."),
        ("sylvaniar_glade", "Sylvaniar Glade", "An elven realm hidden in a sentient forest of living halls and sentinel groves."),
        ("aok", "Aok, the Celestial Isle", "A floating crystal isle whose guardians command celestial energy."),
    )
    _CLASSIC_REGIONS = (
        ("market_road", "Market Road", "A rain-dark trade district linking the town market, inns, and caravan yards."),
        ("whispering_woods", "Whispering Woods", "An old forest where paths move and rumors travel faster than riders."),
        ("spinebreaker_mountains", "Spinebreaker Mountains", "A hard northern range cut by mines, passes, and sealed ruins."),
        ("east_marches", "East Marches", "Border fields shaped by raids, toll roads, and disputed watchtowers."),
        ("celestial_reach", "Celestial Reach", "High plateaus where observatories track unstable magic in the sky."),
    )

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        local_seed = int(hashlib.sha256(f"{seed}:{node.topic_id}".encode()).hexdigest()[:16], 16)
        rng = random.Random(local_seed)
        template = str(campaign_context.get("campaign_template") or "classic_fantasy")
        if node.category == "regions":
            return self._regions(node, template, rng)
        if node.category == "factions":
            return self._factions(node, template, rng)
        if node.category == "locations":
            return self._locations(node, template, campaign_context, rng)
        if node.category == "npcs":
            return self._npcs(node, template, campaign_context, rng)
        if node.category == "story":
            return self._story_threads(node, template)
        return self._lore(node, template, campaign_context)

    def _document(
        self,
        node: CampaignTopicNode,
        title: str,
        full_text: str,
        *,
        visibility: str | None = None,
        entity_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        document_id = f"lore:{_slug(title)}"
        return {
            "document_id": document_id,
            "topic_id": node.topic_id,
            "title": title,
            "full_text": full_text,
            "summary_500": _summary(full_text, 500),
            "summary_120": _summary(full_text, 120),
            "facts": [],
            "entities": list(entity_ids),
            "relationships": [],
            "keywords": _keywords(title, full_text),
            "visibility": visibility or node.visibility,
            "canon_revision": 0,
        }

    def _lore(
        self,
        node: CampaignTopicNode,
        template: str,
        context: Mapping[str, Any],
    ) -> GeneratedTopic:
        genre = str(context.get("genre") or template).replace("_", " ")
        tone = str(context.get("tone") or "heroic adventure")
        realm_name = "Kavrix" if "summoned" in template else str(context.get("realm_name") or "Eldervale")
        descriptions = {
            "realm": f"{realm_name} is a {genre} realm shaped by {tone}. Its lands, institutions, and conflicts are connected parts of one living history rather than isolated backdrops.",
            "cosmology": f"Reality in {realm_name} is layered. Mortal places, divine domains, and unstable thresholds obey explicit laws, and crossing those boundaries always carries a cost.",
            "magic_technology": "Magic is constrained by source, method, cost, range, and consequence. Technology can preserve or amplify magic, but cannot erase those constraints.",
            "history": f"The modern order of {realm_name} emerged from an age of ruptures, contested succession, and alliances formed against threats no single kingdom could survive.",
            "calendar": "The campaign calendar records eras, years, seasons, days, and event order so ages, travel, political terms, and historical sequences remain consistent.",
            "cultures": "Cultures are defined by practices, duties, taboos, material life, and relationships with neighboring peoples rather than by a single visual trait.",
            "institutions": "Guilds, academies, temples, courts, and military orders translate world beliefs into recruitment, law, education, and daily power.",
            "pantheon": "Religions distinguish public doctrine, private revelation, disputed interpretation, and secrets known only to initiates or supernatural beings.",
            "hero_system": "Exceptional heroes are integrated into politics and history. Their powers are documented by origin, limitations, social meaning, and the institutions seeking to recruit or control them.",
            "current_conflicts": "Current conflicts have named participants, incompatible goals, material stakes, escalation clocks, and locations where consequences can enter play.",
        }
        text = descriptions.get(node.topic_id, f"{node.title} establishes structured campaign canon for {realm_name}.")
        entity_id = f"realm:{_slug(realm_name)}" if node.topic_id == "realm" else f"topic:{node.topic_id}"
        authority = "objective_canon"
        fact = {
            "id": f"fact:{node.topic_id}:foundation",
            "subject": entity_id,
            "predicate": "foundation",
            "object": text,
            "content": text,
            "authority": "generated_proposal",
            "approved_authority": authority,
            "visibility": "public" if node.visibility == "public" else node.visibility,
            "entity_refs": [entity_id],
            "category": node.category,
        }
        entity = {
            "id": entity_id,
            "name": realm_name if node.topic_id == "realm" else node.title,
            "kind": "realm" if node.topic_id == "realm" else "lore_topic",
            "visibility": node.visibility,
        }
        document = self._document(node, node.title if node.topic_id != "realm" else realm_name, text, entity_ids=(entity_id,))
        return GeneratedTopic(
            topic_id=node.topic_id,
            documents=(document,),
            entities=(entity,),
            facts=(fact,),
            provenance={"generator": "deterministic_world_forge_v1", "template": template},
        )

    def _regions(self, node: CampaignTopicNode, template: str, rng: random.Random) -> GeneratedTopic:
        seeds = self._KAVRIX_REGIONS if "summoned" in template else self._CLASSIC_REGIONS
        rows = list(seeds)
        while len(rows) < node.target_count:
            index = len(rows) + 1
            rows.append((f"frontier_{index}", f"Frontier {index}", f"A contested frontier region marked by route {rng.randint(2, 9)} and an unresolved local claim."))
        rows = rows[: node.target_count]
        entities = []
        facts = []
        documents = []
        for slug, name, description in rows:
            entity_id = f"region:{slug}"
            entities.append({"id": entity_id, "name": name, "kind": "region", "realm_id": "realm:kavrix" if "summoned" in template else "realm:eldervale", "visibility": "public"})
            facts.append({"id": f"fact:{slug}:overview", "content": description, "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "public", "entity_refs": [entity_id]})
            documents.append(self._document(node, name, description, visibility="public", entity_ids=(entity_id,)))
        return GeneratedTopic(node.topic_id, tuple(documents), tuple(entities), tuple(facts), provenance={"generator": "deterministic_world_forge_v1"})

    def _factions(self, node: CampaignTopicNode, template: str, rng: random.Random) -> GeneratedTopic:
        if "summoned" in template:
            base = [
                ("obsidian_order", "The Obsidian Order", "discipline", "control summoned heroes through law and military service"),
                ("infernal_syndicate", "The Infernal Syndicate", "ambition", "turn unstable power into private dominion"),
                ("silent_chorus", "The Silent Chorus", "ritual silence", "prepare the return of the Unmaker"),
                ("academy_of_heroes", "Academy of Heroes", "instruction", "train and classify summoned champions"),
                ("adventurers_guild", "Adventurer's Guild", "pragmatism", "match dangerous work with capable outsiders"),
            ]
        else:
            base = [
                ("northern_watch", "Northern Watch", "duty", "hold the roads against raiders and winter threats"),
                ("merchant_compact", "Merchant Compact", "profit", "protect caravan routes and favorable tolls"),
                ("ash_covenant", "Ash Covenant", "secrecy", "recover sealed relics before rival powers"),
                ("academy", "Royal Academy", "knowledge", "study magic without destabilizing the realm"),
                ("adventurers_guild", "Adventurer's Guild", "pragmatism", "organize dangerous work and local bounties"),
            ]
        rows = list(base)
        while len(rows) < node.target_count:
            index = len(rows) + 1
            rows.append((f"faction_{index}", f"Faction {index}", "survival", f"secure leverage over frontier route {rng.randint(2, 9)}"))
        entities = []
        facts = []
        documents = []
        relationships = []
        for slug, name, value, goal in rows[: node.target_count]:
            entity_id = f"faction:{slug}"
            description = f"{name} values {value} and seeks to {goal}. Its public mission and private methods do not always agree."
            entities.append({"id": entity_id, "name": name, "kind": "faction", "values": [value], "goals": [goal], "visibility": "partially_known"})
            facts.append({"id": f"fact:{slug}:goal", "content": description, "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "partially_known", "entity_refs": [entity_id]})
            documents.append(self._document(node, name, description, visibility="partially_known", entity_ids=(entity_id,)))
        faction_ids = [str(row["id"]) for row in entities]
        for left, right in zip(faction_ids, faction_ids[1:]):
            relationships.append({"id": f"relationship:{_slug(left)}:rivals:{_slug(right)}", "source_id": left, "target_id": right, "kind": "rivals", "content": f"{left} and {right} compete over policy, recruits, or territory.", "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "partially_known", "entity_refs": [left, right]})
        return GeneratedTopic(node.topic_id, tuple(documents), tuple(entities), tuple(facts), tuple(relationships), provenance={"generator": "deterministic_world_forge_v1"})

    def _locations(
        self,
        node: CampaignTopicNode,
        template: str,
        context: Mapping[str, Any],
        rng: random.Random,
    ) -> GeneratedTopic:
        opening = str(context.get("starting_location") or "rusty_flagon_tavern")
        if "summoned" in template:
            base = [
                (opening, "Vanta Gate", "region:aertos", "A black summoning chamber ringed by mirror traps, delay glyphs, and sacrificial channels."),
                ("academy_courtyard", "Academy Courtyard", "region:aertos", "A warded court where summoned heroes are registered beneath elemental banners."),
                ("solara_research_hall", "Solara Research Hall", "region:solara", "A glass-and-brass laboratory built to measure unfamiliar powers."),
                ("grimstone_gate", "Grimstone Gate", "region:grimstone_hold", "A mountain gate of runed stone guarded by oath-bound smiths."),
                ("sentinel_groves", "Sentinel Groves", "region:sylvaniar_glade", "Living paths and concealed watchtowers guard the elven heartwood."),
                ("aok_crystal_spire", "Aok Crystal Spire", "region:aok", "A celestial observatory suspended above waterfalls that vanish into cloud."),
            ]
        else:
            base = [
                (opening, "Rusty Flagon Tavern", "region:market_road", "A rain-worn tavern where Bran serves travelers, merchants trade rumors, and the notice board changes daily."),
                ("market_district", "Market District", "region:market_road", "A crowded square of workshops, caravan stalls, and guarded warehouses."),
                ("old_quarry", "Old Quarry", "region:east_marches", "An abandoned quarry where pale light leaks from a sealed fissure."),
                ("northern_road", "Northern Road", "region:spinebreaker_mountains", "A muddy trade road marked by broken milestones and fresh hoofprints."),
                ("watchtower", "Old Watchtower", "region:east_marches", "A damaged border tower that still commands the surrounding fields."),
            ]
        rows = list(base)
        while len(rows) < node.target_count:
            index = len(rows) + 1
            rows.append((f"location_{index}", f"Location {index}", "region:market_road", f"A campaign location shaped by pressure {rng.randint(2, 9)}, a local service, and one unresolved secret."))
        entities = []
        facts = []
        documents = []
        for slug, name, region_id, description in rows[: node.target_count]:
            entity_id = f"location:{_slug(slug)}"
            entities.append({"id": entity_id, "name": name, "kind": "location", "region_id": region_id, "dossier_status": "complete", "sensory_profile": description, "visibility": "partially_known"})
            facts.append({"id": f"fact:{_slug(slug)}:location", "content": description, "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "partially_known", "entity_refs": [entity_id, region_id]})
            documents.append(self._document(node, name, description, visibility="partially_known", entity_ids=(entity_id, region_id)))
        return GeneratedTopic(node.topic_id, tuple(documents), tuple(entities), tuple(facts), provenance={"generator": "deterministic_world_forge_v1"})

    def _npcs(
        self,
        node: CampaignTopicNode,
        template: str,
        context: Mapping[str, Any],
        rng: random.Random,
    ) -> GeneratedTopic:
        if "summoned" in template:
            base = [
                {
                    "id": "npc:vexira_umbra",
                    "name": "Vexira Umbra",
                    "appearance": "Unsettlingly beautiful, with dark lacquered-bone skin, crimson lines beneath it, candle-slit eyes, blood-smoke hair, and mirrorsteel armor.",
                    "personality": "Formal, observant, patient, ritual-minded, and cruel with disciplined purpose.",
                    "backstory": "A former Silent Chorus assassin restored by the Unmaker, she has guarded the Vanta Gate for ten years against another premature strike.",
                    "goals": ["protect the Unmaker's return", "humiliate opportunistic summoned heroes"],
                    "motives": ["absolute chosen loyalty", "revenge for the previous Unmaker's death"],
                    "speech_style": "careful measures, quiet formality, blade-like metaphors",
                    "faction_ids": ["faction:silent_chorus"],
                    "location_id": "location:vanta_gate",
                    "secrets": ["She remembers the exact hero who killed the previous Unmaker."],
                    "known_facts": ["fact:hero_system:foundation"],
                },
                {
                    "id": "npc:academy_proctor",
                    "name": "Proctor Ilyan",
                    "appearance": "A silver-robed examiner carrying a chain of ward keys.",
                    "personality": "Precise, skeptical, and protective of untrained summons.",
                    "backstory": "He survived a wild summoning that destroyed an academy annex.",
                    "goals": ["register new heroes safely"],
                    "motives": ["prevent another uncontrolled arrival"],
                    "speech_style": "clinical questions softened by weary courtesy",
                    "faction_ids": ["faction:academy_of_heroes"],
                    "location_id": "location:academy_courtyard",
                    "secrets": [],
                    "known_facts": [],
                },
            ]
        else:
            base = [
                {
                    "id": "npc:bran",
                    "name": "Bran",
                    "appearance": "A broad-shouldered innkeeper with flour on one sleeve and old burn scars across his knuckles.",
                    "personality": "Practical, watchful, dryly kind, and slow to trust grand claims.",
                    "backstory": "Bran inherited the Rusty Flagon after years on caravan roads and still receives reports from drivers he once protected.",
                    "goals": ["keep the Rusty Flagon solvent", "protect travelers who respect the house"],
                    "motives": ["community duty", "fear of losing the tavern"],
                    "speech_style": "plain, economical, lightly sardonic",
                    "faction_ids": ["faction:adventurers_guild"],
                    "location_id": "location:rusty_flagon_tavern",
                    "secrets": ["He knows which caravan failed to return from the old quarry road."],
                    "known_facts": ["fact:current_conflicts:foundation"],
                },
                {
                    "id": "npc:elara",
                    "name": "Elara",
                    "appearance": "A sharp-eyed merchant in a weatherproof blue coat lined with hidden pockets.",
                    "personality": "Quick, ambitious, socially perceptive, and protective of profitable relationships.",
                    "backstory": "Elara built her trade network by moving goods through roads larger houses considered too dangerous.",
                    "goals": ["secure a reliable eastern route"],
                    "motives": ["independence", "commercial leverage"],
                    "speech_style": "fast bargains, precise prices, strategic compliments",
                    "faction_ids": ["faction:merchant_compact"],
                    "location_id": "location:market_district",
                    "secrets": [],
                    "known_facts": [],
                },
                {
                    "id": "npc:captain_aldric",
                    "name": "Captain Aldric",
                    "appearance": "A watch captain in repaired mail with a rain-dark cloak and an unreadable stare.",
                    "personality": "Disciplined, suspicious, fair when evidence is clear, and intolerant of reckless violence.",
                    "backstory": "Aldric rose after exposing a bribed patrol and now trusts records more than reputations.",
                    "goals": ["stabilize the eastern roads"],
                    "motives": ["public duty", "fear of institutional corruption"],
                    "speech_style": "formal questions, exact consequences, no wasted reassurance",
                    "faction_ids": ["faction:northern_watch"],
                    "location_id": "location:market_district",
                    "secrets": [],
                    "known_facts": [],
                },
            ]
        while len(base) < node.target_count:
            index = len(base) + 1
            base.append(
                {
                    "id": f"npc:generated_{index}",
                    "name": f"Generated NPC {index}",
                    "appearance": f"A distinctive traveler carrying token {rng.randint(100, 999)}.",
                    "personality": "Goal-directed, observant, and shaped by a specific local obligation.",
                    "backstory": "Their history connects one faction, one location, and one current conflict.",
                    "goals": [f"resolve obligation {index}"],
                    "motives": ["survival", "belonging"],
                    "speech_style": "specific, concise, and locally grounded",
                    "faction_ids": [],
                    "location_id": "",
                    "secrets": [],
                    "known_facts": [],
                }
            )
        entities = []
        facts = []
        documents = []
        rules = []
        for dossier in base[: node.target_count]:
            row = {**dossier, "kind": "npc", "dossier_status": "complete", "current_emotional_state": "alert", "visibility": "game_master_canon"}
            entities.append(row)
            description = f"{row['appearance']} {row['personality']} {row['backstory']}"
            facts.append({"id": f"fact:{_slug(row['id'])}:dossier", "content": description, "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "game_master_canon", "known_by": [row["id"]], "entity_refs": [row["id"]]})
            for secret_index, secret in enumerate(row.get("secrets") or (), start=1):
                secret_id = f"secret:{_slug(row['id'])}:{secret_index}"
                facts.append({"id": secret_id, "content": secret, "authority": "generated_proposal", "approved_authority": "objective_canon", "visibility": "npc_private", "known_by": [row["id"]], "entity_refs": [row["id"]], "secret_owner_id": row["id"]})
                rules.append({"id": f"acl:{secret_id}", "evidence_id": secret_id, "visibility": "npc_private", "known_by": [row["id"]]})
            documents.append(self._document(node, row["name"], description, visibility="game_master_canon", entity_ids=(row["id"],)))
        return GeneratedTopic(node.topic_id, tuple(documents), tuple(entities), tuple(facts), knowledge_rules=tuple(rules), provenance={"generator": "deterministic_world_forge_v1"})

    def _story_threads(self, node: CampaignTopicNode, template: str) -> GeneratedTopic:
        if "summoned" in template:
            threads = (
                {"id": "thread:vanta_gate_return", "title": "The Vanta Gate Pulses Again", "summary": "Vexira prepares the gate for the Unmaker while rival powers race to intervene.", "actor_ids": ["npc:vexira_umbra"], "location_ids": ["location:vanta_gate"], "faction_ids": ["faction:silent_chorus"], "status": "opening"},
                {"id": "thread:wild_summon", "title": "A Wild Summon", "summary": "An unregistered hero appears where three factions can reach them first.", "actor_ids": [], "location_ids": ["location:academy_courtyard"], "faction_ids": ["faction:academy_of_heroes"], "status": "opening"},
            )
        else:
            threads = (
                {"id": "thread:missing_caravan", "title": "The Missing Caravan", "summary": "A caravan vanished between the East Road and the old quarry.", "actor_ids": ["npc:bran", "npc:elara"], "location_ids": ["location:old_quarry"], "faction_ids": ["faction:merchant_compact"], "status": "opening"},
                {"id": "thread:pale_fissure", "title": "The Pale Fissure", "summary": "Light beneath the quarry suggests a sealed magical rule is failing.", "actor_ids": ["npc:captain_aldric"], "location_ids": ["location:old_quarry"], "faction_ids": ["faction:northern_watch"], "status": "opening"},
            )
        return GeneratedTopic(node.topic_id, story_threads=threads, provenance={"generator": "deterministic_world_forge_v1"})


def _counts(topic: GeneratedTopic) -> dict[str, int]:
    return {
        "documents": len(topic.documents),
        "entities": len(topic.entities),
        "facts": len(topic.facts),
        "relationships": len(topic.relationships),
        "knowledge_rules": len(topic.knowledge_rules),
        "story_threads": len(topic.story_threads),
    }


def generate_campaign_topics(
    graph: CampaignTopicGraph,
    *,
    generator: WorldForgeTopicGenerator | None = None,
    seed: int = 0,
    campaign_context: Mapping[str, Any] | None = None,
    max_parallel_jobs: int = 6,
) -> WorldForgeGenerationResult:
    """Generate independent ready topics in parallel while preserving dependencies."""

    selected_generator = generator or DeterministicWorldForgeGenerator()
    context = dict(campaign_context or {})
    node_map = graph.node_map()
    pending = {
        node.topic_id: set(node.dependencies)
        for node in graph.nodes
        if node.category not in _NON_GENERATION_CATEGORIES
    }
    topics: dict[str, GeneratedTopic] = {}
    jobs: dict[str, WorldForgeJobRecord] = {}
    batches: list[tuple[str, ...]] = []
    workers = max(1, min(int(max_parallel_jobs), 12))
    while pending:
        ready = tuple(sorted(topic_id for topic_id, dependencies in pending.items() if dependencies.issubset(topics)))
        if not ready:
            unresolved = ",".join(sorted(pending))
            raise ValueError(f"World Forge generation dependencies cannot be resolved: {unresolved}")
        batches.append(ready)
        with ThreadPoolExecutor(max_workers=min(workers, len(ready))) as executor:
            futures = {}
            for topic_id in ready:
                node = node_map[topic_id]
                dependencies = {dep: topics[dep] for dep in node.dependencies if dep in topics}
                futures[
                    executor.submit(
                        selected_generator.generate,
                        node,
                        seed=seed,
                        campaign_context=context,
                        dependency_topics=dependencies,
                    )
                ] = node
            for future in as_completed(futures):
                node = futures[future]
                try:
                    topic = future.result()
                    if topic.topic_id != node.topic_id:
                        raise ValueError(f"generator returned {topic.topic_id} for {node.topic_id}")
                    topics[node.topic_id] = topic
                    jobs[node.topic_id] = WorldForgeJobRecord(
                        topic_id=node.topic_id,
                        status="completed",
                        dependency_ids=node.dependencies,
                        generator_role=node.generator_role,
                        output_counts=_counts(topic),
                    )
                except Exception as exc:  # deterministic error envelope
                    jobs[node.topic_id] = WorldForgeJobRecord(
                        topic_id=node.topic_id,
                        status="failed",
                        dependency_ids=node.dependencies,
                        generator_role=node.generator_role,
                        error=str(exc),
                    )
        for topic_id in ready:
            pending.pop(topic_id, None)
        failed = {topic_id for topic_id in ready if topic_id not in topics}
        if failed:
            for topic_id, dependencies in list(pending.items()):
                if dependencies.intersection(failed):
                    jobs[topic_id] = WorldForgeJobRecord(
                        topic_id=topic_id,
                        status="blocked",
                        dependency_ids=node_map[topic_id].dependencies,
                        generator_role=node_map[topic_id].generator_role,
                        error="dependency_failed",
                    )
                    pending.pop(topic_id)
            break
    ordered_topics = tuple(topics[node.topic_id] for node in graph.topological_order() if node.topic_id in topics)
    ordered_jobs = tuple(jobs[topic_id] for topic_id in sorted(jobs))
    failed_ids = tuple(sorted(job.topic_id for job in ordered_jobs if job.status != "completed"))
    return WorldForgeGenerationResult(ordered_topics, ordered_jobs, failed_ids, tuple(batches))
