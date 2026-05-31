
from tests.rpg.autoplay import campaign_report
from tests.rpg.autoplay.campaign_report import (
    render_campaign_report_html,
)

def test_campaign_report_strips_legacy_autoplay_partial_shell():
    legacy = """
    <header>
      <h1>Autoplay Campaign Report <span class="status-pill">partial</span></h1>
      <nav>
        <a href="#summary">Summary</a>
        <a href="#journal">Journal</a>
      </nav>
    </header>
    <section class="hero" id="summary">
      <h2>Executive Summary</h2>
      <p>The campaign can progress through a complete tavern investigation branch.</p>
    </section>
    <section id="campaign-journal">
      <h2>Campaign Calendar & Player Journal</h2>
      <p>Keep this useful legacy section.</p>
    </section>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_partial(legacy)

    assert "Autoplay Campaign Report" not in cleaned
    assert "Executive Summary" not in cleaned
    assert "Summary</a>" not in cleaned
    assert "Campaign Calendar & Player Journal" in cleaned
    assert "Keep this useful legacy section." in cleaned


def test_campaign_report_does_not_render_old_autoplay_partial_as_separate_section():
    html = render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    # The unified hero still contains this phrase once as the run-report title.
    assert "Autoplay Campaign Report" in html
    assert 'class="rpg-hero-report"' in html

    # But the old standalone report shell must not exist at the top level.
    # Legacy data may appear in debug sections.
    debug_start = html.find('<section class="rpg-card dark')
    if debug_start != -1:
        main_html = html[:debug_start]
    else:
        main_html = html
    assert '<header class="rpg-hero"' in main_html  # The rpg-hero
    assert '<section class="hero"' not in main_html
    assert "<h2>Executive Summary</h2>" not in main_html


def test_campaign_report_debug_strips_old_shell_but_keeps_legacy_details():
    html = campaign_report._wrap_technical_debug_groups(
        {
            "campaign": """
              <header><h1>Autoplay Campaign Report <span class="status-pill">partial</span></h1></header>
              <section class="hero" id="summary"><h2>Executive Summary</h2><p>Duplicate summary.</p></section>
              <section id="campaign-journal"><h2>Campaign Calendar & Player Journal</h2><p>Useful details.</p></section>
            """
        }
    )

    assert "<header>" not in html
    assert "Executive Summary" not in html
    assert "Duplicate summary" not in html
    assert "Campaign Calendar & Player Journal" in html
    assert "Useful details" in html
    assert 'id="legacy-campaign-journal"' in html


def test_campaign_report_strips_legacy_partial_inside_body_after_debug():
    html = """
    <!doctype html>
    <html>
    <body>
      <main class="rpg-shell">
        <section class="rpg-card dark span-12" id="technical-debug">
          <h2>Technical Debug</h2>
        </section>
      </main>
      <header>
        <h1>Autoplay Campaign Report <span class="status-pill warn">partial</span></h1>
        <p>Session autoplay_abc · Strategy balanced_story_player · Turns 20</p>
        <nav>
          <a href="#summary">Summary</a>
          <a href="#campaign-journal">Journal</a>
          <a href="#quests">Quests</a>
        </nav>
      </header>
      <section class="hero" id="summary">
        <h2>Executive Summary</h2>
        <p>The campaign can progress through a complete tavern investigation branch.</p>
      </section>
    </body>
    </html>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert "Technical Debug" in cleaned
    assert "status-pill" not in cleaned
    assert "partial" not in cleaned
    assert "Summary</a>" not in cleaned
    assert "Journal</a>" not in cleaned
    assert "Executive Summary" not in cleaned
    assert "complete tavern investigation branch" not in cleaned


