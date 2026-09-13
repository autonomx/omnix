from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.generation_retry import _retry_closure


def test_selected_retry_does_not_expand_to_downstream_topics() -> None:
    graph = CampaignTopicGraph(
        graph_version="test",
        campaign_template="test",
        depth="standard",
        nodes=(
            CampaignTopicNode(topic_id="realm", title="Realm", category="lore"),
            CampaignTopicNode(
                topic_id="locations",
                title="Locations",
                category="lore",
                dependencies=("realm",),
            ),
            CampaignTopicNode(
                topic_id="npcs",
                title="NPCs",
                category="lore",
                dependencies=("locations",),
            ),
        ),
    )

    affected, targets = _retry_closure(graph, ("locations",))

    assert affected == ("locations",)
    assert targets == ("realm", "locations")
