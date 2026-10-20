"""``dub_status``: the dubbing app's tool for voice API clients and MCP (Voice Studio Phase 7).

Registered through Voice Studio's ``VOICE_CLIENT_TOOLS`` port, so the platform
never imports this app (ADR-0016). It reads; it starts nothing.
"""
from __future__ import annotations

from typing import Any


def _summary(project: Any) -> dict[str, Any]:
    return {"id": project.id, "title": project.title, "source_language": project.source_language,
            "target_language": project.target_language, "line_count": project.line_count,
            "approved_count": project.approved_count, "updated_at": project.updated_at,
            "steps": {step: str((state or {}).get("status") or "") for step, state in (project.steps or {}).items()
                      if isinstance(state, dict)}}


class DubStatusTool:
    name = "dub_status"
    capability = "dub.status"
    description = "Dubbing projects in this workspace, or one project's steps, lines and outputs."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"project_id": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    }

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from app.persistence.database import default_database
        from app.runtime.tenant_context import current_tenant

        from . import service

        project_id = str(arguments.get("project_id") or "").strip()
        if not project_id:
            return {"projects": [_summary(project) for project in service.list_projects(default_database(),
                                                                                         current_tenant())]}
        try:
            project = service.get_project(default_database(), current_tenant(), project_id)
        except service.DubbingNotFound as exc:
            raise LookupError("no such dubbing project in this workspace") from exc
        return {**_summary(project), "assets": dict(project.assets or {}),
                "lines": [{"id": segment.id, "speaker": segment.speaker, "fit": segment.fit_status,
                           "approved": bool(segment.approved)}
                          for segment in project.segments]}


__all__ = ["DubStatusTool"]
