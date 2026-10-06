"""Memory v2 search matches any meaningful word of a question."""
from __future__ import annotations

import pytest

from app.platform.assistant_memory.v2.search_index import match_query


@pytest.mark.parametrize(("question", "query"), [
    ("What is my favorite game?", "favorite:* | game:*"),
    ("Where does my sister Leila live?", "sister:* | leila:* | live:*"),
    ("Do I have any food allergies?", "food:* | allergies:*"),
    ("Who is Dr. Patel?", "dr | patel:*"),
])
def test_questions_become_any_word_queries(question, query) -> None:
    assert match_query(question) == query


def test_tsquery_syntax_in_user_text_is_reduced_to_words() -> None:
    assert match_query("drop & table | x:* ! (y)") == "drop:* | table:*"


def test_a_question_of_only_common_words_matches_nothing() -> None:
    assert match_query("what is it?") is None
    assert match_query("") is None


def test_long_questions_are_capped() -> None:
    assert match_query(" ".join(f"word{index}" for index in range(100))).count("|") == 23
