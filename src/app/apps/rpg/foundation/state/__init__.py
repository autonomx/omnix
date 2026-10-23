"""Typed campaign state (RQ-1.1, RQ-1.2): the document's sections, a view over them, the closed vocabulary of
changes, and the reducer that applies them."""
from .changes import CHANGE_TYPES, StateChange, parse_changes
from .reducer import ChangeRejected, reduce
from .sections import SECTION_PATHS, SECTIONS, InventoryStack, Purse, Section, read_path
from .view import CampaignStateView

__all__ = [
    "CHANGE_TYPES",
    "SECTIONS",
    "SECTION_PATHS",
    "CampaignStateView",
    "ChangeRejected",
    "InventoryStack",
    "Purse",
    "Section",
    "StateChange",
    "parse_changes",
    "read_path",
    "reduce",
]
