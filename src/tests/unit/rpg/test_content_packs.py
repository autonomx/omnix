from app.rpg.modding.content_packs import (
    apply_content_pack,
    build_pack_application_preview,
    ensure_content_pack_state,
    install_content_pack,
    list_content_packs,
)


def test_ensure_content_pack_state():
    result = ensure_content_pack_state({"presentation_state": {}})
    modding_state = result["presentation_state"]["modding_state"]
    assert modding_state["installed_packs"] == []


def test_install_and_list_content_packs():
    simulation_state = {"presentation_state": {}}
    simulation_state = install_content_pack(
        simulation_state,
        {
            "manifest": {"id": "pack:test", "title": "Test Pack"},
            "characters": [],
        },
    )
    packs = list_content_packs(simulation_state)
    assert len(packs) == 1
    assert packs[0]["manifest"]["id"] == "pack:test"


def test_build_pack_application_preview():
    preview = build_pack_application_preview(
        {
            "manifest": {"id": "pack:test", "title": "Test Pack"},
            "characters": [{"name": "Captain Elira"}],
        }
    )
    assert preview["manifest"]["id"] == "pack:test"
    assert preview["character_count"] == 1


def test_apply_content_pack_updates_visual_defaults():
    simulation_state = {"presentation_state": {"visual_state": {"defaults": {}}}}
    simulation_state = apply_content_pack(
        simulation_state,
        {
            "manifest": {"id": "pack:visual", "title": "Visual Pack"},
            "visual_defaults": {"portrait_style": "grimdark"},
        },
    )
    defaults = simulation_state["presentation_state"]["visual_state"]["defaults"]
    assert defaults["portrait_style"] == "grimdark"


def test_normalize_pack_manifest_defaults():
    pack = {
        "manifest": {},
    }
    simulation_state = install_content_pack({"presentation_state": {}}, pack)
    packs = list_content_packs(simulation_state)
    assert len(packs) == 1
    manifest = packs[0]["manifest"]
    assert manifest["version"] == "1.0"
    assert manifest["pack_type"] == "mixed"
    assert manifest["id"] == ""
    assert manifest["title"] == ""


def test_packs_sorted_by_title():
    simulation_state = {"presentation_state": {}}
    simulation_state = install_content_pack(
        simulation_state,
        {"manifest": {"id": "b", "title": "Beta Pack"}, "characters": []},
    )
    simulation_state = install_content_pack(
        simulation_state,
        {"manifest": {"id": "a", "title": "Alpha Pack"}, "characters": []},
    )
    packs = list_content_packs(simulation_state)
    assert len(packs) == 2
    assert packs[0]["manifest"]["title"] == "Alpha Pack"
    assert packs[1]["manifest"]["title"] == "Beta Pack"


def test_packs_limited_to_max():
    simulation_state = {"presentation_state": {}}
    for i in range(50):
        simulation_state = install_content_pack(
            simulation_state,
            {"manifest": {"id": f"pack:{i}", "title": f"Pack {i}"}, "characters": []},
        )
    packs = list_content_packs(simulation_state)
    assert len(packs) <= 32  # _MAX_PACKS