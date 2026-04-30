"""
Pytest configuration for RPG tests.
Adds project root and source directories to sys.path for imports.
"""
import sys
from pathlib import Path

# Add project roots to path for importing app modules
TESTS_DIR = Path(__file__).resolve().parent
APP_DIR = TESTS_DIR.parent.parent  # src/app/
SRC_DIR = APP_DIR.parent  # src/
PROJECT_ROOT = SRC_DIR.parent  # f:\LLM\omnix

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(TESTS_DIR))