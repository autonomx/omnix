from __future__ import annotations

from pathlib import Path

from app.desktop_companion.build_identity import resolve_desktop_companion_build_identity


def test_build_identity_prefers_explicit_omnix_commit_sha() -> None:
    result = resolve_desktop_companion_build_identity(
        environ={
            "OMNIX_COMMIT_SHA": "abcdef0123456789",
            "OMNIX_APP_VERSION": "2.3.4",
        },
        repo_root=Path("/not-used"),
    )

    assert result.exact_commit_sha == "abcdef0123456789"
    assert result.app_version == "2.3.4"
    assert result.source == "environment:omnix_commit_sha"


def test_build_identity_falls_back_without_exposing_paths(tmp_path: Path) -> None:
    result = resolve_desktop_companion_build_identity(
        environ={},
        repo_root=tmp_path,
    )

    assert result.exact_commit_sha == "unknown-local-build"
    assert result.app_version == "1.0.0"
    assert result.source == "fallback"
