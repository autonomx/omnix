"""Fail-closed certification for committing generated Campaign Bible canon."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class WorldForgeCommitBlockedError(RuntimeError):
    """Raised when generated canon is not eligible for authoritative commit."""


@dataclass(frozen=True)
class WorldForgeCommitCertification:
    passed: bool
    content_hash: str = ""
    errors: tuple[str, ...] = ()
    checks: Mapping[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "content_hash": self.content_hash,
            "errors": list(self.errors),
            "checks": dict(self.checks),
        }


def certify_world_forge_commit(result: Any) -> WorldForgeCommitCertification:
    generation = getattr(result, "generation", None)
    audit = getattr(result, "audit", None)
    compilation = getattr(result, "compilation", None)
    document = (
        dict(getattr(compilation, "document", {}) or {})
        if compilation is not None
        else {}
    )
    content_hash = str(document.get("content_hash") or "").strip()
    metadata = dict(getattr(compilation, "metadata", {}) or {})
    missing = tuple(getattr(compilation, "missing_requirements", ()) or ())
    failed_topics = tuple(getattr(generation, "failed_topic_ids", ()) or ())
    checks = {
        "generation_passed": bool(getattr(generation, "passed", False)),
        "no_failed_topics": not failed_topics,
        "audit_passed": bool(getattr(audit, "passed", False)),
        "compiler_launch_ready": bool(
            getattr(compilation, "launch_ready", False)
        ),
        "no_missing_requirements": not missing,
        "content_hash_present": content_hash.startswith("sha256:"),
        "compiler_hash_matches": str(metadata.get("content_hash") or "")
        == content_hash,
        "aggregate_launch_ready": bool(getattr(result, "launch_ready", False)),
    }
    errors = tuple(name for name, passed in checks.items() if not passed)
    return WorldForgeCommitCertification(
        passed=not errors,
        content_hash=content_hash,
        errors=errors,
        checks=checks,
    )


def require_world_forge_commit_ready(result: Any) -> WorldForgeCommitCertification:
    certification = certify_world_forge_commit(result)
    if not certification.passed:
        raise WorldForgeCommitBlockedError(
            "World Forge canon is not commit-ready: "
            + ",".join(certification.errors)
        )
    return certification
