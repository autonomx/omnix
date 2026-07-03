from app.assistant_tools.contacts_adapter import ContactRecord, FakeContactsRuntimeAdapter, run_contacts_tool_request
from app.assistant_tools.models import AssistantToolRequest


def test_fake_contacts_adapter_searches_records():
    adapter = FakeContactsRuntimeAdapter(
        contacts=[ContactRecord(id="c1", name="Ada Lovelace", email="ada@example.com")]
    )

    matches = adapter.search_contacts("Ada")

    assert len(matches) == 1
    assert matches[0].name == "Ada Lovelace"


def test_contacts_request_returns_matching_records():
    adapter = FakeContactsRuntimeAdapter(
        contacts=[ContactRecord(id="c1", name="Ada Lovelace", email="ada@example.com")]
    )

    result = run_contacts_tool_request(
        AssistantToolRequest(tool_id="contacts", action_id="contacts.search_contacts", input={"query": "Ada"}),
        adapter,
    )

    assert result.error is None
    assert result.output["contacts"][0]["name"] == "Ada Lovelace"
