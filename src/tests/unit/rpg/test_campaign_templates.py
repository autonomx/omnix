"""Unit tests for Phase 13.3 — Campaign Templates."""
from app.rpg.templates.campaign_templates import (
    build_campaign_template,
    build_template_start_payload,
    list_campaign_templates,
)


def test_build_campaign_template_basic():
    template = build_campaign_template(
        template_id="template:test",
        title="Starter Adventure",
        description="A small intro",
        bootstrap={"title": "Starter"},
    )
    assert template["manifest"]["id"] == "template:test"


def test_build_template_start_payload_basic():
    result = build_template_start_payload({
        "manifest": {"id": "template:test", "title": "Starter"},
        "bootstrap": {"title": "Starter", "summary": "Intro", "visual_defaults": {}},
    })
    assert "setup_payload" in result
    assert result["template_manifest"]["id"] == "template:test"


def test_list_campaign_templates_sorted():
    templates = list_campaign_templates([
        {"manifest": {"id": "b", "title": "Beta"}, "bootstrap": {}},
        {"manifest": {"id": "a", "title": "Alpha"}, "bootstrap": {}},
    ])
    assert templates[0]["manifest"]["title"] == "Alpha"