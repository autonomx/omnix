from __future__ import annotations

from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzz_bundle_ao3_runner_self_check_compat.pyfrag"
)


def _load_bundle_ao3_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao3_runner_self_check_compat_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ao3_self_check_uses_original_runner_then_restores_wrapper():
    calls = []

    def original_runner(_args=None):
        return {"ok": True}

    def wrapper(_args=None):
        return {"ok": True, "wrapped": True}

    wrapper._bundle_ao2_wrapped = True

    def real_runner_check():
        calls.append("checked")
        assert namespace["_run_autoplay_campaign"] is original_runner
        return None

    namespace = {
        "_run_autoplay_campaign": wrapper,
        "_BUNDLE_AO2_ORIGINAL_RUN_AUTOPLAY_CAMPAIGN": original_runner,
        "_assert_real_autoplay_runner_present": real_runner_check,
    }
    namespace = _load_bundle_ao3_namespace(namespace)

    result = namespace["_assert_real_autoplay_runner_present"]()

    assert result is None
    assert calls == ["checked"]
    assert namespace["_run_autoplay_campaign"] is wrapper


def test_bundle_ao3_self_check_without_ao2_wrapper_delegates_normally():
    calls = []

    def runner(_args=None):
        return {"ok": True}

    def real_runner_check():
        calls.append(namespace["_run_autoplay_campaign"])
        return "ok"

    namespace = {
        "_run_autoplay_campaign": runner,
        "_assert_real_autoplay_runner_present": real_runner_check,
    }
    namespace = _load_bundle_ao3_namespace(namespace)

    assert namespace["_assert_real_autoplay_runner_present"]() == "ok"
    assert calls == [runner]


def test_bundle_ao3_self_check_restores_wrapper_when_original_check_raises():
    def original_runner(_args=None):
        return {"ok": True}

    def wrapper(_args=None):
        return {"ok": True, "wrapped": True}

    wrapper._bundle_ao2_wrapped = True

    def real_runner_check():
        assert namespace["_run_autoplay_campaign"] is original_runner
        raise RuntimeError("real check failed")

    namespace = {
        "_run_autoplay_campaign": wrapper,
        "_BUNDLE_AO2_ORIGINAL_RUN_AUTOPLAY_CAMPAIGN": original_runner,
        "_assert_real_autoplay_runner_present": real_runner_check,
    }
    namespace = _load_bundle_ao3_namespace(namespace)

    try:
        namespace["_assert_real_autoplay_runner_present"]()
    except RuntimeError as exc:
        assert "real check failed" in str(exc)
    else:
        raise AssertionError("expected real check failure")

    assert namespace["_run_autoplay_campaign"] is wrapper
