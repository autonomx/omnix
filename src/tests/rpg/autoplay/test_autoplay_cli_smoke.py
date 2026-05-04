import subprocess
import sys
from pathlib import Path


def test_autoplay_cli_fallback_smoke(tmp_path: Path):
    cmd = [
        sys.executable,
        "src/tests/rpg/autoplay_llm_campaign.py",
        "--turns",
        "2",
        "--player-agent",
        "fallback",
        "--artifact-detail",
        "full",
        "--output-dir",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "turns_executed: 2" in result.stdout
    assert (tmp_path / "autoplay-campaign-results.zip").exists()