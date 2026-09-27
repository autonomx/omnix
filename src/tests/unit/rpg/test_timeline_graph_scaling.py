from app.rpg.core.timeline_graph import TimelineGraph


def test_new_events_do_not_scan_existing_roots():
    class RootsWithoutMembershipScan(list):
        def __contains__(self, _value):
            raise AssertionError("new event must use the node identity index")

    graph = TimelineGraph()
    graph.roots = RootsWithoutMembershipScan()
    for index in range(500):
        graph.add_event(f"root:{index}", None)
    graph.add_event("child", "root:0")
    graph.add_event("root:0", None)
    assert graph.node_count() == 501
    assert graph.get_roots() == [f"root:{index}" for index in range(500)]
    assert graph.get_branch("child") == ["root:0", "child"]
