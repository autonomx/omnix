from tests.rpg.autoplay_llm_campaign import build_arg_parser


def test_legacy_http_flags_still_parse_but_are_not_default_runtime():
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--turns",
            "1",
            "--player-agent",
            "fallback",
            "--start-app-server",
            "--server-startup-timeout",
            "7",
        ]
    )

    assert args.start_app_server is True
    assert args.server_startup_timeout == 7