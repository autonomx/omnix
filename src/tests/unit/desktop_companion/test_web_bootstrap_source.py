from pathlib import Path


def test_production_web_bootstrap_initializes_complete_desktop_companion_stack() -> None:
    src_root = Path(__file__).resolve().parents[3]
    web_root = src_root.parent / "web" / "src"
    # The assistant module's runtime (WP-9.7) starts the companion stack; its
    # controls and text surface are React components (WP-9.4).
    runtime = (web_root / "features" / "assistant" / "runtime.ts").read_text(encoding="utf-8")
    manifest = (web_root / "features" / "assistant" / "module.ts").read_text(encoding="utf-8")
    view_runtime = (web_root / "app" / "viewRuntime.ts").read_text(encoding="utf-8")
    router = (web_root / "app" / "router.tsx").read_text(encoding="utf-8")

    required = (
        "initializeDesktopCompanionWatchController",
        "initializeDesktopCompanionDeliveryController",
        "initializeDesktopCompanionExpressionEnricher",
        "initializeDesktopCompanionShadowEvaluationController",
        "initializeDesktopCompanionOperationalGuard",
    )
    for initializer in required:
        assert initializer in runtime

    assert "desktop-companion-watch-controller" in runtime
    assert "activateAssistantRuntime" in manifest
    assert "activateViewRuntime(activeModuleId, { queryClient })" in router
    assert "workspace runtime failed to initialize" in view_runtime
