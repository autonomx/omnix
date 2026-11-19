"""One decision per requested stock from a local model.

A local model constrains its output to the JSON schema it is given, so the schema names every requested stock and what
a state needs ("armed" needs a trigger): omissions and half-formed decisions cannot be generated. What still fails
costs only that stock. The others are kept, and the failed ones are asked once more; one still unresolved is simply not
decided on this pass, and the monitor asks again on its next one. Research only: nothing here grants execution
authority.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from app.providers import ChatMessage
from app.providers.structured.contracts import StructuredMode
from app.providers.structured.schema_projection import project_provider_schema

from .structured_llm import TradingModelOutputError, trading_model_call
from .trade_logging import trade_log

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Requires = Mapping[str, tuple[str, ...]]

# These bound what a decision can cost in output tokens.
THESIS_MAX_CHARACTERS = 400
EVIDENCE_MAX_ITEMS = 3
EVIDENCE_MAX_CHARACTERS = 160
FALLBACK_STATE = "watch"


class _RawBatch(BaseModel):
    """The batch before its decisions are judged one by one."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[dict[str, Any]]


def _non_null(schema: dict[str, Any]) -> dict[str, Any]:
    """The field as required: a price is a number, not the Decimal-as-text the model schema also allows."""
    options = [option for option in schema.get("anyOf", ()) if option.get("type") != "null"]
    if not options:
        return schema
    numbers = [option for option in options if option.get("type") == "number"]
    kept = numbers or options
    return kept[0] if len(kept) == 1 else {"anyOf": kept}


def _bounded(properties: dict[str, Any]) -> dict[str, Any]:
    bounded = copy.deepcopy(properties)
    if "thesis" in bounded:
        bounded["thesis"]["maxLength"] = THESIS_MAX_CHARACTERS
    for name in ("evidence_for", "evidence_against"):
        if name in bounded:
            bounded[name]["maxItems"] = EVIDENCE_MAX_ITEMS
            bounded[name]["items"] = {"type": "string", "maxLength": EVIDENCE_MAX_CHARACTERS}
    return bounded


def _decision_schema(base: dict[str, Any], instrument_id: str, requires: Requires) -> dict[str, Any]:
    properties = _bounded(base["properties"])
    properties["instrument_id"] = {"const": instrument_id}

    def shape(state: dict[str, Any] | None, needed: tuple[str, ...]) -> dict[str, Any]:
        shaped = copy.deepcopy(properties)
        if state is not None:
            shaped["state"] = state
        for name in needed:
            shaped[name] = _non_null(shaped[name])
        return {"type": "object", "additionalProperties": False, "required": base["required"], "properties": shaped}

    if not requires:
        return shape(None, ())
    states = list(properties["state"]["enum"])
    variants = [shape({"enum": [state for state in states if state not in requires]}, ())]
    variants += [shape({"const": state}, needed) for state, needed in requires.items() if state in states]
    return {"anyOf": variants}


def per_instrument_format(
    item_model: type[BaseModel],
    instrument_ids: Sequence[str],
    *,
    requires: Requires,
    schema_name: str,
) -> dict[str, Any]:
    """A JSON-schema response format with exactly one decision for each requested stock, in order."""
    base = project_provider_schema(
        item_model.model_json_schema(), mode=StructuredMode.JSON_SCHEMA, provider_name="chatgpt_codex",
    )
    count = len(instrument_ids)
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["decisions"],
        "properties": {
            "decisions": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "prefixItems": [_decision_schema(base, instrument_id, requires) for instrument_id in instrument_ids],
            }
        },
    }
    if base.get("$defs"):
        schema["$defs"] = base["$defs"]
    return {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}


def _accept(raw: dict[str, Any], item_model: type[T], requires: Requires) -> tuple[T | None, bool]:
    """The validated decision and whether it was downgraded; a state missing what it needs is only a watch."""
    candidate = dict(raw)
    needed = requires.get(str(candidate.get("state")), ())
    downgraded = any(candidate.get(name) is None for name in needed)
    if downgraded:
        candidate["state"] = FALLBACK_STATE
    try:
        return item_model.model_validate(candidate), downgraded
    except ValidationError:
        return None, downgraded


@dataclass(frozen=True)
class LocalBatch(Generic[T]):
    items: tuple[T, ...]
    response: Any
    unresolved: tuple[str, ...]
    downgraded: tuple[str, ...]
    attempts: int


def local_batch_call(
    provider: Any,
    *,
    rows: Sequence[dict[str, Any]],
    build_messages: Callable[[list[dict[str, Any]]], list[ChatMessage]],
    item_model: type[T],
    requires: Requires,
    contract_id: str,
    schema_name: str,
    model: str | None,
    max_tokens: Callable[[int], int],
) -> LocalBatch[T]:
    """Ask for every row, then once more for the rows without a usable decision."""
    ordered = [str(row["instrument_id"]) for row in rows]
    pending = list(rows)
    found: dict[str, T] = {}
    downgraded: set[str] = set()
    response: Any = None
    failure: TradingModelOutputError | None = None
    attempts = 0
    for _ in range(2):
        attempts += 1
        try:
            reply = trading_model_call(
                provider,
                build_messages(pending),
                output_model=_RawBatch,
                contract_id=contract_id,
                schema_name=schema_name,
                model=model,
                max_tokens=max_tokens(len(pending)),
                response_format=per_instrument_format(
                    item_model,
                    [str(row["instrument_id"]) for row in pending],
                    requires=requires,
                    schema_name=schema_name,
                ),
            )
        except TradingModelOutputError as exc:
            failure = exc
            continue
        response = reply.response
        requested = {str(row["instrument_id"]) for row in pending}
        for raw in reply.value.decisions:
            instrument_id = str(raw.get("instrument_id"))
            if instrument_id not in requested or instrument_id in found:
                continue
            accepted, was_downgraded = _accept(raw, item_model, requires)
            if accepted is not None:
                found[instrument_id] = accepted
                if was_downgraded:
                    downgraded.add(instrument_id)
        pending = [row for row in pending if str(row["instrument_id"]) not in found]
        if not pending:
            break
    if not found:
        if failure is not None:
            raise failure
        raise RuntimeError(f"{contract_id}:no_valid_decisions")
    unresolved = tuple(str(row["instrument_id"]) for row in pending)
    if unresolved or downgraded:
        trade_log(
            "auto_trading", "local_batch_partial", contract_id=contract_id, unresolved=list(unresolved),
            downgraded=sorted(downgraded), attempts=attempts, execution_authority=False,
        )
    return LocalBatch(
        items=tuple(found[instrument_id] for instrument_id in ordered if instrument_id in found),
        response=response,
        unresolved=unresolved,
        downgraded=tuple(sorted(downgraded)),
        attempts=attempts,
    )


__all__ = ["LocalBatch", "local_batch_call", "per_instrument_format"]
