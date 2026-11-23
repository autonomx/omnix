"""What a world graph audit is: a named report and its gate, and the error the gate raises.

Each audit module (``generation_<audit>.py``) owns its issue type, its report and its ``require_valid_*`` gate; the
gate raises a ``GraphAuditError`` subclass that names its code and the issue fields its message lists. The
message is ``<code>:`` and then each issue's fields joined by ``:``, the issues joined by ``;``; a field is an
attribute path (``claim.subject_id``) with an optional format (``entity_ratio:.4f``). An audit whose issue does
not read as a list of fields overrides ``render``. ``compilation`` runs the audits in the order of its registry,
``GraphAudit`` entries that unpack as ``(name, report, require)``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from operator import attrgetter
from typing import Any, ClassVar, NamedTuple

ReportFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], dict[str, Any]]
RequireFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], Any]


class GraphAudit(NamedTuple):
    name: str
    report: ReportFn
    require: RequireFn


class GraphAuditError(ValueError):
    code: ClassVar[str]
    fields: ClassVar[tuple[str, ...]] = ("code", "path")

    def __init__(self, issues: Iterable[Any]) -> None:
        self.issues = tuple(issues)
        super().__init__(f"{self.code}:" + ";".join(self.render(issue) for issue in self.issues))

    @classmethod
    def render(cls, issue: Any) -> str:
        parts = []
        for field in cls.fields:
            path, _, spec = field.partition(":")
            parts.append(format(attrgetter(path)(issue), spec))
        return ":".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "issues": [issue.as_dict() for issue in self.issues]}


__all__ = ["GraphAudit", "GraphAuditError", "ReportFn", "RequireFn"]
