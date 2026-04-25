"""Deterministic RPG economy and service helpers.

This package owns authoritative service/economy facts.
LLM narration may describe these facts, but must not create them.
"""

from app.rpg.economy.currency import (
    add_currency,
    can_afford,
    currency_to_copper,
    format_currency,
    normalize_currency,
    subtract_currency,
)
from app.rpg.economy.service_registry import get_provider_offers, get_service_provider
from app.rpg.economy.service_resolver import (
    resolve_service_intent,
    resolve_service_turn,
)
from app.rpg.economy.service_transactions import (
    append_service_transaction_record,
    build_service_transaction_record,
    get_transaction_history,
)

__all__ = [
    "add_currency",
    "append_service_transaction_record",
    "build_service_transaction_record",
    "can_afford",
    "currency_to_copper",
    "format_currency",
    "get_provider_offers",
    "get_service_provider",
    "get_transaction_history",
    "normalize_currency",
    "resolve_service_intent",
    "resolve_service_turn",
    "subtract_currency",
]
