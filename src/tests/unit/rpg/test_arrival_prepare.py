"""The arrival's local map is read while travel resolves (evolution roadmap EV-7): the turn then finds it read, and
reads nothing again; a destination the journey did not reach is never used."""
from __future__ import annotations

from app.apps.rpg.session.turn import local_map


def test_the_destinations_map_is_read_beside_travel_and_used_once(monkeypatch) -> None:
    reads: list[str] = []
    monkeypatch.setattr(local_map, "_existing", lambda session, target: reads.append(target) or ("definition", "snap"))
    document = {"simulation_state": {"world_model": {"locations": {"loc:far": {"map_id": "map:far"}}}}, "state": {}}
    local_map.prepare_arrival("rpg_1", document, "loc:far")
    target = local_map.map_instance_id_for("rpg_1", "map:far")
    assert local_map._prepared("rpg_1", target) == ("existing", ("definition", "snap"))
    assert reads == [target]
    assert local_map._prepared("rpg_1", target) is None  # used once
    local_map.prepare_arrival("rpg_1", document, "loc:nowhere")  # no grid there: nothing to read
    assert reads == [target]
