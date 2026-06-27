"""Voice Studio language normalization tests."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.jobs.voice_inline import _tts_language_code


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("en", "en"),
        ("en-US", "en"),
        ("English", "en"),
        ("English (US)", "en"),
        ("English (UK)", "en"),
        ("Spanish (Spain)", "es"),
        ("French", "fr"),
        ("Klingon", "Klingon"),
    ],
)
def test_tts_language_code_normalizes_ui_labels(label, expected):
    assert _tts_language_code(label) == expected
