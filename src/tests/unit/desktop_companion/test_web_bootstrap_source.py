from pathlib import Path


def test_production_web_bootstrap_initializes_complete_desktop_companion_stack() -> None:
    src_root = Path(__file__).resolve().parents[3]
    source = (src_root / "apps" / "web" / "src" / "main.tsx").read_text(encoding="utf-8")

    required = (
        "initializeDesktopCompanionWatchController",
        "initializeDesktopCompanionControls",
        "initializeDesktopCompanionTextSurface",
        "initializeDesktopCompanionShadowEvaluationController",
        "initializeDesktopCompanionOperationalGuard",
    )
    for initializer in required:
        assert initializer in source

    assert "desktop-companion-watch-controller" in source
    assert "Assistant context and Desktop Companion controllers failed to initialize" in source