def test_campaign_report_legacy_tail_sanitizer_preserves_rpg_hero_report():
    html = """
    <main class="rpg-shell">
      <header class="rpg-hero" id="campaign-overview">
        <h1>The Autoplay Campaign Chronicle</h1>
        <div class="rpg-hero-report">
          <h2>Autoplay Campaign Report</h2>
          <div>Pre-Turn Attach Rate</div>
        </div>
      </header>
    </main>
    <header>
      <h1>Autoplay Campaign Report <span class="status-pill warn">partial</span></h1>
    </header>
    <section class="hero" id="summary"><h2>Executive Summary</h2></section>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert "The Autoplay Campaign Chronicle" in cleaned
    assert "rpg-hero-report" in cleaned
    assert "Pre-Turn Attach Rate" in cleaned
    assert "status-pill" not in cleaned
    assert "Executive Summary" not in cleaned


def test_campaign_report_render_output_has_no_old_partial_markers():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "rpg-hero-report" in html
    assert "Autoplay Campaign Report" in html
    assert "status-pill warn" not in html
    assert "<h2>Executive Summary</h2>" not in html
    assert "Summary</a>" not in html
    assert "Journal</a>" not in html
    assert 'id="summary"' not in html


def test_campaign_report_nav_is_split_into_primary_and_appendix_sections():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'class="rpg-nav"' in html
    assert 'class="rpg-nav-primary"' in html
    assert 'class="rpg-nav-appendix"' in html
    assert "Appendix Sections" in html

    nav_html = html.split('class="rpg-nav"', 1)[1].split("</nav>", 1)[0]

    # Primary links remain immediately visible.
    assert 'href="#campaign-overview"' in nav_html
    assert 'href="#verdict-cards"' in nav_html
    assert 'href="#adventure-timeline"' in nav_html
    assert 'href="#quest-board"' in nav_html
    assert 'href="#npc-chronicle"' in nav_html
    assert 'href="#location-journey"' in nav_html
    assert 'href="#player-sheet"' in nav_html
    assert 'href="#qa-dashboard"' in nav_html
    assert 'href="#technical-debug"' in nav_html

    # Appendix links are still present, but inside the collapsible appendix group.
    assert 'href="#campaign-journal"' in nav_html
    assert 'href="#quest-progress"' in nav_html
    assert 'href="#npc-evolution"' in nav_html
    assert 'href="#hundred-turn-eval"' in nav_html
    assert 'href="#background-result-timing"' in nav_html
    assert 'href="#performance"' in nav_html
    assert 'href="#console-log"' in nav_html
    assert 'href="#timeline"' in nav_html
    assert 'href="#debug"' in nav_html


def test_campaign_report_does_not_render_old_report_highlights_block():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'class="report-quick-links"' not in html or ".report-quick-links { display: none" in html
    assert "Campaign Journal (5)" not in html
    assert "Quest Progress (1)" not in html
    assert "NPC Evolution (1)" not in html

    assert "<h2>Report Highlights</h2>" not in html


def test_campaign_report_promoted_sections_use_rpg_theme():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'id="campaign-journal"' in html
    assert 'id="quest-progress"' in html
    assert 'id="npc-evolution"' in html
    assert 'class="rpg-card rpg-promoted-section span-12"' in html
    assert "Campaign Calendar & Player Journal" in html
    assert "Quest Progress" in html
    assert "NPC Evolution" in html


def test_campaign_report_strips_second_legacy_main_after_rpg_shell():
    html = """
    <main class="rpg-shell">
      <section id="technical-debug" class="rpg-card dark span-12">
        <h2>Technical Debug</h2>
      </section>
    </main>
    <main>
      <section id="campaign-journal"><h2>Campaign Calendar & Player Journal</h2></section>
      <section id="quest-progress"><h2>Quest Progress</h2></section>
      <section id="debug"><h2>Raw Debug Appendix</h2></section>
    </main>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert 'class="rpg-shell"' in cleaned
    assert "Technical Debug" in cleaned
    assert '<main>\n      <section id="campaign-journal"' not in cleaned
    assert 'id="campaign-journal"' not in cleaned
    assert 'id="quest-progress"' not in cleaned
    assert 'id="debug"' not in cleaned


def test_campaign_report_promoted_sections_have_high_contrast_css():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert ".rpg-promoted-section *" in html
    assert "color: #24170d !important" in html
    assert "background: #fff8e9 !important" in html
    assert "body > main:not(.rpg-shell)" in html


def test_campaign_report_appendix_nav_is_open_and_contains_extended_links():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert '<details class="rpg-nav-appendix" open>' in html
    nav_html = html.split('class="rpg-nav"', 1)[1].split("</nav>", 1)[0]
    assert 'href="#campaign-journal"' in nav_html
    assert 'href="#quest-progress"' in nav_html
    assert 'href="#npc-evolution"' in nav_html
    assert 'href="#performance"' in nav_html
    assert 'href="#console-log"' in nav_html
    assert 'href="#timeline"' in nav_html
    assert 'href="#debug"' in nav_html


