"""Runtime economy, shop, and inn action adapters for RPG Phase 20."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.economy_services import (
    Currency,
    MerchantInventory,
    MerchantStockItem,
    ServiceOffer,
    authorize_service,
    buy_item,
)

ECONOMY_RUNTIME_SOURCE = "phase20_economy_runtime_v1"


def build_economy_runtime_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Resolve one report-facing economy action without mutating runtime state."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    action = str(turn_result.get("economy_action") or turn_result.get("action_kind") or "")
    wallet = _wallet(state, turn_result)
    result: Mapping[str, object] | None = None
    issues: list[str] = []
    if action == "buy_item":
        result, issues = _buy_report(turn_result, state, wallet)
    elif action == "service":
        result, issues = _service_report(turn_result, state, wallet)
    else:
        issues.append("unsupported_economy_action")
    return {
        "source": ECONOMY_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": issues,
        "action": action,
        "wallet_before": wallet.as_gsc(),
        "result": dict(result or {}),
    }


def _buy_report(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
    wallet: Currency,
) -> tuple[Mapping[str, object], list[str]]:
    merchant = _merchant_inventory(state, turn_result)
    item_id = str(turn_result.get("item_id") or "")
    quantity = int(turn_result.get("quantity") or 1)
    if not item_id:
        return {}, ["missing_item_id"]
    try:
        updated, wallet_after = buy_item(merchant, wallet, item_id, quantity)
    except (KeyError, ValueError) as exc:
        return {"reason": str(exc)}, [f"buy_failed:{str(exc)}"]
    item = merchant.item(item_id)
    return {
        "ok": True,
        "merchant_id": merchant.merchant_id,
        "item_id": item_id,
        "quantity": quantity,
        "unit_price": item.price.as_gsc() if item else {},
        "wallet_after": wallet_after.as_gsc(),
        "stock_after": updated.item(item_id).quantity if updated.item(item_id) else 0,
    }, []


def _service_report(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
    wallet: Currency,
) -> tuple[Mapping[str, object], list[str]]:
    offer = _service_offer(state, turn_result)
    if offer is None:
        return {}, ["missing_service_offer"]
    raw_exception = turn_result.get("service_exception")
    exception = str(raw_exception) if raw_exception else None
    resolution = authorize_service(offer, wallet, exception=exception)  # type: ignore[arg-type]
    issues = [] if resolution.ok else [f"service_failed:{resolution.reason}"]
    return resolution.as_dict(), issues


def _merchant_inventory(state: Mapping[str, object], turn_result: Mapping[str, object]) -> MerchantInventory:
    merchant_id = str(turn_result.get("merchant_id") or "merchant")
    economy = _mapping(state.get("economy"))
    merchants = _mapping(economy.get("merchants"))
    raw = _mapping(merchants.get(merchant_id) or turn_result.get("merchant"))
    stock: dict[str, MerchantStockItem] = {}
    for item in _sequence(raw.get("stock")):
        if isinstance(item, Mapping):
            stock_item = _stock_item(item)
            stock[stock_item.item_id] = stock_item
    return MerchantInventory(merchant_id, stock)


def _stock_item(raw: Mapping[str, object]) -> MerchantStockItem:
    item_id = str(raw.get("item_id") or raw.get("id") or "item")
    price = _currency(_mapping(raw.get("price")))
    return MerchantStockItem(
        item_id=item_id,
        name=str(raw.get("name") or item_id),
        price=price,
        quantity=int(raw.get("quantity") or 0),
    )


def _service_offer(state: Mapping[str, object], turn_result: Mapping[str, object]) -> ServiceOffer | None:
    service_id = str(turn_result.get("service_id") or "")
    economy = _mapping(state.get("economy"))
    for raw in _sequence(economy.get("services")) + _sequence(turn_result.get("services")):
        if not isinstance(raw, Mapping):
            continue
        if service_id and str(raw.get("service_id") or raw.get("id")) != service_id:
            continue
        return ServiceOffer(
            service_id=str(raw.get("service_id") or raw.get("id") or service_id),
            name=str(raw.get("name") or service_id or "Service"),
            price=_currency(_mapping(raw.get("price"))),
            provider_id=str(raw.get("provider_id") or raw.get("provider") or "provider"),
            tags=tuple(str(item) for item in _sequence(raw.get("tags"))),
        )
    return None


def _wallet(state: Mapping[str, object], turn_result: Mapping[str, object]) -> Currency:
    raw = _mapping(turn_result.get("wallet") or _mapping(state.get("player")).get("currency"))
    return _currency(raw)


def _currency(raw: Mapping[str, object]) -> Currency:
    return Currency.from_gsc(
        gold=int(raw.get("gold") or 0),
        silver=int(raw.get("silver") or 0),
        copper=int(raw.get("copper") or 0),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
