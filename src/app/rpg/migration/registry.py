"""Phase 8.5 — Migration Registry.

Central migration step registry with deterministic ordering of version hops.
Operates on serialized dicts, not live objects.
"""

from __future__ import annotations

from typing import Any, Callable

from .models import (
    CURRENT_PACK_FORMAT_VERSION,
    CURRENT_SAVE_FORMAT_VERSION,
    SUPPORTED_MIGRATION_SCOPES,
    MigratedPayload,
    MigrationReport,
    MigrationStep,
)


class MigrationRegistry:
    """Central registry of version migration steps.

    Steps are keyed by *scope* (``"save"`` or ``"pack"``) and
    *from_version*.  Only +1 version hops are allowed to keep migration
    paths deterministic and easy to reason about.

    Each registered callable receives a ``dict`` payload and must return
    a ``(dict, dict)`` tuple of ``(migrated_payload, step_metadata)``.
    """

    def __init__(self) -> None:
        self._save_steps: dict[int, tuple[int, Callable[[dict], tuple[dict, dict]], MigrationStep]] = {}
        self._pack_steps: dict[int, tuple[int, Callable[[dict], tuple[dict, dict]], MigrationStep]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_save_step(
        self,
        from_version: int,
        to_version: int,
        fn: Callable[[dict], tuple[dict, dict]],
        *,
        name: str = "",
        description: str = "",
    ) -> None:
        """Register a save migration step from *from_version* to *to_version*."""
        if to_version != from_version + 1:
            raise ValueError(
                f"Only +1 version hops allowed: {from_version} -> {to_version}"
            )
        if from_version in self._save_steps:
            raise ValueError(
                f"Duplicate save migration step for version {from_version}"
            )
        step = MigrationStep(
            from_version=from_version,
            to_version=to_version,
            scope="save",
            name=name or f"save_{from_version}_to_{to_version}",
            description=description,
        )
        self._save_steps[from_version] = (to_version, fn, step)

    def register_pack_step(
        self,
        from_version: int,
        to_version: int,
        fn: Callable[[dict], tuple[dict, dict]],
        *,
        name: str = "",
        description: str = "",
    ) -> None:
        """Register a pack migration step from *from_version* to *to_version*."""
        if to_version != from_version + 1:
            raise ValueError(
                f"Only +1 version hops allowed: {from_version} -> {to_version}"
            )
        if from_version in self._pack_steps:
            raise ValueError(
                f"Duplicate pack migration step for version {from_version}"
            )
        step = MigrationStep(
            from_version=from_version,
            to_version=to_version,
            scope="pack",
            name=name or f"pack_{from_version}_to_{to_version}",
            description=description,
        )
        self._pack_steps[from_version] = (to_version, fn, step)

    # ------------------------------------------------------------------
    # Path computation
    # ------------------------------------------------------------------

    def _get_steps(self, scope: str) -> dict[int, tuple[int, Callable, MigrationStep]]:
        if scope == "save":
            return self._save_steps
        if scope == "pack":
            return self._pack_steps
        raise ValueError(f"Unsupported migration scope: {scope!r}")

    def get_save_path(self, from_version: int, to_version: int) -> list[MigrationStep]:
        """Return the ordered list of save migration steps."""
        return self._build_path("save", from_version, to_version)

    def get_pack_path(self, from_version: int, to_version: int) -> list[MigrationStep]:
        """Return the ordered list of pack migration steps."""
        return self._build_path("pack", from_version, to_version)

    def _build_path(self, scope: str, from_version: int, to_version: int) -> list[MigrationStep]:
        steps_map = self._get_steps(scope)
        path: list[MigrationStep] = []
        current = from_version
        while current < to_version:
            entry = steps_map.get(current)
            if entry is None:
                return []  # gap — no path
            _next_ver, _fn, step = entry
            path.append(step)
            current = _next_ver
        return path

    def has_path(self, scope: str, from_version: int, to_version: int) -> bool:
        """Return ``True`` if a migration path exists for the given scope/range."""
        if from_version == to_version:
            return True
        if from_version > to_version:
            return False
        if scope not in SUPPORTED_MIGRATION_SCOPES:
            return False
        path = self._build_path(scope, from_version, to_version)
        return len(path) > 0

    # ------------------------------------------------------------------
    # Migration execution
    # ------------------------------------------------------------------

    def migrate(
        self,
        scope: str,
        payload: dict[str, Any],
        from_version: int,
        to_version: int,
    ) -> MigratedPayload:
        """Apply all migration steps from *from_version* to *to_version*.

        Returns a :class:`MigratedPayload` with the transformed payload
        and a detailed :class:`MigrationReport`.
        """
        report = MigrationReport(
            scope=scope,
            original_version=from_version,
        )

        if scope not in SUPPORTED_MIGRATION_SCOPES:
            report.errors.append(f"Unsupported migration scope: {scope!r}")
            report.final_version = from_version
            return MigratedPayload(payload=dict(payload), report=report)

        if from_version == to_version:
            report.final_version = to_version
            return MigratedPayload(payload=dict(payload), report=report)

        if from_version > to_version:
            report.errors.append(
                f"Downgrade not supported: {from_version} -> {to_version}"
            )
            report.final_version = from_version
            return MigratedPayload(payload=dict(payload), report=report)

        steps_map = self._get_steps(scope)
        current = from_version
        current_payload = dict(payload)

        while current < to_version:
            entry = steps_map.get(current)
            if entry is None:
                report.errors.append(
                    f"No migration step for {scope} version {current} -> {current + 1}"
                )
                break
            next_ver, fn, step = entry
            pre_keys = set(current_payload.keys())
            try:
                migrated, step_meta = fn(current_payload)
            except Exception as exc:
                report.errors.append(
                    f"Migration step {step.name} failed: {exc}"
                )
                break
            post_keys = set(migrated.keys())
            changed = sorted(post_keys.symmetric_difference(pre_keys))
            if changed:
                report.changed_keys.extend(changed)

            report.applied_steps.append({
                "name": step.name,
                "from_version": step.from_version,
                "to_version": step.to_version,
                "metadata": step_meta,
            })
            current_payload = migrated
            current = next_ver

        report.final_version = current
        return MigratedPayload(payload=current_payload, report=report)
