from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class ValidationIssue:
    """A single validation problem, shaped for frontend consumption."""

    path: str
    code: str
    message: str
    severity: str = "error"  # "error" | "warning" | "info"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationIssue":
        return cls(
            path=data["path"],
            code=data["code"],
            message=data["message"],
            severity=data.get("severity", "error"),
        )


@dataclass
class ValidationResult:
    """Aggregated validation result with structured issues."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def is_blocking(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "blocking": self.is_blocking(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationResult":
        return cls(
            valid=data["valid"],
            issues=[ValidationIssue.from_dict(i) for i in data.get("issues", [])],
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("setup_id", "title", "genre", "setting", "premise")


def validate_setup_ids(payload: dict) -> list[ValidationIssue]:
    """Check for duplicate ids among NPCs, factions, and locations."""
    issues: list[ValidationIssue] = []

    seen_npcs: set[str] = set()
    for idx, npc in enumerate(payload.get("npc_seeds", [])):
        npc_id = npc.get("npc_id", "")
        if not npc_id:
            issues.append(
                ValidationIssue(
                    path=f"npc_seeds[{idx}].npc_id",
                    code="missing_id",
                    message="NPC seed is missing npc_id",
                )
            )
        elif npc_id in seen_npcs:
            issues.append(
                ValidationIssue(
                    path=f"npc_seeds[{idx}].npc_id",
                    code="duplicate_id",
                    message=f"Duplicate npc_id: {npc_id}",
                )
            )
        else:
            seen_npcs.add(npc_id)

    seen_factions: set[str] = set()
    for idx, faction in enumerate(payload.get("factions", [])):
        faction_id = faction.get("faction_id", "")
        if not faction_id:
            issues.append(
                ValidationIssue(
                    path=f"factions[{idx}].faction_id",
                    code="missing_id",
                    message="Faction seed is missing faction_id",
                )
            )
        elif faction_id in seen_factions:
            issues.append(
                ValidationIssue(
                    path=f"factions[{idx}].faction_id",
                    code="duplicate_id",
                    message=f"Duplicate faction_id: {faction_id}",
                )
            )
        else:
            seen_factions.add(faction_id)

    seen_locations: set[str] = set()
    for idx, location in enumerate(payload.get("locations", [])):
        location_id = location.get("location_id", "")
        if not location_id:
            issues.append(
                ValidationIssue(
                    path=f"locations[{idx}].location_id",
                    code="missing_id",
                    message="Location seed is missing location_id",
                )
            )
        elif location_id in seen_locations:
            issues.append(
                ValidationIssue(
                    path=f"locations[{idx}].location_id",
                    code="duplicate_id",
                    message=f"Duplicate location_id: {location_id}",
                )
            )
        else:
            seen_locations.add(location_id)

    return issues


def validate_setup_required_fields(payload: dict) -> list[ValidationIssue]:
    """Ensure required top-level string fields are present and non-empty."""
    issues: list[ValidationIssue] = []
    for field_name in _REQUIRED_FIELDS:
        val = payload.get(field_name)
        if not val or (isinstance(val, str) and not val.strip()):
            issues.append(
                ValidationIssue(
                    path=field_name,
                    code="required",
                    message=f"'{field_name}' is required and must be non-empty",
                )
            )
    return issues


def validate_setup_balances(payload: dict) -> list[ValidationIssue]:
    """Validate that content-balance weights are in [0, 1] and sum ≈ 1."""
    issues: list[ValidationIssue] = []
    cb = payload.get("content_balance")
    if cb is None:
        return issues

    balance_fields = ("mystery", "combat", "politics", "exploration", "social")
    total = 0.0
    for bf in balance_fields:
        val = cb.get(bf)
        if val is None:
            continue
        if not isinstance(val, (int, float)):
            issues.append(
                ValidationIssue(
                    path=f"content_balance.{bf}",
                    code="invalid_type",
                    message=f"content_balance.{bf} must be a number",
                )
            )
            continue
        if val < 0 or val > 1:
            issues.append(
                ValidationIssue(
                    path=f"content_balance.{bf}",
                    code="out_of_range",
                    message=f"content_balance.{bf} must be between 0 and 1",
                    severity="warning",
                )
            )
        total += val

    if total > 0 and abs(total - 1.0) > 0.05:
        issues.append(
            ValidationIssue(
                path="content_balance",
                code="balance_sum",
                message=f"Content balance weights sum to {total:.2f}, expected ~1.0",
                severity="warning",
            )
        )
    return issues


def validate_setup_cross_references(payload: dict) -> list[ValidationIssue]:
    """Check that NPC faction/location references point to valid ids."""
    issues: list[ValidationIssue] = []

    faction_ids = {f.get("faction_id") for f in payload.get("factions", [])}
    location_ids = {loc.get("location_id") for loc in payload.get("locations", [])}
    npc_ids = {n.get("npc_id") for n in payload.get("npc_seeds", [])}

    for idx, npc in enumerate(payload.get("npc_seeds", [])):
        fid = npc.get("faction_id")
        if fid and fid not in faction_ids:
            issues.append(
                ValidationIssue(
                    path=f"npc_seeds[{idx}].faction_id",
                    code="dangling_ref",
                    message=f"NPC '{npc.get('npc_id', '')}' references unknown faction '{fid}'",
                    severity="warning",
                )
            )
        lid = npc.get("location_id")
        if lid and lid not in location_ids:
            issues.append(
                ValidationIssue(
                    path=f"npc_seeds[{idx}].location_id",
                    code="dangling_ref",
                    message=f"NPC '{npc.get('npc_id', '')}' references unknown location '{lid}'",
                    severity="warning",
                )
            )

    starting_npc_ids = payload.get("starting_npc_ids", [])
    for idx, snid in enumerate(starting_npc_ids):
        if snid not in npc_ids:
            issues.append(
                ValidationIssue(
                    path=f"starting_npc_ids[{idx}]",
                    code="dangling_ref",
                    message=f"starting_npc_ids references unknown NPC '{snid}'",
                    severity="warning",
                )
            )

    starting_location = payload.get("starting_location_id")
    if starting_location and starting_location not in location_ids:
        issues.append(
            ValidationIssue(
                path="starting_location_id",
                code="dangling_ref",
                message=f"starting_location_id references unknown location '{starting_location}'",
                severity="warning",
            )
        )

    return issues


def validate_setup_ux_hints(payload: dict) -> list[ValidationIssue]:
    """UX-helpful warnings that guide the creator but never block launch."""
    issues: list[ValidationIssue] = []

    locations = payload.get("locations", [])
    npc_seeds = payload.get("npc_seeds", [])
    starting_npc_ids = payload.get("starting_npc_ids", [])
    starting_location_id = payload.get("starting_location_id")

    # Warn if zero locations defined
    if not locations:
        issues.append(
            ValidationIssue(
                path="locations",
                code="no_locations",
                message="No locations defined — the engine will generate a default starting area",
                severity="warning",
            )
        )

    # Warn if zero NPCs defined
    if not npc_seeds:
        issues.append(
            ValidationIssue(
                path="npc_seeds",
                code="no_npcs",
                message="No NPCs defined — the adventure will start with no pre-defined characters",
                severity="warning",
            )
        )

    # Warn if premise is too short
    premise = payload.get("premise", "")
    if premise and len(premise.strip()) < 20:
        issues.append(
            ValidationIssue(
                path="premise",
                code="short_premise",
                message="Premise is very short — consider adding more detail for a richer opening",
                severity="warning",
            )
        )

    # Warn if title equals setting exactly
    title = payload.get("title", "")
    setting = payload.get("setting", "")
    if title and setting and title.strip().lower() == setting.strip().lower():
        issues.append(
            ValidationIssue(
                path="title",
                code="title_equals_setting",
                message="Title is identical to setting — consider making them distinct",
                severity="warning",
            )
        )

    # Warn if too many starting NPCs selected
    if len(starting_npc_ids) > 5:
        issues.append(
            ValidationIssue(
                path="starting_npc_ids",
                code="too_many_starting_npcs",
                message=f"{len(starting_npc_ids)} starting NPCs selected — consider fewer for a focused opening",
                severity="warning",
            )
        )

    # Warn if no starting location but locations exist
    if locations and not starting_location_id:
        issues.append(
            ValidationIssue(
                path="starting_location_id",
                code="no_starting_location",
                message="Locations are defined but no starting location is selected — the first location will be used",
                severity="info",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Semantic validation helpers (pure, deterministic, no LLM)
# ---------------------------------------------------------------------------

_GENERIC_NPC_NAMES = frozenset({
    "guard", "merchant", "villager", "soldier", "innkeeper", "farmer",
    "thief", "bandit", "knight", "priest", "healer", "stranger",
    "traveler", "elder", "scout", "warrior", "mage", "wizard",
    "captain", "chief", "leader", "shopkeeper", "bartender", "smith",
    "npc", "enemy", "ally", "boss", "minion", "servant",
})

_GENERIC_FACTION_NAMES = frozenset({
    "faction", "group", "guild", "order", "clan", "tribe",
    "the good guys", "the bad guys", "enemies", "allies",
    "team a", "team b", "faction 1", "faction 2",
})


def _text_strength(text: str) -> float:
    """Score text quality 0.0 to 1.0 based on length, word count, specificity."""
    if not text or not text.strip():
        return 0.0
    cleaned = text.strip()
    length = len(cleaned)
    words = cleaned.split()
    word_count = len(words)

    # Length score: ramp up to 1.0 at 200+ chars
    length_score = min(length / 200.0, 1.0)
    # Word count score: ramp up to 1.0 at 30+ words
    word_score = min(word_count / 30.0, 1.0)
    # Unique-word ratio as proxy for specificity (penalize repetition)
    unique_ratio = len(set(w.lower() for w in words)) / max(word_count, 1)

    return round(0.4 * length_score + 0.35 * word_score + 0.25 * unique_ratio, 3)


def _looks_generic_name(name: str) -> bool:
    """Return True if name looks like a placeholder (Guard, Merchant, etc.)."""
    if not name or not name.strip():
        return True
    cleaned = name.strip().lower()
    if cleaned in _GENERIC_NPC_NAMES or cleaned in _GENERIC_FACTION_NAMES:
        return True
    # Check for numbered placeholders like "Guard 1", "NPC_2"
    if re.match(r"^(npc|guard|merchant|enemy|faction|group)[\s_\-]*\d*$", cleaned):
        return True
    return False


def _entity_description_strength(entity: dict) -> float:
    """Score entity description quality 0.0 to 1.0."""
    desc = entity.get("description", "")
    name = entity.get("name", "")
    # Start from text strength of description
    score = _text_strength(desc)
    # Penalize if name is generic
    if _looks_generic_name(name):
        score *= 0.5
    return round(score, 3)


def _opening_is_actionable(opening: dict) -> bool:
    """Return True if opening has enough substance to create a good start."""
    if not opening or not isinstance(opening, dict):
        return False
    hook = opening.get("opening_hook", "")
    conflict = opening.get("starter_conflict", "")
    scene = opening.get("scene_frame", "")
    # Need at least a hook or conflict with some substance
    has_hook = bool(hook and len(hook.strip()) >= 10)
    has_conflict = bool(conflict and len(conflict.strip()) >= 10)
    has_scene = bool(scene and len(scene.strip()) >= 10)
    # Actionable if at least two of the three are present
    return sum([has_hook, has_conflict, has_scene]) >= 2


def _compute_seed_cohesion(setup: dict) -> float:
    """Score how well seeds relate to each other and to the premise/objective.

    Uses word-overlap heuristics between premise, objective, and entity
    descriptions as a proxy for thematic cohesion.
    """
    premise = setup.get("premise", "")
    objective = setup.get("campaign_objective", "")
    hook = setup.get("opening_hook", "")
    core_text = f"{premise} {objective} {hook}".lower().split()
    if not core_text:
        return 0.0

    # Build a set of "core" words (skip short words)
    core_words = {w for w in core_text if len(w) > 3}
    if not core_words:
        return 0.5  # No meaningful core words to compare

    entity_texts: list[str] = []
    for npc in setup.get("npc_seeds", []):
        entity_texts.append(npc.get("description", ""))
        entity_texts.append(npc.get("name", ""))
    for faction in setup.get("factions", []):
        entity_texts.append(faction.get("description", ""))
        entity_texts.append(faction.get("name", ""))
    for loc in setup.get("locations", []):
        entity_texts.append(loc.get("description", ""))
        entity_texts.append(loc.get("name", ""))

    if not entity_texts or all(not t for t in entity_texts):
        return 0.0

    # Compute overlap: fraction of entities that share words with core text
    entity_hits = 0
    total_entities = 0
    for text in entity_texts:
        if not text:
            continue
        total_entities += 1
        words = {w.lower() for w in text.split() if len(w) > 3}
        if words & core_words:
            entity_hits += 1

    if total_entities == 0:
        return 0.0
    return round(entity_hits / total_entities, 3)


def validate_adventure_setup_semantics(setup: dict) -> dict:
    """Second-layer semantic validation that produces warnings, not blocking errors.

    Returns::

        {
            "warnings": [...],    # list of ValidationIssue dicts
            "notices": [...],     # list of ValidationIssue dicts
            "scores": {
                "premise_strength": 0.0-1.0,
                "opening_clarity": 0.0-1.0,
                "seed_cohesion": 0.0-1.0,
                "player_hook_strength": 0.0-1.0,
            }
        }
    """
    warnings: list[dict] = []
    notices: list[dict] = []

    # --- Scores ---
    premise = setup.get("premise", "")
    objective = setup.get("campaign_objective", "")
    opening_hook = setup.get("opening_hook", "")
    starter_conflict = setup.get("starter_conflict", "")

    premise_strength = _text_strength(premise)
    hook_strength = _text_strength(opening_hook)
    conflict_strength = _text_strength(starter_conflict)
    objective_strength = _text_strength(objective)

    opening_clarity = round(
        0.4 * hook_strength + 0.35 * conflict_strength + 0.25 * _text_strength(
            setup.get("scene_frame", "")
        ),
        3,
    )

    player_hook_strength = round(
        0.4 * hook_strength + 0.3 * objective_strength + 0.3 * _text_strength(
            setup.get("player_background", "")
        ),
        3,
    )

    seed_cohesion = _compute_seed_cohesion(setup)

    scores = {
        "premise_strength": premise_strength,
        "opening_clarity": opening_clarity,
        "seed_cohesion": seed_cohesion,
        "player_hook_strength": player_hook_strength,
    }

    # --- 1. Weak premise ---
    if premise_strength < 0.3:
        warnings.append(ValidationIssue(
            path="premise",
            code="weak_premise",
            message="Premise is thin — a richer premise helps the engine create a stronger world",
            severity="warning",
        ).to_dict())
    if not objective or not objective.strip():
        notices.append(ValidationIssue(
            path="campaign_objective",
            code="empty_objective",
            message="No campaign objective set — the engine will infer one from the premise",
            severity="info",
        ).to_dict())
    if not opening_hook or not opening_hook.strip():
        notices.append(ValidationIssue(
            path="opening_hook",
            code="empty_opening_hook",
            message="No opening hook — consider adding one to draw players in immediately",
            severity="info",
        ).to_dict())

    # --- 2. No actionable opening ---
    opening_dict = {
        "opening_hook": opening_hook,
        "starter_conflict": starter_conflict,
        "scene_frame": setup.get("scene_frame", ""),
    }
    if not _opening_is_actionable(opening_dict):
        warnings.append(ValidationIssue(
            path="opening_hook",
            code="no_actionable_opening",
            message="Opening lacks substance — add a hook, conflict, or scene frame so players have something to act on",
            severity="warning",
        ).to_dict())

    # --- 3. Generic factions/NPCs ---
    npc_seeds = setup.get("npc_seeds", [])
    factions = setup.get("factions", [])

    npc_names_seen: list[str] = []
    for idx, npc in enumerate(npc_seeds):
        name = npc.get("name", "")
        if _looks_generic_name(name):
            warnings.append(ValidationIssue(
                path=f"npc_seeds[{idx}].name",
                code="generic_npc_name",
                message=f"NPC name '{name}' looks generic — a unique name adds personality",
                severity="warning",
            ).to_dict())
        if _entity_description_strength(npc) < 0.15:
            notices.append(ValidationIssue(
                path=f"npc_seeds[{idx}].description",
                code="weak_npc_description",
                message=f"NPC '{name}' has a thin description — more detail helps the engine portray them",
                severity="info",
            ).to_dict())
        npc_names_seen.append(name.strip().lower())

    # Check for duplicate NPC labels
    if len(npc_names_seen) != len(set(npc_names_seen)):
        seen: set[str] = set()
        for idx, n in enumerate(npc_names_seen):
            if n and n in seen:
                warnings.append(ValidationIssue(
                    path=f"npc_seeds[{idx}].name",
                    code="duplicate_npc_name",
                    message=f"Multiple NPCs share the name '{npc_seeds[idx].get('name', '')}' — consider differentiating",
                    severity="warning",
                ).to_dict())
            seen.add(n)

    faction_names_seen: list[str] = []
    for idx, faction in enumerate(factions):
        name = faction.get("name", "")
        if _looks_generic_name(name):
            warnings.append(ValidationIssue(
                path=f"factions[{idx}].name",
                code="generic_faction_name",
                message=f"Faction name '{name}' looks generic — a distinctive name makes the world richer",
                severity="warning",
            ).to_dict())
        if _entity_description_strength(faction) < 0.15:
            notices.append(ValidationIssue(
                path=f"factions[{idx}].description",
                code="weak_faction_description",
                message=f"Faction '{name}' has a thin description — more detail helps define their role",
                severity="info",
            ).to_dict())
        faction_names_seen.append(name.strip().lower())

    if len(faction_names_seen) != len(set(faction_names_seen)):
        seen_f: set[str] = set()
        for idx, n in enumerate(faction_names_seen):
            if n and n in seen_f:
                warnings.append(ValidationIssue(
                    path=f"factions[{idx}].name",
                    code="duplicate_faction_name",
                    message=f"Multiple factions share the name '{factions[idx].get('name', '')}' — consider differentiating",
                    severity="warning",
                ).to_dict())
            seen_f.add(n)

    # --- 4. Contradictory canon/rules ---
    forbidden_content = {t.strip().lower() for t in setup.get("forbidden_content", []) if t}
    allowed_tone = {t.strip().lower() for t in setup.get("allowed_tone", []) if t}
    core_world_laws = [w.strip().lower() for w in setup.get("core_world_laws", []) if w]
    genre_rules = [r.strip().lower() for r in setup.get("genre_rules", []) if r]

    tone_conflict = forbidden_content & allowed_tone
    if tone_conflict:
        for item in tone_conflict:
            warnings.append(ValidationIssue(
                path="forbidden_content",
                code="tone_conflict",
                message=f"'{item}' appears in both forbidden_content and allowed_tone — this is contradictory",
                severity="warning",
            ).to_dict())

    # Check world laws vs genre rules for obvious contradictions
    for law in core_world_laws:
        for rule in genre_rules:
            # Simple negation detection
            if (law.startswith("no ") and law[3:] in rule) or \
               (rule.startswith("no ") and rule[3:] in law):
                warnings.append(ValidationIssue(
                    path="core_world_laws",
                    code="law_rule_conflict",
                    message=f"World law '{law}' may conflict with genre rule '{rule}'",
                    severity="warning",
                ).to_dict())

    # --- 5. Disconnected starting NPCs/location ---
    starting_npc_ids = set(setup.get("starting_npc_ids", []))
    starting_location_id = setup.get("starting_location_id", "")
    locations = setup.get("locations", [])

    if starting_npc_ids and starting_location_id:
        for idx, npc in enumerate(npc_seeds):
            npc_id = npc.get("npc_id", "")
            if npc_id in starting_npc_ids:
                npc_loc = npc.get("location_id", "")
                if npc_loc and npc_loc != starting_location_id:
                    notices.append(ValidationIssue(
                        path=f"npc_seeds[{idx}].location_id",
                        code="starting_npc_elsewhere",
                        message=(
                            f"Starting NPC '{npc.get('name', npc_id)}' is assigned to "
                            f"location '{npc_loc}', not the starting location '{starting_location_id}'"
                        ),
                        severity="info",
                    ).to_dict())

    if starting_location_id and locations:
        location_ids = {loc.get("location_id") for loc in locations}
        if starting_location_id not in location_ids:
            warnings.append(ValidationIssue(
                path="starting_location_id",
                code="starting_location_unreferenced",
                message=f"Starting location '{starting_location_id}' is not in the locations list",
                severity="warning",
            ).to_dict())

    # --- 6. Too many seeds / no center ---
    total_seeds = len(npc_seeds) + len(factions) + len(locations)
    if total_seeds > 15 and premise_strength < 0.4:
        warnings.append(ValidationIssue(
            path="premise",
            code="seeds_without_focus",
            message=(
                f"{total_seeds} seeds defined but premise is weak — "
                "consider strengthening the premise to tie everything together"
            ),
            severity="warning",
        ).to_dict())

    if total_seeds > 0 and not starter_conflict and not opening_hook:
        notices.append(ValidationIssue(
            path="starter_conflict",
            code="no_central_conflict",
            message="Seeds are defined but there is no starter conflict or opening hook to unify them",
            severity="info",
        ).to_dict())

    if seed_cohesion < 0.2 and total_seeds > 5:
        warnings.append(ValidationIssue(
            path="premise",
            code="low_cohesion",
            message="Seeds seem disconnected from the premise — consider aligning descriptions with the central theme",
            severity="warning",
        ).to_dict())

    return {
        "warnings": warnings,
        "notices": notices,
        "scores": scores,
    }


def validate_adventure_setup_payload(payload: dict) -> ValidationResult:
    """Run all validation checks and return a structured result."""
    all_issues: list[ValidationIssue] = []
    all_issues.extend(validate_setup_required_fields(payload))
    all_issues.extend(validate_setup_ids(payload))
    all_issues.extend(validate_setup_balances(payload))
    all_issues.extend(validate_setup_cross_references(payload))
    all_issues.extend(validate_setup_ux_hints(payload))
    return ValidationResult(issues=all_issues)
