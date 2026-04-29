from app.runtime_paths import (
    generated_images_root,
    repo_root,
    resources_data_root,
    rpg_npc_profiles_root,
    rpg_sessions_root,
    test_results_root,
)


def test_resources_data_root_is_repo_root_not_src():
    root = repo_root()
    data_root = resources_data_root()

    assert data_root == root / "resources" / "data"
    assert "src" not in data_root.relative_to(root).parts


def test_rpg_sessions_root_is_under_repo_resources_data():
    root = repo_root()
    sessions_root = rpg_sessions_root()

    assert sessions_root == root / "resources" / "data" / "rpg_sessions"
    assert "src" not in sessions_root.relative_to(root).parts


def test_npc_profiles_root_is_under_repo_resources_data():
    root = repo_root()
    profiles_root = rpg_npc_profiles_root()

    assert profiles_root == root / "resources" / "data" / "rpg_npc_profiles"
    assert "src" not in profiles_root.relative_to(root).parts


def test_generated_images_root_is_under_repo_resources_data():
    root = repo_root()
    images_root = generated_images_root()

    assert images_root == root / "resources" / "data" / "generated_images"
    assert "src" not in images_root.relative_to(root).parts


def test_test_results_root_is_under_repo_resources_data():
    root = repo_root()
    results_root = test_results_root()

    assert results_root == root / "resources" / "data" / "test-results"
    assert "src" not in results_root.relative_to(root).parts


def test_no_bad_src_runtime_data_directories_exist():
    root = repo_root()

    bad_paths = [
        root / "src" / "data" / "rpg_sessions",
        root / "src" / "resources" / "data",
        root / "src" / "data" / "generated_images",
        root / "src" / "resources" / "data" / "rpg_npc_profiles",
    ]

    existing = [str(path) for path in bad_paths if path.exists()]
    assert not existing, "Runtime data must not live under src: " + ", ".join(existing)