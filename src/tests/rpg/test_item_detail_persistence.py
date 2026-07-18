from __future__ import annotations

from app.rpg.session import item_detail


class _Gateway:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate(self, prompt, *, context, timeout_s):
        self.calls += 1
        assert "inventory item" in prompt
        assert context["item"]["name"] == "Trail Rations"
        assert timeout_s == 20.0
        return self.response


def _state() -> dict:
    return {
        "current_location": "Rusty Flagon Tavern",
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "inventory": [
                {
                    "id": "trail_rations",
                    "name": "Trail Rations",
                    "type": "consumable",
                    "quantity": 3,
                    "tags": ["food", "travel"],
                }
            ]
        },
    }


def test_item_detail_reuses_persisted_description_without_calling_llm(monkeypatch) -> None:
    gateway = _Gateway("This should not be used.")
    monkeypatch.setattr(
        item_detail,
        "_read_persisted_description",
        lambda _key: ({"summary": "Hard-baked travel cakes wrapped for the road."}, None),
    )

    result = item_detail.generate_item_detail(
        _state(),
        "Trail Rations",
        llm_gateway=gateway,
    )

    assert result["ok"] is True
    assert result["item_detail"]["source"] == "postgresql_cache"
    assert result["item_detail"]["summary"] == "Hard-baked travel cakes wrapped for the road."
    assert result["description_persistence"]["cache_hit"] is True
    assert gateway.calls == 0


def test_new_item_detail_is_generated_and_persisted(monkeypatch) -> None:
    gateway = _Gateway(
        "These compact travel cakes are baked from coarse grain and dried fruit. "
        "Their browned edges and tight wrapping make them durable enough for saddlebags. "
        "Road wardens and caravan hands commonly carry them between settlements."
    )
    writes = []
    monkeypatch.setattr(item_detail, "_read_persisted_description", lambda _key: (None, None))

    def _persist(**payload):
        writes.append(payload)
        return ({"summary": payload["summary"]}, None)

    monkeypatch.setattr(item_detail, "_persist_description", _persist)

    result = item_detail.generate_item_detail(
        _state(),
        "Trail Rations",
        llm_gateway=gateway,
    )

    assert result["ok"] is True
    assert result["item_detail"]["source"] == "llm"
    assert result["description_persistence"]["status"] == "stored"
    assert result["description_persistence"]["cache_hit"] is False
    assert gateway.calls == 1
    assert len(writes) == 1
    assert writes[0]["item_key"] == "trail_rations"
    assert len(writes[0]["description_key"]) == 64
