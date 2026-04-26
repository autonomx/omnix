from tests.rpg import manual_llm_transcript as transcript


def test_scoped_session_id_defaults_to_run_scoped():
    assert (
        transcript._scoped_session_id("manual_test_session", "run123")
        == "manual_test_session_run123"
    )


def test_scoped_session_id_can_use_stable_legacy_id():
    assert (
        transcript._scoped_session_id(
            "manual_test_session",
            "run123",
            stable=True,
        )
        == "manual_test_session"
    )


def test_manual_service_session_id_defaults_to_run_scoped():
    assert (
        transcript._manual_service_session_id("shop_success", "run123")
        == "manual_service_shop_success_run123"
    )


def test_manual_service_session_id_can_use_stable_legacy_id():
    assert (
        transcript._manual_service_session_id(
            "shop_success",
            "run123",
            stable=True,
        )
        == "manual_service_shop_success"
    )</content>
<parameter name="filePath">src/app/rpg/tests/test_manual_transcript_session_isolation.py