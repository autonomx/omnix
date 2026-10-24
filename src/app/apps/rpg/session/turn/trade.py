"""Trade on the pipeline (RQ-2.3): buying from the people who sell where the hero stands, and asking what they sell.

Trade's owner is the economy's service resolver (roadmap §4.3). The pipeline asks it, on a copy of the campaign,
which offer the player means and what buying it does, and turns the answer into changes: coin, goods, a need
eased, as typed changes; who remembers the trade, the ledger and the offer's stock, as ``TradeRecorded``. The
reducer applies them, as it applies every change.

Paid information, repairs and using a room already paid for stay on the older path until their mechanics move
(RQ-2.4, RQ-2.5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import copy_state, safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import TRADE_SECTIONS, StateChange, TimeAdvanced, TradeRecorded, TurnCounted
from app.apps.rpg.foundation.state.extract import changes_between
from app.apps.rpg.rules.economy.currency import format_currency
from app.apps.rpg.rules.economy.service_resolver import resolve_service_turn

MINUTES_PER_TICK = 10
TRADE_KINDS = frozenset({"service_purchase", "service_inquiry"})
# What the pipeline sells; the rest of the economy's services keep the older path for now.
TRADED_SERVICES = frozenset({"shop_goods", "meal", "drink", "lodging"})
_EASES = {"meal": "hunger", "drink": "thirst"}


@dataclass(frozen=True)
class TradeResolution:
    changes: list[StateChange]
    lines: list[str]
    refused: bool = False
    minutes: int = MINUTES_PER_TICK
    kind: str = ""
    provider_name: str = ""


def _lines(service_result: Mapping[str, Any], application: Mapping[str, Any]) -> tuple[list[str], bool]:
    """What happened, as the older path said it, and whether the trade was refused."""
    provider = _s(service_result.get("provider_name")) or "The provider"
    purchase = _d(service_result.get("purchase"))
    offers = [_d(offer) for offer in _l(service_result.get("offers"))]
    if service_result.get("kind") == "service_purchase" and application.get("applied") is True:
        label = _s(_d(application.get("transaction_record")).get("label")) or "the selected service"
        lines = [f"You pay {format_currency(_d(purchase.get('price')))} to {provider} for {label}. "
                 "The transaction is complete."]
        if _d(_d(purchase.get("applied_effects")).get("survival_relief")).get("ok"):
            eased = _EASES.get(_s(service_result.get("service_kind")))
            if eased:
                lines.append(f"It eases your {eased}.")
        return lines, False
    unspecified = _s(service_result.get("status")) == "purchase_offer_not_found" and len(offers) > 1
    if purchase.get("blocked") and not unspecified:
        reason = _s(purchase.get("blocked_reason")).replace("_", " ")
        return [f"The purchase from {provider} does not go through: {reason or 'it is refused'}."], True
    listed = ", ".join(f"{_s(offer.get('label'))} ({format_currency(_d(offer.get('price')))})"
                       for offer in offers if _s(offer.get("label")))
    if listed:
        return [f"{provider} offers: {listed}." + (" Nothing is sold until you name one." if unspecified else "")], False
    return [f"{provider} has nothing to offer you here."], True


def resolve_trade(document: Mapping[str, Any], text: str) -> TradeResolution | None:
    """The trade the player asks for, or ``None`` when it is not one the pipeline makes."""
    from app.apps.rpg.session.service_runtime import service_action_from_result, service_authoritative_result

    simulation = copy_state(_d(document.get("simulation_state")))
    match = resolve_service_turn(player_input=text, action=None, resolved_action={}, simulation_state=simulation,
                                 runtime_state=_d(document.get("runtime_state")))
    if not match.get("matched") or match.get("kind") not in TRADE_KINDS:
        return None
    if _s(match.get("service_kind")) not in TRADED_SERVICES:
        return None
    applied = service_authoritative_result(simulation, service_action_from_result(text, {}, match))
    after = _d(applied.get("simulation_state")) or simulation
    result = _d(applied.get("result"))
    service_result = _d(result.get("service_result")) or match
    application = _d(result.get("service_application"))
    before = _d(document.get("simulation_state"))
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    counted = TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)
    # Coin, goods and needs as typed changes; the trade's living-world sections whole.
    typed = [change for change in changes_between(document, {**dict(document), "simulation_state": after})
             if change.type not in {"turn_counted", "time_advanced"}]
    sections = {key: after[key] for key in TRADE_SECTIONS if key in after and after.get(key) != before.get(key)}
    lines, refused = _lines(service_result, application)
    changes: list[StateChange] = [counted, TimeAdvanced(ticks=1, minutes=MINUTES_PER_TICK), *typed]
    if sections:
        changes.append(TradeRecorded(simulation=sections, summary={
            "kind": _s(service_result.get("kind")), "service_kind": _s(service_result.get("service_kind")),
            "provider_id": _s(service_result.get("provider_id")), "offer_id": _s(service_result.get("selected_offer_id"))}))
    return TradeResolution(changes, lines, refused=refused, kind=_s(service_result.get("kind")),
                           provider_name=_s(service_result.get("provider_name")))


__all__ = ["TRADED_SERVICES", "TradeResolution", "resolve_trade"]
