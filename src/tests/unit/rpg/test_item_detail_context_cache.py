from app.persistence.tenant import TenantContext
from app.rpg.session import item_detail


def test_item_detail_context_is_read_for_each_tenant(monkeypatch) -> None:
    contexts = [
        TenantContext(
            user_id="user:first",
            workspace_id="workspace:first",
            membership_id="membership:first",
            roles=frozenset({"owner"}),
        ),
        TenantContext(
            user_id="user:second",
            workspace_id="workspace:second",
            membership_id="membership:second",
            roles=frozenset({"owner"}),
        ),
    ]
    database = object()
    monkeypatch.setattr(item_detail, "default_database", lambda: database)
    monkeypatch.setattr(item_detail, "current_tenant", lambda: contexts.pop(0))

    first_database, first_context = item_detail._description_database_context()
    second_database, second_context = item_detail._description_database_context()

    assert first_database is database
    assert second_database is database
    assert first_context.workspace_id == "workspace:first"
    assert second_context.workspace_id == "workspace:second"