def test_campaign_report_final_html_has_no_report_highlights_block():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "<h2>Report Highlights</h2>" not in html
    assert 'class="report-quick-links"' not in html
    assert "Campaign Journal (" not in html
    assert "Quest Progress (" not in html
    assert "NPC Evolution (" not in html


def test_campaign_report_strips_unsafe_file_self_links():
    html = """
    <html>
      <head>
        <base href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/">
        <meta http-equiv="refresh" content="0;url=file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html">
      </head>
      <body>
        <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html">Self</a>
        <iframe src="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html"></iframe>
        <script>
          window.location = "file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html";
          window.open("file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html");
        </script>
      </body>
    </html>
    """

    cleaned = campaign_report._strip_unsafe_file_urls_from_report_html(html)

    assert "file:///" not in cleaned
    assert "<base" not in cleaned.lower()
    assert "http-equiv=\"refresh\"" not in cleaned.lower()
    assert "<iframe" not in cleaned.lower()
    assert 'href="#campaign-overview"' in cleaned
    assert "window.location" not in cleaned
    assert "window.open" not in cleaned


def test_campaign_report_rewrites_file_artifact_links_to_relative_filenames():
    html = """
    <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-summary.json">Summary JSON</a>
    <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/console-log.txt">Console</a>
    """

    cleaned = campaign_report._strip_unsafe_file_urls_from_report_html(html)

    assert "file:///" not in cleaned
    assert 'href="autoplay-summary.json"' in cleaned
    assert 'href="console-log.txt"' in cleaned


def test_campaign_report_rendered_html_has_no_file_urls():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert "file:///" not in html
    assert "file:\\" not in html
    assert "<base " not in html.lower()
    assert "<iframe" not in html.lower()
    assert "window.location" not in html
    assert "window.open" not in html
    assert len(html) > 1000


def test_campaign_report_render_returns_non_empty_html_document():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert isinstance(html, str)
    assert len(html) > 1000
    assert "<!doctype html>" in html.lower()
    assert "rpg-shell" in html
    assert "The Autoplay Campaign Chronicle" in html
    assert "Autoplay Campaign Report" in html


def test_campaign_report_finalizer_does_not_blank_valid_html():
    html_doc = """<!doctype html>
    <html>
      <body>
        <main class="rpg-shell">
          <header class="rpg-hero" id="campaign-overview">
            <h1>The Autoplay Campaign Chronicle</h1>
          </header>
        </main>
      </body>
    </html>
    """

    finalized = campaign_report._finalize_campaign_report_html(html_doc)

    assert len(finalized) > 100
    assert "rpg-shell" in finalized
    assert "The Autoplay Campaign Chronicle" in finalized


def test_campaign_report_write_outputs_non_empty_html(tmp_path):
    result = campaign_report.write_campaign_report(
        output_dir=tmp_path,
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        health={},
    )

    html_path = tmp_path / "autoplay-campaign-report.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert len(html) > 1000
    assert "rpg-shell" in html
    assert "file:///" not in html
    assert result["campaign_report_html"].endswith("autoplay-campaign-report.html")


def test_campaign_report_render_returns_full_rpg_html_document():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert isinstance(html, str)
    assert len(html) > 1000
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<html" in html.lower()
    assert "<head>" in html.lower()
    assert "<style>" in html.lower()
    assert "<body>" in html.lower()
    assert 'class="rpg-shell"' in html
    assert "The Autoplay Campaign Chronicle" in html
    assert "Autoplay Campaign Report" in html


def test_campaign_report_render_does_not_start_with_legacy_fragment():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    start = html.lstrip()[:300].lower()
    assert not start.startswith("<section")
    assert 'id="player"' not in start
    assert 'id="console-log"' not in start
    assert 'id="debug"' not in start
    assert start.startswith("<!doctype html>")


def test_campaign_report_render_contains_rpg_css():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "--rpg-bg" in html
    assert ".rpg-shell" in html
    assert ".rpg-hero" in html
    assert ".rpg-card" in html
    assert ".rpg-promoted-section" in html


def test_campaign_report_write_outputs_full_html_document(tmp_path):
    result = campaign_report.write_campaign_report(
        output_dir=tmp_path,
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        health={},
    )

    html_path = tmp_path / "autoplay-campaign-report.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert len(html) > 1000
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<style>" in html.lower()
    assert 'class="rpg-shell"' in html
    assert "file:///" not in html
    assert result["campaign_report_html"].endswith("autoplay-campaign-report.html")
