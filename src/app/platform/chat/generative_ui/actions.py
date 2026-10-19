"""Server validation of ``ui_action`` on a sent message (chat generative UI, GUI-5.4).

A widget action is a claim by the browser that the message answers a block of
an earlier reply. It is kept only when it matches that reply exactly:

- the source is an assistant message in the same session;
- the block exists and supports the action (``choose`` on ``choices``,
  ``submit`` on ``form``);
- for ``choose``, the message is exactly the option's label;
- for ``submit``, every value matches its field and required fields are filled.

Anything else is stripped and the text proceeds as an ordinary message. An
action never does anything beyond a normal chat turn: it grants nothing.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)


class UiActionRejected(ValueError):
    """Why an action does not match its source reply."""


def _source_block(session: Any, action: Any) -> Mapping[str, Any]:
    if session is None:
        raise UiActionRejected("session_not_found")
    source = next((message for message in getattr(session, "messages", []) if message.id == action.source_message_id), None)
    if source is None or source.role != "assistant":
        raise UiActionRejected("source_not_an_assistant_reply_in_session")
    if source.metadata.get("delivery_status") == "interrupted":
        raise UiActionRejected("source_has_no_ui")
    ui = source.metadata.get("ui")
    blocks = ui.get("blocks") if isinstance(ui, Mapping) else None
    block = blocks.get(action.block_id) if isinstance(blocks, Mapping) else None
    if not isinstance(block, Mapping):
        raise UiActionRejected("block_not_found")
    return block


def _check_choice(block: Mapping[str, Any], action: Any, content: str) -> dict[str, Any]:
    if block.get("type") != "choices":
        raise UiActionRejected("block_does_not_support_choose")
    options = [str(option.get("label") or "") for option in block.get("options") or [] if isinstance(option, Mapping)]
    text = content.strip()
    index = action.option_index if action.option_index is not None else (options.index(text) if text in options else None)
    if index is None or not 0 <= index < len(options):
        raise UiActionRejected("option_not_found")
    if options[index] != text:
        raise UiActionRejected("content_is_not_the_option_label")
    return {"source_message_id": action.source_message_id, "block_id": action.block_id, "action": "choose", "option_index": index}


def _check_value(field: Mapping[str, Any], value: Any) -> None:
    kind = field.get("kind")
    if kind == "toggle":
        if not isinstance(value, bool):
            raise UiActionRejected(f"value_not_boolean:{field.get('name')}")
    elif kind == "select":
        if not isinstance(value, str) or value not in (field.get("options") or []):
            raise UiActionRejected(f"value_not_an_option:{field.get('name')}")
    elif kind == "slider":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise UiActionRejected(f"value_not_a_number:{field.get('name')}")
        if not float(field.get("min", 0)) <= float(value) <= float(field.get("max", 0)):
            raise UiActionRejected(f"value_out_of_range:{field.get('name')}")
    else:
        limit = int(field.get("max_length") or 200)
        if not isinstance(value, str) or len(value) > limit:
            raise UiActionRejected(f"value_not_text:{field.get('name')}")


def _check_submit(block: Mapping[str, Any], action: Any) -> dict[str, Any]:
    if block.get("type") != "form":
        raise UiActionRejected("block_does_not_support_submit")
    fields = {str(field.get("name")): field for field in block.get("fields") or [] if isinstance(field, Mapping)}
    values = dict(action.values or {})
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise UiActionRejected(f"unknown_fields:{','.join(unknown)}")
    for name, field in fields.items():
        if name not in values:
            if field.get("required") and field.get("kind") != "toggle":
                raise UiActionRejected(f"required_field_missing:{name}")
            continue
        _check_value(field, values[name])
        if field.get("required") and field.get("kind") in {"select", "text"} and not str(values[name]).strip():
            raise UiActionRejected(f"required_field_missing:{name}")
    return {"source_message_id": action.source_message_id, "block_id": action.block_id, "action": "submit", "values": values}


def validate_ui_action(session: Any, action: Any, content: str) -> dict[str, Any]:
    """The normalized action when it matches its source reply; raises ``UiActionRejected`` otherwise."""
    block = _source_block(session, action)
    if action.action == "choose":
        return _check_choice(block, action, content)
    return _check_submit(block, action)


def admitted_request(chat_store: Any, session_id: str, request: Any) -> Any:
    """The request to admit: its ``ui_action`` normalized when valid, removed when not."""
    action = getattr(request, "ui_action", None)
    if action is None:
        return request
    try:
        session = chat_store.get_session(session_id)
        normalized = validate_ui_action(session, action, request.content)
    except UiActionRejected as rejected:
        logger.info("chat_ui_action_stripped session=%s reason=%s", session_id, rejected)
        return request.model_copy(update={"ui_action": None})
    except Exception:
        logger.warning("chat_ui_action_validation_failed session=%s", session_id, exc_info=True)
        return request.model_copy(update={"ui_action": None})
    return request.model_copy(update={"ui_action": type(action).model_validate(normalized)})
