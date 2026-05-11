from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from app.rpg.ai.grounding_settings import normalize_grounding_settings


_MONEY_AMOUNT_PATTERN = (
    r"(?:"
    r"\d+(?:,\d{3})*(?:\.\d+)?"
    r"|"
    r"a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|half|quarter|couple|few|several"
    r"(?:[-\s]+(?:and\s+)?(?:a\s+)?(?:half|quarter))?"
    r")"
)

_CURRENCY_UNIT_PATTERN = (
    r"(?:"
    r"gold|silver|copper|coin|coins|gp|sp|cp|"
    r"gold\s+piece|gold\s+pieces|"
    r"silver\s+piece|silver\s+pieces|"
    r"copper\s+piece|copper\s+pieces"
    r")"
)

_MONEY_PHRASE_PATTERN = rf"{_MONEY_AMOUNT_PATTERN}\s*{_CURRENCY_UNIT_PATTERN}"

_PRICE_CONTEXT_PATTERN = (
    r"(?:"
    r"costs?|price|priced|rate|fee|charge|fare|toll|rent|"
    r"listed\s+at|goes\s+for|runs?|comes\s+to|"
    r"that(?:'ll| will)\s+be|that\s+is|that's|"
    r"it(?:'ll| will)\s+be|it\s+is|it's|"
    r"you(?:'ll| will)\s+need\s+to\s+pay|"
    r"pay|"
    r"for"
    r")"
)

_SERVICE_CONTEXT_PATTERN = (
    r"(?:"
    r"cot|bed|room|chamber|lodging|stay|night|meal|drink|ale|wine|"
    r"service|stabling|stable|horse|supplies|ration|rations|repair|"
    r"weapon|armor|armour|item|goods|wares|passage|ride|cart|boat|ferry"
    r")"
)

_PRICE_QUOTE_PATTERNS = [
    # "costs 50 silver", "price is 1,200 gold", "that'll be 3 gp"
    rf"\b{_PRICE_CONTEXT_PATTERN}\s+(?:is\s+|at\s+|of\s+|about\s+|around\s+|just\s+)?{_MONEY_PHRASE_PATTERN}\b",

    # "5 silver per night", "3 gp each", "10 copper for the meal"
    rf"\b{_MONEY_PHRASE_PATTERN}\s+(?:per|each|for|a|an|the)\s+\w+\b",

    # "a room is 5 silver", "lodging runs 2 gold", "the cot costs 3 sp"
    rf"\b(?:the\s+)?{_SERVICE_CONTEXT_PATTERN}\s+(?:is|are|costs?|runs?|goes\s+for|comes\s+to)\s+{_MONEY_PHRASE_PATTERN}\b",

    # "for 5 silver", "for one gold", useful for merchant/service wording.
    rf"\bfor\s+(?:just\s+|only\s+|about\s+|around\s+)?{_MONEY_PHRASE_PATTERN}\b",

    # "5 silver cot", "one gold room" as a noun phrase.
    rf"\b{_MONEY_PHRASE_PATTERN}\s+{_SERVICE_CONTEXT_PATTERN}\b",
]

_REWARD_PATTERNS = [
    rf"\b{_MONEY_PHRASE_PATTERN}\b",
    r"\bgain(?:ed|s)?\b.*\b(gold|silver|copper|coin|coins|xp|experience)\b",
    r"\breceiv(?:e|ed|es)\b.*\b(gold|silver|copper|coin|coins|xp|experience)\b",
    r"\breward(?:ed)?\b",
    r"\badds?\b.*\bto your inventory\b",
    r"\bhand(?:s|ed)?\b.*\b(gold|silver|copper|coin|coins)\b",
]

_COMBAT_PATTERNS = [
    r"\bkill(?:ed|s)?\b",
    r"\bslay(?:s|ing|ed)?\b",
    r"\bdie(?:s|d)?\b",
    r"\bdead\b",
    r"\bdeath\b",
    r"\bwound(?:ed|s)?\b",
    r"\binjur(?:y|ed|es)\b",
    r"\bdamage(?:d|s)?\b",
    r"\bbleed(?:s|ing)?\b",
    r"\bblood\b",
    r"\bbloodshed\b",
    r"\battack(?:ed|s)?\b",
    r"\bcombat\b",
]

