from pathlib import Path


def test_production_web_bootstrap_initializes_complete_desktop_companion_stack() -> None:
    src_root = Path(__file__).resolve().parents[3]
    web_root = src_root / "apps" / "web" / "src"
    runtime = (web_root / "app" / "viewRuntime.ts").read_text(encoding="utf-8")
    router = (web_root / "app" / "router.tsx").read_text(encoding="utf-8")

    required = (
        "initializeDesktopCompanionWatchController",
        "initializeDesktopCompanionControls",
        "initializeDesktopCompanionTextSurface",
        "initializeDesktopCompanionShadowEvaluationController",
        "initializeDesktopCompanionOperationalGuard",
    )
    for initializer in required:
        assert initializer in runtime

    assert "desktop-companion-watch-controller" in runtime
    assert "initializeChatRuntime(queryClient)" in runtime
    assert "initializeViewRuntime(activeModule.id, queryClient)" in router
    assert "workspace runtime failed to initialize" in runtime
