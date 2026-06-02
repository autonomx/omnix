from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Tuple

from app.rpg.economy.currency import normalize_currency

SOURCE = "deterministic_economy_report"
CONTRACT_SOURCE = "deterministic_economy_presentation_contract"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def format_currency(currency: Any) -> str:
    value = normalize_currency(currency)
    parts = []
    for key in ("gold", "silver", "copper"):
        amount = _safe_int(value.get(key), 0)
        if amount:
            parts.append(f"{amount} {key}")
    return ", ".join(parts) if parts else "0 copper"


def _transaction_key(row: Dict[str, Any]) -> Tuple[str, str, int, int, str]:
    price = normalize_currency(row.get("price"))
    price_key = f"{price['gold']}g:{price['silver']}s:{price['copper']}c"
    return (
        _safe_str(row.get("kind") or row.get("action_type")),
        _safe_str(row.get("item_id")),
        _safe_int(row.get("qty"), 0),
        _safe_int(row.get("tick"), 0),
        price_key,
    )


def _normalize_transaction(row: Any, *, turn: int = 0) -> Dict[str, Any]:
    row = _safe_dict(row)
    item_id = _safe_str(row.get("item_id"))
    kind = _safe_str(row.get("kind") or row.get("action_type"))
    if kind not in {"buy", "sell"} or not item_id:
        return {}
    return {
        "turn": _safe_int(row.get("turn"), turn),
        "tick": _safe_int(row.get("tick"), 0),
        "kind": kind,
        "item_id": item_id,
        "qty": max(1, _safe_int(row.get("qty"), 1)),
        "price": normalize_currency(row.get("price")),
        "reason": _safe_str(row.get("reason")),
        "source": _safe_str(row.get("source") or "deterministic_merchant_transactions"),
    }


def _collect_from_container(container: Any, *, turn: int, rows: List[Dict[str, Any]]) -> None:
    container = _safe_dict(container)
    direct = _normalize_transaction(container.get("transaction_log_entry"), turn=turn)
    if direct:
        rows.append(direct)
    merchant = _safe_dict(container.get("merchant_state"))
    for entry in _safe_list(merchant.get("transaction_log")):
        normalized = _normalize_transaction(entry, turn=turn)
        if normalized:
            rows.append(normalized)


def collect_economy_transactions(report_data: Any) -> List[Dict[str, Any]]:
    data = _safe_dict(report_data)
    rows: List[Dict[str, Any]] = []
    for entry in _safe_list(data.get("economy_transaction_log")) + _safe_list(data.get("transaction_log")):
        normalized = _normalize_transaction(entry)
        if normalized:
            rows.append(normalized)
    for merchant in _safe_dict(_safe_dict(data.get("economy_state")).get("merchants")).values():
        for entry in _safe_list(_safe_dict(merchant).get("transaction_log")):
            normalized = _normalize_transaction(entry)
            if normalized:
                rows.append(normalized)
    for turn_row in _safe_list(data.get("turns")):
        turn_row = _safe_dict(turn_row)
        turn = _safe_int(turn_row.get("turn") or turn_row.get("turn_index"), 0)
        _collect_from_container(turn_row, turn=turn, rows=rows)
        for key in ("result", "resolved_result", "narration_context"):
            _collect_from_container(turn_row.get(key), turn=turn, rows=rows)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = _transaction_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_economy_presentation_contract(report_data: Any) -> Dict[str, Any]:
    rows = collect_economy_transactions(report_data)
    allowed = [
        f"{row['kind']} {row['qty']} x {row['item_id']} for {format_currency(row['price'])}"
        for row in rows
    ]
    return {
        "source": CONTRACT_SOURCE,
        "allowed_transaction_claims": allowed,
        "forbidden_economy_claims": [
            "Do not invent merchant stock.",
            "Do not invent prices.",
            "Do not change deterministic transaction totals.",
            "Do not claim items or currency changed unless backed by transaction rows.",
        ],
    }


def build_economy_transaction_report(report_data: Any) -> Dict[str, Any]:
    rows = collect_economy_transactions(report_data)
    return {
        "source": SOURCE,
        "transaction_count": len(rows),
        "transactions": rows,
        "presentation_contract": build_economy_presentation_contract(report_data),
    }


def render_economy_transactions_html(report_data: Any) -> str:
    report = build_economy_transaction_report(report_data)
    rows = report["transactions"]
    if not rows:
        return ""
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(row['turn']))}</td>"
            f"<td>{escape(row['kind'])}</td>"
            f"<td>{escape(row['item_id'])}</td>"
            f"<td>{escape(str(row['qty']))}</td>"
            f"<td>{escape(format_currency(row['price']))}</td>"
            f"<td>{escape(row['reason'])}</td>"
            f"<td>{escape(row['source'])}</td>"
            "</tr>"
        )
    contract = report["presentation_contract"]
    forbidden = "".join(f"<li>{escape(item)}</li>" for item in contract["forbidden_economy_claims"])
    return (
        "<section id=\"economy-transactions\">"
        "<h2>Economy Transactions</h2>"
        "<p>Deterministic buy/sell rows and deltas backed by runtime transaction logs.</p>"
        "<table><thead><tr><th>Turn</th><th>Kind</th><th>Item</th><th>Qty</th>"
        "<th>Total</th><th>Reason</th><th>Source</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        "<h3>Economy Presentation Guardrails</h3>"
        f"<p>Source: {escape(contract['source'])}</p>"
        "<ul>"
        + forbidden
        + "</ul></section>"
    )
