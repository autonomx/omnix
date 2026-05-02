from __future__ import annotations

from pathlib import Path
from typing import List

from app.runtime_paths import resources_data_root

MANUAL_LOG_MAX_CHUNK_BYTES = 1_000_000
MANUAL_LOG_CHUNK_SOFT_BYTES = 850_000
MANUAL_LOG_CHUNK_DIR_NAME = "chunks"
MANUAL_HTML_DIR_NAME = "html"
MANUAL_HTML_SCENARIO_DIR_NAME = "scenarios"
MANUAL_HTML_JSON_PREVIEW_CHARS = 160_000

TEST_RESULTS_ROOT = resources_data_root() / "test-results"
TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = TEST_RESULTS_ROOT / "manual_rpg_llm_transcript.txt"
SERVICE_OUTPUT_PATH = TEST_RESULTS_ROOT / "manual_rpg_service_scenarios_all.txt"
CODE_DIFF_PATH = TEST_RESULTS_ROOT / "code-diff.txt"
RESULTS_ZIP_PATH = TEST_RESULTS_ROOT / "manual-rpg-test-results.zip"
TOKEN_USAGE_PATH = TEST_RESULTS_ROOT / "token-usage.txt"
CONVERSATION_PATH = TEST_RESULTS_ROOT / "conversation.html"

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"

RPG_SESSION_DIRS = [
    REPO_ROOT / "resources" / "data" / "rpg_sessions",
    REPO_ROOT / "data" / "rpg_sessions",
]

DEFAULT_MANAGED_SERVER_HEALTH_URLS: List[str] = []
DEFAULT_CODE_DIFF_ROOTS = ["src"]

CODE_DIFF_EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "test-results",
}

MANUAL_TEST_TURNS = [
    "I ask Bran for a room to rent",
    "I ask Bran for food",
    "I ask Bran if he has heard any rumors",
    "I ask Bran for directions to the market",
    "I follow Bran's directions to the market",
    "I ask Elara what she sells",
    "I buy a torch from Elara",
    "I ask Elara to repair my gear",
]