"""Context-local identity shared by RPG turn middleware and its domain hook."""
from contextvars import ContextVar


DIRECT_RPG_SUBMISSION_ID: ContextVar[str] = ContextVar(
    "omnix_direct_rpg_submission_id", default=""
)
