from app.assistant_tools.contacts_adapter import ContactRecord, FakeContactsRuntimeAdapter


def test_fake_contacts_adapter_searches_records():
    adapter = FakeContactsRuntimeAdapter(
        contacts=[ContactRecord(id="c1", name="Ada Lovelace", email="ada@example.com")]
    )

    matches = adapter.search_contacts("Ada")

    assert len(matches) == 1
    assert matches[0].name == "Ada Lovelace"
