from __future__ import annotations

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

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
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


def validate_adventure_setup_payload(payload: dict) -> ValidationResult:
    """Run all validation checks and return a structured result."""
    all_issues: list[ValidationIssue] = []
    all_issues.extend(validate_setup_required_fields(payload))
    all_issues.extend(validate_setup_ids(payload))
    all_issues.extend(validate_setup_balances(payload))
    all_issues.extend(validate_setup_cross_references(payload))
    has_errors = any(i.severity == "error" for i in all_issues)
    return ValidationResult(valid=not has_errors, issues=all_issues)