_OBJECTIVE_COMPLETION_PATTERNS = [
    r"\bcomplete(?:d|s)?\b.*\bobjective\b",
    r"\bquest\b.*\bcomplete(?:d|s)?\b",
    r"\bmission\b.*\bcomplete(?:d|s)?\b",
    r"\bresolved\b.*\bquest\b",
]

_LOCATION_MOVE_PATTERNS = [
    r"\byou arrive at\b",
    r"\byou reach\b",
    r"\byou travel to\b",
    r"\byou enter\b",
    r"\byou leave for\b",
]

_UNSUPPORTED_DEBT_CLAIM_PATTERNS = [
    r"\byou\s+owe\s+me\b",
    r"\byou\s+owed\s+me\b",
    r"\bowe\s+me\s+(?:money|coin|coins|gold|silver|copper|payment|debt)\b",
    r"\bpay\s+me\b",
    r"\bpay\s+what\s+you\s+owe\b",
    r"\bsettle\s+(?:your\s+)?debt\b",
    r"\bdebt\b.*\b(?:pay|owed|owe|coin|gold|silver|copper)\b",
]

_CLEAR_DEBT_REFUSAL_PATTERNS = [
    r"\bdo\s+not\s+owe\b",
    r"\bdon't\s+owe\b",
    r"\bdoes\s+not\s+owe\b",
    r"\bnot\s+owe\b",
]

_AMBIGUOUS_DEBT_RESPONSE_PATTERNS = [
    r"\bfifty\s+gold\?\b",
    r"\b\d+\s*(?:gold|silver|copper|coin|coins|gp|sp|cp)\?\b",
    r"\byou'?re\s+sure\s+about\s+that\b",
    r"\bare\s+you\s+sure\b",
    r"\bpay\s+me\s+now\?\b",
    r"\blet\s+me\s+think\s+about\s+what\s+i\s+owe\b",
    r"\bwhat\s+i\s+owe\s+you\b",
    r"\bconsider(?:ing)?\s+(?:the\s+)?debt\b",
    r"\bunder\s+discussion\b",
    r"\bwe'?ll\s+see\b",
    r"\bmaybe\b",
    r"\bperhaps\b",
]

_NEGATION_MARKERS = (
    " no ",
    " not ",
    " without ",
    " does not ",
    " do not ",
    " did not ",
    " never ",
    " cannot ",
    " can't ",
)


@dataclass
class GroundingViolation:
    code: str
    message: str
    field: str = ""
    evidence: str = ""


@dataclass
class GroundingValidationResult:
    ok: bool
    violations: List[GroundingViolation] = field(default_factory=list)
    fallback_used: bool = False
    fallback_source: str = ""
    selected_candidate: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "fallback_used": bool(self.fallback_used),
            "fallback_source": self.fallback_source,
            "selected_candidate": self.selected_candidate,
            "violations": [
                {
                    "code": v.code,
                    "message": v.message,
                    "field": v.field,
                    "evidence": v.evidence,
                }
                for v in self.violations
            ],
        }


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_flatten_text(v) for v in value)
    return _safe_str(value)


def _contains_pattern(text: str, patterns: Iterable[str]) -> Optional[str]:
    text = _safe_str(text)
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = f" {_safe_str(text[max(0, match.start() - 32) : match.start()]).lower()} "
            if any(marker in prefix for marker in _NEGATION_MARKERS):
                continue
            return pattern
    return None


def _contains_price_quote(text: str) -> bool:
    text = _safe_str(text)
    for pattern in _PRICE_QUOTE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _ids_from_entries(entries: Any) -> Set[str]:
    ids: Set[str] = set()
    for entry in _safe_list(entries):
        if isinstance(entry, str):
            ids.add(entry.strip())
        elif isinstance(entry, Mapping):
            for key in (
                "id",
                "name",
                "label",
                "npc",
                "speaker",
                "location",
                "item",
                "objective",
                "quest",
                "node_id",
            ):
                value = entry.get(key)
                if value:
                    ids.add(_safe_str(value).strip())
    return {value for value in ids if value}


