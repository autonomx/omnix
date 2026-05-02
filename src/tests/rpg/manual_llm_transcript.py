from __future__ import annotations

import os
import sys

# Preserve historical behavior: allow running this script directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tests.rpg.manual.cli import main


if __name__ == "__main__":
    main()
