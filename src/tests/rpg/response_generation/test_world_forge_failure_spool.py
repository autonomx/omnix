from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.generation_failure_spool import (
    FailureSpoolingWorldForgeGenerator,
    ReplayedGenerationFailure,
    delete_failure_spool,
    read_failure_spool,
)
from app.rpg.worlds.generation_worker import _topic_generator_for_job


class _FailingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: dict,
        dependency_topics: dict[str, GeneratedTopic],
    ) -> GeneratedTopic:
        del node, seed, campaign_context, dependency_topics
        self.calls += 1
        raise RuntimeError("provider returned malformed setting rules")


def _job(attempt_count: int) -> dict:
    return {
        "id": "job:setting-rules",
        "attempt_count": attempt_count,
        "input_payload": {
            "run_id": "run:1",
            "world_id": "world:1",
            "draft_revision": 1,
            "topic": {"topic_id": "setting_rules"},
            "dependency_hashes": {},
            "dependency_trust": {},
            "settings": {
                "provider_route": "lmstudio",
                "model": "local-model",
            },
        },
    }


def test_provider_failure_is_replayed_without_second_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR", str(tmp_path))
    underlying = _FailingGenerator()
    first = FailureSpoolingWorldForgeGenerator(
        underlying,
        job_id="job:setting-rules",
        run_id="run:1",
        world_id="world:1",
        draft_revision=1,
        topic_id="setting_rules",
        dependency_hashes={},
        dependency_trust={},
    )

    with pytest.raises(RuntimeError, match="malformed setting rules"):
        first.generate(
            CampaignTopicNode("setting_rules", "Setting Rules", "lore"),
            seed=3,
            campaign_context={},
            dependency_topics={},
        )

    assert underlying.calls == 1
    stored = read_failure_spool("job:setting-rules")
    assert stored is not None
    assert stored["topic_id"] == "setting_rules"
    assert stored["validation"]["status"] == "failed"
    assert stored["error_message"] == "provider returned malformed setting rules"

    replay = _topic_generator_for_job(_job(attempt_count=2), underlying)
    with pytest.raises(ReplayedGenerationFailure, match="malformed setting rules"):
        replay.generate(
            CampaignTopicNode("setting_rules", "Setting Rules", "lore"),
            seed=3,
            campaign_context={},
            dependency_topics={},
        )

    assert underlying.calls == 1
    delete_failure_spool("job:setting-rules")
