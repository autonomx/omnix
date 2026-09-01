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


def normalize_semantic_task(task: SemanticTask) -> SemanticTask:
    """Return a canonical SemanticTask without guessing new user intent."""

    operations: list[SemanticOperation] = []
    seen_operations: set[tuple[str, str, str]] = set()
    for operation in task.operations:
        normalized = operation
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
        key = (
            subject.target,
            subject.reference.strip().casefold(),
            str(subject.kind or "").strip().casefold(),
        )
        if key not in seen_subjects:
            seen_subjects.add(key)
            subjects.append(subject)

    # Merge duplicate dependencies deterministically. Required dominates
    # optional and current dominates timeless.
    merged: dict[tuple[str, str], SemanticDataDependency] = {}
    order: list[tuple[str, str]] = []
    for dependency in task.data_dependencies:
        ref = str(dependency.subject_reference or "").strip()
        key = (dependency.target, ref.casefold())
        existing = merged.get(key)
        if existing is None:
            merged[key] = dependency
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
                    existing.subject_reference or dependency.subject_reference
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
