import sys

from tests.rpg.autoplay.console_capture import ConsoleCapture, summarize_console_log


def test_console_capture_writes_stdout_and_stderr(tmp_path):
    path = tmp_path / "console-log.txt"
    with ConsoleCapture(output_path=path) as capture:
        print("hello stdout")
        print("hello stderr", file=sys.stderr)
        capture.write_file()

    text = path.read_text(encoding="utf-8")
    assert "hello stdout" in text
    assert "hello stderr" in text


def test_summarize_console_log_detects_turn_errors():
    summary = summarize_console_log(
        "\n".join(
            [
                "Provider discovery complete. 5 providers available",
                "TURN 1 ERROR: UnboundLocalError: cannot access local variable 'turn_contract'",
                "warning: something small",
            ]
        )
    )

    assert summary["line_count"] == 3
    assert summary["turn_error_count"] == 1
    assert summary["error_count"] >= 1
    assert summary["warning_count"] == 1
    assert "turn_contract" in summary["turn_errors"][0]


def test_console_log_summary_from_text_is_non_empty_when_logs_present():
    text = "\n".join(
        [
            "Registered provider: lmstudio",
            "Provider discovery complete. 5 providers available",
            "Submitted combined background LLM job combined_background_llm:s:1",
        ]
    )

    summary = summarize_console_log(text)

    assert summary["line_count"] == 3
    assert summary["provider_line_count"] >= 2
    assert summary["turn_error_count"] == 0


def test_console_log_file_is_in_artifact_path_list(tmp_path):
    output_dir = tmp_path
    console_log = output_dir / "console-log.txt"
    console_log.write_text("hello console", encoding="utf-8")

    assert console_log.exists()