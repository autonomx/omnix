import subprocess
import sys


def test_campaign_director_manual_scenario_runner_does_not_crash_on_turn_record_name():
    cmd = [
        sys.executable,
        "src/tests/rpg/manual_llm_transcript.py",
        "--service-scenarios",
        "--artifact-detail",
        "full",
        "--scenario",
        "campaign_director_no_story_pack_rules_noops",
        "--scenario-workers",
        "1",
        "--fail-on-regression-warnings",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=120)

    combined = result.stdout + "\n" + result.stderr
    assert result.returncode == 0, combined
    assert "NameError: name 'turn_summary' is not defined" not in combined
    assert "scenario_count: 1" in combined or '"scenario_count": 1' in combined