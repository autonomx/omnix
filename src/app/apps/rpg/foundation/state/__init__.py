"""Typed campaign state (RQ-1.1, RQ-1.2): the document's sections, a view over them, the closed vocabulary of
changes, and the reducer that applies them."""
from .changes import parse_changes
from .reducer import reduce
from .sections import SECTION_PATHS, read_path
from .view import CampaignStateView

__all__ = ["SECTION_PATHS", "CampaignStateView", "parse_changes", "read_path", "reduce"]
