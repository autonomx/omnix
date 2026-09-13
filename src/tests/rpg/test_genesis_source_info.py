from app.rpg.session.genesis.source_info import (
    DEFAULT_SOURCE_BUILD,
    WIZARD_SOURCE_KIND,
    WIZARD_SOURCE_NAME,
    genesis_source_info,
    source_payload,
    wizard_source_payload,
)


def test_wizard_source_payload_is_stable() -> None:
    payload = wizard_source_payload()

    assert payload == {
        "source_build": DEFAULT_SOURCE_BUILD,
        "source_kind": WIZARD_SOURCE_KIND,
        "source_name": WIZARD_SOURCE_NAME,
    }


def test_source_info_can_describe_another_origin() -> None:
    info = genesis_source_info(
        source_kind="scenario_template_v1",
        source_name="fixture_start",
        source_build="1",
    )

    assert source_payload(info) == {
        "source_build": "1",
        "source_kind": "scenario_template_v1",
        "source_name": "fixture_start",
    }
