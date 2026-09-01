"""Deterministic normalization for SemanticTask v2.

The LLM describes meaning. This module canonicalizes Omnix's own semantic
ontology without selecting tools, capabilities, trust policy, or execution
authority.
"""
from __future__ import annotations

from .semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
)


_NON_SOFTWARE_RELEASE_KIND_TOKENS = (
    "game",
    "film",
    "movie",
    "television",
    "tv",
    "album",
    "music",
    "book",
    "media",
    "hardware",
    "console",
)


def _retarget_nonsoftware_release(task: SemanticTask) -> bool:
    """Return true when software_release was used for an explicitly non-software release.

    Semantic normalization may repair ontology labels, but it must not guess from
    an unknown title. We only retarget when every explicit software_release
    subject kind clearly belongs to a non-software release category.
    """

    kinds = [
        str(subject.kind or "").strip().casefold()
        for subject in task.subjects
        if subject.target == "software_release" and str(subject.kind or "").strip()
    ]
    if not kinds:
        return False
    return all(
        any(token in kind for token in _NON_SOFTWARE_RELEASE_KIND_TOKENS)
        for kind in kinds
    )


def normalize_semantic_task(task: SemanticTask) -> SemanticTask:
    """Return a canonical SemanticTask without guessing new user intent."""

    retarget_nonsoftware_release = _retarget_nonsoftware_release(task)

    operations: list[SemanticOperation] = []
    seen_operations: set[tuple[str, str, str]] = set()
    for operation in task.operations:
        normalized = operation
        if retarget_nonsoftware_release and operation.target == "software_release":
            normalized = operation.model_copy(update={"target": "public_web"})
        # Explanation/composition are response semantics unless composing a
        # real mailbox draft. Topical domain labels must not accidentally imply
        # execution authority.
        if operation.kind == "explain" and operation.target != "conversation":
            normalized = operation.model_copy(update={"target": "conversation"})
        elif (
            operation.kind == "compose"
            and operation.target not in {"conversation", "email"}
        ):
            normalized = operation.model_copy(update={"target": "conversation"})
        key = (
            normalized.kind,
            normalized.target,
            str(normalized.subject_reference or "").strip().casefold(),
        )
        if key not in seen_operations:
            seen_operations.add(key)
            operations.append(normalized)

    subjects: list[SemanticSubject] = []
    seen_subjects: set[tuple[str, str, str]] = set()
    for subject in task.subjects:
        normalized_subject = subject
        if retarget_nonsoftware_release and subject.target == "software_release":
            normalized_subject = subject.model_copy(update={"target": "public_web"})
        key = (
            normalized_subject.target,
            normalized_subject.reference.strip().casefold(),
            str(normalized_subject.kind or "").strip().casefold(),
        )
        if key not in seen_subjects:
            seen_subjects.add(key)
            subjects.append(normalized_subject)

    # Merge duplicate dependencies deterministically. Required dominates
    # optional and current dominates timeless.
    merged: dict[tuple[str, str], SemanticDataDependency] = {}
    order: list[tuple[str, str]] = []
    for dependency in task.data_dependencies:
        normalized_dependency = dependency
        if retarget_nonsoftware_release and dependency.target == "software_release":
            normalized_dependency = dependency.model_copy(update={"target": "public_web"})
        ref = str(normalized_dependency.subject_reference or "").strip()
        key = (normalized_dependency.target, ref.casefold())
        existing = merged.get(key)
        if existing is None:
            merged[key] = normalized_dependency
            order.append(key)
            continue
        merged[key] = existing.model_copy(
            update={
                "required": existing.required or dependency.required,
                "freshness": (
                    "current"
                    if "current" in {existing.freshness, dependency.freshness}
                    else "timeless"
                ),
                "subject_reference": (
                    existing.subject_reference or normalized_dependency.subject_reference
                ),
            }
        )

    return task.model_copy(
        update={
            "operations": operations,
            "subjects": subjects,
            "data_dependencies": [merged[key] for key in order],
        }
    )


__all__ = ["normalize_semantic_task"]