def _texts_from_entries(entries: Any) -> List[str]:
    texts: List[str] = []
    for entry in _safe_list(entries):
        if isinstance(entry, str):
            texts.append(entry)
        elif isinstance(entry, Mapping):
            for key in ("text", "summary", "title", "name", "label", "description", "command"):
                value = entry.get(key)
                if value:
                    texts.append(_safe_str(value))
    return [text for text in texts if text]


def _extract_allowed_fact_texts(turn_contract: Mapping[str, Any]) -> List[str]:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )
    texts: List[str] = []

    for source in (contract, result):
        for key in (
            "new_facts",
            "facts",
            "allowed_facts",
            "known_facts",
            "unlocked_facts",
            "new_leads",
            "allowed_leads",
            "suggested_actions",
            "allowed_next_actions",
        ):
            value = source.get(key)
            if isinstance(value, Mapping):
                texts.extend(_safe_str(k) for k in value.keys())
                texts.extend(_texts_from_entries(value.values()))
            else:
                texts.extend(_texts_from_entries(value))

    narration_brief = _safe_dict(contract.get("narration_brief"))
    texts.extend(_texts_from_entries([narration_brief]))
    return [text for text in texts if text]


def _extract_allowed_ids(turn_contract: Mapping[str, Any], *keys: str) -> Set[str]:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )
    ids: Set[str] = set()

    for source in (contract, result):
        for key in keys:
            value = source.get(key)
            if isinstance(value, Mapping):
                ids.update(_safe_str(k).strip() for k in value.keys())
                ids.update(_ids_from_entries(value.values()))
            else:
                ids.update(_ids_from_entries(value))
    return {value for value in ids if value}


def _delta_exists(turn_contract: Mapping[str, Any], keys: Sequence[str]) -> bool:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )
    state_delta = _safe_dict(contract.get("state_delta"))

    for source in (contract, result, state_delta):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", {}, []):
                return True
    return False


def _currency_or_inventory_delta_exists(turn_contract: Mapping[str, Any]) -> bool:
    return _delta_exists(
        turn_contract,
        (
            "currency_delta",
            "currency",
            "money_delta",
            "reward",
            "inventory_delta",
            "items_added",
            "items_removed",
            "xp_result",
            "skill_xp_result",
            "level_up",
        ),
    )


def _combat_delta_exists(turn_contract: Mapping[str, Any]) -> bool:
    return _delta_exists(
        turn_contract,
        (
            "combat_delta",
            "damage_delta",
            "health_delta",
            "defeat",
            "combat",
            "combat_result",
            "npc_combat_result",
        ),
    )


def _quest_completion_exists(turn_contract: Mapping[str, Any]) -> bool:
    return _delta_exists(
        turn_contract,
        (
            "completed_quests",
            "quest_completed",
            "complete_quest",
            "completed_objectives",
            "objective_completed",
            "quest_log_delta",
            "quest_result",
        ),
    )


def _payment_or_debt_authorized(turn_contract: Mapping[str, Any]) -> bool:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )

    candidates = [
        contract,
        result,
        _safe_dict(contract.get("service_result")),
        _safe_dict(contract.get("interaction_result")),
        _safe_dict(contract.get("conversation_result")),
        _safe_dict(contract.get("npc_backbone_decision")),
        _safe_dict(contract.get("state_delta")),
        _safe_dict(result.get("service_result")),
        _safe_dict(result.get("interaction_result")),
        _safe_dict(result.get("conversation_result")),
        _safe_dict(result.get("npc_backbone_decision")),
        _safe_dict(result.get("state_delta")),
    ]

    for source in candidates:
        if not source:
            continue

        for key in (
            "currency_delta",
            "money_delta",
            "reward",
            "payment",
            "payment_due",
            "debt",
            "debt_confirmed",
            "owed_amount",
            "inventory_delta",
            "items_added",
        ):
            if source.get(key) not in (None, "", {}, []):
                return True

        if source.get("accepted") is True and (
            source.get("service_id")
            or source.get("service")
            or source.get("price")
            or source.get("cost")
        ):
            return True

    return False


