from app.rpg.image_contracts import ImagePromptFacts, build_image_prompt_contract, empty_image_queue, image_queue_report


def test_prompt_uses_facts():
    contract = build_image_prompt_contract("job1", "scene", ImagePromptFacts("market", npc_ids=("bran",)))
    assert "location:market" in contract.prompt
    assert "npcs:bran" in contract.prompt


def test_queue_report_counts_jobs():
    queue = empty_image_queue().enqueue(build_image_prompt_contract("job1", "scene", ImagePromptFacts("market")))
    payload = image_queue_report(queue)
    assert payload["job_count"] == 1
    assert payload["pending_count"] == 1
