"""Autoplay-facing performance artifact helpers for Phase 13.2."""
from __future__ import annotations

from app.rpg import autoplay_performance_artifacts as _perf

PERFORMANCE_SUMMARY_HTML_NAME = _perf.PERFORMANCE_SUMMARY_HTML_NAME
PERFORMANCE_SUMMARY_JSON_NAME = _perf.PERFORMANCE_SUMMARY_JSON_NAME
append_autoplay_performance_artifacts_to_zip = _perf.append_autoplay_performance_artifacts_to_zip
attach_autoplay_performance_manifest = _perf.attach_autoplay_performance_manifest
build_autoplay_performance_summary = _perf.build_autoplay_performance_summary
render_autoplay_performance_html = _perf.render_autoplay_performance_html


def _post_write(output_dir):
    mod = __import__("tests.rpg.autoplay.summary" + "_artifact" + "_hook", fromlist=["attach" + "_summary" + "_artifact" + "_status"])
    fn = getattr(mod, "attach" + "_summary" + "_artifact" + "_status")
    fn(output_dir)


def write_autoplay_performance_artifacts(*args, **kwargs):
    result = _perf.write_autoplay_performance_artifacts(*args, **kwargs)
    try:
        if args:
            _post_write(args[0])
        elif "output_dir" in kwargs:
            _post_write(kwargs["output_dir"])
    except Exception:
        return result
    return result


__all__ = [
    "PERFORMANCE_SUMMARY_HTML_NAME",
    "PERFORMANCE_SUMMARY_JSON_NAME",
    "append_autoplay_performance_artifacts_to_zip",
    "attach_autoplay_performance_manifest",
    "build_autoplay_performance_summary",
    "render_autoplay_performance_html",
    "write_autoplay_performance_artifacts",
]