def _allowed_speakers(
    turn_contract: Mapping[str, Any],
    state_snapshot: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    state = _safe_dict(state_snapshot)
    allowed: Set[str] = set()

    allowed.update(
        _extract_allowed_ids(turn_contract, "allowed_npcs", "present_npcs", "known_npcs", "unlocked_npcs", "npcs")
    )
    allowed.update(
        _extract_allowed_ids(state, "present_npcs", "known_npcs", "unlocked_npcs", "npcs")
    )

    for source in (_safe_dict(turn_contract), state):
        for key in ("speaker", "npc_speaker", "target_id", "target_name", "npc_name", "speaker_name"):
            value = source.get(key)
            if value:
                allowed.add(_safe_str(value).strip())

    return {value for value in allowed if value}


def _speaker_allowed(speaker: str, allowed: Set[str]) -> bool:
    speaker = _safe_str(speaker).strip()
    if not speaker:
        return True
    allowed_lower = {value.lower() for value in allowed}
    if speaker.lower() in allowed_lower:
        return True
    slug = speaker.lower().replace(" ", "_")
    return any(value.lower().endswith(slug) for value in allowed)


def _allowed_locations(
    turn_contract: Mapping[str, Any],
    state_snapshot: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    contract = _safe_dict(turn_contract)
    state = _safe_dict(state_snapshot)
    allowed: Set[str] = set()

    allowed.update(_extract_allowed_ids(contract, "allowed_locations", "unlocked_locations", "locations"))
    allowed.update(_extract_allowed_ids(state, "allowed_locations", "unlocked_locations", "locations"))

    for source in (contract, state):
        for key in (
            "location",
            "current_location",
            "current_location_id",
            "new_location",
            "set_location",
            "location_name",
        ):
            value = source.get(key)
            if isinstance(value, Mapping):
                allowed.update(_ids_from_entries([value]))
            elif value:
                allowed.add(_safe_str(value).strip())
    return {value for value in allowed if value}


def validate_narration_grounding(
    narration_payload: Mapping[str, Any],
    turn_contract: Mapping[str, Any],
    *,
    state_snapshot: Optional[Mapping[str, Any]] = None,
    strict_named_fact_check: bool = False,
) -> GroundingValidationResult:
    payload = _safe_dict(narration_payload)
    contract = _safe_dict(turn_contract)
    state = _safe_dict(state_snapshot)

    violations: List[GroundingViolation] = []
    full_text = _flatten_text(
        {
            "narration": payload.get("narration"),
            "action": payload.get("action"),
            "npc": payload.get("npc"),
            "reward": payload.get("reward"),
            "followup_hooks": payload.get("followup_hooks"),
        }
    )

    if payload.get("reward") not in (None, "", {}, []):
        if not _currency_or_inventory_delta_exists(contract):
            violations.append(
                GroundingViolation(
                    code="unsupported_reward",
                    field="reward",
                    message="Narration included a reward, but the turn contract has no reward/currency/inventory delta.",
                    evidence=_flatten_text(payload.get("reward"))[:240],
                )
            )

    reward_pattern = _contains_pattern(full_text, _REWARD_PATTERNS)
    if reward_pattern and not _reward_pattern_is_only_price_quote(full_text, reward_pattern) and not _currency_or_inventory_delta_exists(contract):
        violations.append(
            GroundingViolation(
                code="unsupported_reward_claim",
                field="narration",
                message="Narration mentions reward/currency/item gain, but the turn contract does not authorize it.",
                evidence=reward_pattern,
            )
        )

    combat_pattern = _contains_pattern(full_text, _COMBAT_PATTERNS)
    if combat_pattern and not _combat_delta_exists(contract):
        violations.append(
            GroundingViolation(
                code="unsupported_combat_claim",
                field="narration",
                message="Narration mentions combat/death/injury/blood/damage, but the turn contract has no combat delta.",
                evidence=combat_pattern,
            )
        )

    objective_pattern = _contains_pattern(full_text, _OBJECTIVE_COMPLETION_PATTERNS)
    if objective_pattern and not _quest_completion_exists(contract):
        violations.append(
            GroundingViolation(
                code="unsupported_objective_or_quest_completion",
                field="narration",
                message="Narration claims objective/quest completion without matching turn-contract completion.",
                evidence=objective_pattern,
            )
        )

    npc = _safe_dict(payload.get("npc"))
    speaker = _safe_str(npc.get("speaker") or npc.get("name") or npc.get("id")).strip()
    if speaker:
        allowed = _allowed_speakers(contract, state)
        if allowed and not _speaker_allowed(speaker, allowed):
            violations.append(
                GroundingViolation(
                    code="unsupported_npc_speaker",
                    field="npc.speaker",
                    message="NPC speaker is not present/known/allowed by the turn contract.",
                    evidence=speaker,
                )
            )

    move_pattern = _contains_pattern(full_text, _LOCATION_MOVE_PATTERNS)
    if move_pattern:
        allowed_locations = _allowed_locations(contract, state)
        lower_text = full_text.lower()
        if allowed_locations and not any(_safe_str(loc).lower() in lower_text for loc in allowed_locations):
            violations.append(
                GroundingViolation(
                    code="unsupported_location_move",
                    field="narration",
                    message="Narration appears to move the player to a location not authorized by the turn contract.",
                    evidence=move_pattern,
                )
            )

    if strict_named_fact_check:
        allowed_blob = " ".join(_extract_allowed_fact_texts(contract)).lower()
        for candidate in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", _safe_str(payload.get("narration"))):
            if candidate.lower() not in allowed_blob:
                violations.append(
                    GroundingViolation(
                        code="possible_unsupported_named_fact",
                        field="narration",
                        message="Narration contains a named phrase not found in allowed facts/leads/actions.",
                        evidence=candidate,
                    )
                )
                break

    player_action_text = _safe_str(
        contract.get("player_action")
        or contract.get("input")
        or contract.get("command")
        or _safe_dict(contract.get("result")).get("player_action")
    )

    player_made_debt_claim = bool(
        _contains_pattern(player_action_text, _UNSUPPORTED_DEBT_CLAIM_PATTERNS)
    )

    text_mentions_payment_or_debt = bool(
        _contains_pattern(full_text, _UNSUPPORTED_DEBT_CLAIM_PATTERNS)
        or _contains_pattern(full_text, _REWARD_PATTERNS)
    )

    if player_made_debt_claim and not _payment_or_debt_authorized(contract):
        clear_refusal = _contains_pattern(full_text, _CLEAR_DEBT_REFUSAL_PATTERNS)
        ambiguous_debt_response = _contains_pattern(full_text, _AMBIGUOUS_DEBT_RESPONSE_PATTERNS)
        explicit_grant = _contains_pattern(
            full_text,
            [
                rf"\b(?:hands?|handed|gives?|gave|pays?|paid)\s+(?:you\s+)?{_MONEY_PHRASE_PATTERN}\b",
                rf"\byou\s+(?:gain|receive|get|are\s+given)\s+{_MONEY_PHRASE_PATTERN}\b",
                r"\bpayment\s+changes\s+hands\b",
            ],
        )

        if explicit_grant:
            violations.append(
                GroundingViolation(
                    code="unsupported_debt_payment_claim",
                    field="narration",
                    message="Narration grants or confirms payment for an unsupported debt claim.",
                    evidence=explicit_grant,
                )
            )
        elif ambiguous_debt_response and not clear_refusal:
            violations.append(
                GroundingViolation(
                    code="unsupported_debt_claim_not_refused",
                    field="narration",
                    message="Player made an unsupported debt/payment claim, but narration answered ambiguously instead of clearly refusing.",
                    evidence=ambiguous_debt_response,
                )
            )
        elif text_mentions_payment_or_debt and not clear_refusal:
            violations.append(
                GroundingViolation(
                    code="unsupported_debt_claim_not_refused",
                    field="narration",
                    message="Player made an unsupported debt/payment claim, but narration did not clearly refuse or challenge it.",
                    evidence=player_action_text[:240],
                )
            )

    return GroundingValidationResult(ok=not violations, violations=violations)


def _first_allowed_speaker(
    turn_contract: Mapping[str, Any],
    state_snapshot: Optional[Mapping[str, Any]] = None,
) -> str:
    allowed = sorted(_allowed_speakers(turn_contract, state_snapshot))
    for value in allowed:
        if value and not value.lower().startswith("npc:"):
            return value
    for value in allowed:
        if value:
            return value.replace("npc:", "").replace("_", " ").title()
    return ""


def build_deterministic_fallback_narration(
    turn_contract: Mapping[str, Any],
    *,
    violations: Optional[Sequence[GroundingViolation]] = None,
    state_snapshot: Optional[Mapping[str, Any]] = None,
    reason: str = "grounding_validation_failed",
) -> Dict[str, Any]:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )
    violations = list(violations or [])

    codes = {violation.code for violation in violations}
    speaker = _first_allowed_speaker(contract, state_snapshot)

    player_action_text = _safe_str(
        contract.get("player_action")
        or contract.get("input")
        or contract.get("command")
        or _safe_dict(contract.get("result")).get("player_action")
    )
    player_made_debt_claim = bool(
        _contains_pattern(player_action_text, _UNSUPPORTED_DEBT_CLAIM_PATTERNS)
    )

    narration = ""
    action = ""
    npc_line = ""

    if (
        player_made_debt_claim
        or "unsupported_debt_payment_claim" in codes
        or "unsupported_debt_claim_not_refused" in codes
    ):
        display_speaker = speaker or "The NPC"
        narration = f"{display_speaker} does not hand over any coin."
        action = "The unsupported debt claim is refused; no payment or reward is resolved."
        npc_line = "No. I do not owe you coin."
    elif "unsupported_reward_claim" in codes or "unsupported_reward" in codes:
        narration = f"{speaker or 'The NPC'} does not hand over any coin."
        action = "No payment, reward, or inventory change is resolved by the turn contract."
        npc_line = "No coin changes hands. I can't agree to that."
    elif "unsupported_combat_claim" in codes:
        narration = "The confrontation remains tense, but no injury is resolved."
        action = "No combat, damage, death, or injury is resolved by the turn contract."
        npc_line = "Careful. This does not need to become violence."
    elif "unsupported_location_move" in codes:
        current_location = (
            contract.get("current_location")
            or contract.get("location")
            or result.get("current_location")
            or result.get("location")
            or "the current location"
        )
        narration = f"You remain at {current_location}."
        action = "No location change is resolved by the turn contract."
    elif "unsupported_objective_or_quest_completion" in codes:
        narration = "The lead remains unresolved."
        action = "No quest or objective completion is resolved by the turn contract."
        npc_line = "Not yet. We need something solid before calling this finished."
    elif "unsupported_npc_speaker" in codes:
        narration = "No unsupported speaker enters the exchange."
        action = "Only present and allowed characters may speak."
    else:
        brief = _safe_dict(contract.get("narration_brief"))
        facts = _extract_allowed_fact_texts(contract)
        narration = (
            _safe_str(brief.get("summary")).strip()
            or (facts[0] if facts else "")
            or _safe_str(result.get("narrative_brief") or result.get("message") or result.get("summary")).strip()
            or "The action resolves according to the current turn contract."
        )
        action = narration

    npc = None
    if npc_line:
        npc = {"speaker": speaker or "NPC", "line": npc_line}

    return {
        "format_version": "rpg_narration_v2",
        "narration": narration,
        "action": action,
        "npc": npc,
        "reward": None,
        "followup_hooks": [],
        "grounding_fallback": True,
        "grounding_fallback_reason": reason,
    }


def build_fallback_narration(
    turn_contract: Mapping[str, Any],
    *,
    reason: str = "grounding_validation_failed",
) -> Dict[str, Any]:
    return build_deterministic_fallback_narration(turn_contract, reason=reason)


def _reward_pattern_is_only_price_quote(text: str, reward_pattern: Optional[str]) -> bool:
    if not reward_pattern:
        return False

    text = _safe_str(text)

    # Explicit grant/receive verbs still mean reward claim, not price quote.
    explicit_grant_patterns = [
        rf"\byou\s+(?:gain|gained|receive|received|get|got|take|took|earn|earned|are\s+given|were\s+given)\s+{_MONEY_PHRASE_PATTERN}\b",
        rf"\b(?:gain|gained|receive|received|receives|rewarded|earns?|earned)\b.*\b{_MONEY_PHRASE_PATTERN}\b",
        rf"\b(?:hands?|handed|gives?|gave|offers?|offered|pays?|paid)\s+(?:you\s+)?{_MONEY_PHRASE_PATTERN}\b",
        rf"\b{_MONEY_PHRASE_PATTERN}\s+(?:is|are|was|were)\s+(?:added|placed|put)\b.*\b(?:inventory|purse|hand|pocket|pack)\b",
        r"\badds?\b.*\bto your inventory\b",
        r"\bpayment changes hands\b",
    ]
    if _contains_pattern(text, explicit_grant_patterns):
        return False

    # If there is a price/cost/service context, treat currency mention as a quote.
    return bool(_contains_price_quote(text))


def _candidate_payload(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)
    npc = _safe_dict(value.get("npc"))
    return {
        "format_version": "rpg_narration_v2",
        "narration": _safe_str(value.get("narration")).strip(),
        "action": _safe_str(value.get("action")).strip(),
        "npc": {
            "speaker": _safe_str(npc.get("speaker")).strip(),
            "line": _safe_str(npc.get("line")).strip(),
        }
        if npc
        else None,
        "reward": value.get("reward") if value.get("reward") not in ("", {}, []) else None,
        "followup_hooks": _safe_list(value.get("followup_hooks")),
    }


def select_grounded_narration_candidate(
    parsed_payload: Mapping[str, Any],
    turn_contract: Mapping[str, Any],
    *,
    state_snapshot: Optional[Mapping[str, Any]] = None,
    grounding_settings: Optional[Mapping[str, Any]] = None,
    strict_named_fact_check: bool = False,
) -> Dict[str, Any]:
    settings = normalize_grounding_settings(grounding_settings or {})
    parsed = _safe_dict(parsed_payload)

    if not settings.get("enabled", True):
        payload = _candidate_payload(parsed)
        payload["grounding_validation"] = {
            "ok": True,
            "selected_candidate": "ungrounded_disabled",
            "fallback_used": False,
            "violations": [],
        }
        return payload

    if "primary" in parsed or "safe_fallback" in parsed:
        primary = _candidate_payload(parsed.get("primary"))
        safe_fallback = _candidate_payload(parsed.get("safe_fallback"))
    else:
        primary = _candidate_payload(parsed)
        safe_fallback = {}

    primary_result = validate_narration_grounding(
        primary,
        turn_contract,
        state_snapshot=state_snapshot,
        strict_named_fact_check=strict_named_fact_check,
    )

    if primary_result.ok:
        primary_result.selected_candidate = "primary"
        primary["grounding_validation"] = primary_result.to_dict()
        return primary

    if settings.get("llm_safe_fallback_candidate", True) and safe_fallback:
        fallback_result = validate_narration_grounding(
            safe_fallback,
            turn_contract,
            state_snapshot=state_snapshot,
            strict_named_fact_check=strict_named_fact_check,
        )
        if fallback_result.ok:
            fallback_result.selected_candidate = "safe_fallback"
            fallback_result.fallback_used = True
            fallback_result.fallback_source = "llm_safe_fallback"
            validation = fallback_result.to_dict()
            validation["primary_rejected"] = True
            validation["primary_violations"] = primary_result.to_dict().get("violations", [])
            safe_fallback["grounding_validation"] = validation
            return safe_fallback

    deterministic = build_deterministic_fallback_narration(
        turn_contract,
        violations=primary_result.violations,
        state_snapshot=state_snapshot,
    )
    primary_result.selected_candidate = "deterministic_fallback"
    primary_result.fallback_used = True
    primary_result.fallback_source = "deterministic_fallback"
    deterministic["grounding_validation"] = primary_result.to_dict()
    return deterministic


def validate_or_fallback_narration(
    narration_payload: Mapping[str, Any],
    turn_contract: Mapping[str, Any],
    *,
    state_snapshot: Optional[Mapping[str, Any]] = None,
    strict_named_fact_check: bool = False,
) -> Dict[str, Any]:
    return select_grounded_narration_candidate(
        narration_payload,
        turn_contract,
        state_snapshot=state_snapshot,
        grounding_settings=None,
        strict_named_fact_check=strict_named_fact_check,
    )