from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


_HTML_ID_RE = re.compile(r'\bid="([^"]+)"')
_HTML_HREF_RE = re.compile(r'href=(["\'])#([^"\']+)\1')


def _prefix_legacy_section_ids(html: str, *, prefix: str = "legacy-") -> str:
    """Prefix IDs and same-document hrefs inside legacy/debug HTML.

    N82 moved old report sections into the Technical Debug wrapper, but those
    sections kept IDs like campaign-journal, quest-progress, quality, debug.
    The new RPG shell also has top-level anchors. Duplicate IDs make browser
    anchor navigation unreliable and can send nav clicks to the wrong section.
    """
    text = _safe_str(html)
    if not text:
        return ""

    id_map: Dict[str, str] = {}

    def replace_id(match: re.Match[str]) -> str:
        old = match.group(1)
        if old.startswith(prefix):
            new = old
        else:
            new = f"{prefix}{old}"
        id_map[old] = new
        return f'id="{new}"'

    text = _HTML_ID_RE.sub(replace_id, text)

    def replace_href(match: re.Match[str]) -> str:
        quote = match.group(1)
        old = match.group(2)
        new = id_map.get(old)
        if not new:
            return match.group(0)
        return f'href={quote}#{new}{quote}'

    text = _HTML_HREF_RE.sub(replace_href, text)
    return text


def _strip_legacy_autoplay_report_partial(html: str) -> str:
    """Remove the old standalone Autoplay Campaign Report shell.

    The RPG report now has a unified hero that contains the campaign chronicle
    and run-report stats. The legacy HTML still contains an older standalone
    report header/nav and old Executive Summary hero. If preserved verbatim, it
    appears as a second report with a different visual theme.

    Keep the useful detailed legacy sections, but strip the duplicate shell:
    - <header>Autoplay Campaign Report ... old nav ...</header>
    - old <section class="hero">Executive Summary ...</section>
    """
    text = _safe_str(html)
    if not text:
        return ""

    # Remove the old report header/nav block when it is the legacy report header.
    text = re.sub(
        r"<header\b[^>]*>\s*.*?Autoplay Campaign Report.*?\bstatus-pill\b.*?</header>",
        "",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove the old blue/purple Executive Summary hero block. This content is
    # now represented by the unified RPG hero + Validation Snapshot.
    text = re.sub(
        r"<section\b(?=[^>]*\bclass=\"[^\"]*\bhero\b[^\"]*\")[^>]*>\s*.*?<h2>\s*Executive Summary\s*</h2>.*?</section>",
        "",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Some generated variants use single quotes for class.
    text = re.sub(
        r"<section\b(?=[^>]*\bclass='[^']*\bhero\b[^']*')[^>]*>\s*.*?<h2>\s*Executive Summary\s*</h2>.*?</section>",
        "",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return _strip_legacy_autoplay_report_tail(text)


def _strip_legacy_autoplay_report_tail(html: str) -> str:
    """Remove any standalone legacy Autoplay Campaign Report partial.

    The RPG report now owns the campaign overview and run-report stats.
    The old legacy report can still be accidentally appended in several shapes:

      1. inside <body> after Technical Debug
      2. after </main>
      3. after </body>
      4. inside grouped debug HTML

    It is identified by the old status-pill/partial header and old nav:

      <h1>Autoplay Campaign Report <span class="status-pill ...">partial</span></h1>
      Summary Journal Quests Evolution ...
      <section ...><h2>Executive Summary</h2>...

    This sanitizer removes the duplicate legacy shell while preserving the RPG
    hero, which also legitimately contains the text "Autoplay Campaign Report".
    """
    text = _safe_str(html)
    if not text:
        return ""

    # Remove old standalone report header/nav blocks anywhere in the document.
    # This intentionally requires status-pill/partial so we do not remove the
    # new RPG hero's "Autoplay Campaign Report" title.
    text = re.sub(
        r"<header\b[^>]*>\s*.*?<h1[^>]*>\s*Autoplay Campaign Report\s*"
        r"<span\b[^>]*\bstatus-pill\b[^>]*>.*?partial.*?</span>\s*</h1>.*?</header>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )



    # Remove the old Executive Summary block. In different generations it may
    # be class="hero", id="summary", or both.
    text = re.sub(
        r"<section\b(?=[^>]*\bid=[\"']summary[\"'])(?=[\s\S]*?<h2[^>]*>\s*Executive Summary\s*</h2>)[\s\S]*?</section>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<section\b(?=[^>]*\bclass=[\"'][^\"']*\bhero\b[^\"']*[\"'])(?=[\s\S]*?<h2[^>]*>\s*Executive Summary\s*</h2>)[\s\S]*?</section>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # If the legacy report is appended after the RPG shell as a raw tail, cut
    # from the first remaining standalone legacy header marker to EOF. This is
    # intentionally checked after the precise removals above.
    legacy_tail = re.search(
        r"<header\b[^>]*>\s*[\s\S]*?Autoplay Campaign Report[\s\S]*?\bstatus-pill\b[\s\S]*?\bpartial\b[\s\S]*?</header>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if legacy_tail:
        text = text[: legacy_tail.start()]

    # Clean up repeated body/html endings if a legacy full document was spliced.
    text = re.sub(r"</body>\s*</html>\s*</body>\s*</html>\s*$", "</body>\n</html>", text, flags=re.IGNORECASE)

    # N83.1.6.1: remove a second standalone legacy <main> appended after the
    # RPG shell. Artifact 161 showed this exact shape:
    #
    #   <main class="rpg-shell"> ... Technical Debug ... </main>
    #   <main>
    #     <section id="campaign-journal">...
    #     <section id="quest-progress">...
    #
    # These sections are already either promoted into the RPG shell or preserved
    # under grouped Technical Debug as legacy-* anchors. The raw second main is
    # the source of the washed-out old theme below the real report.
    text = re.sub(
        r"</main>\s*<main>\s*"
        r"(?=\s*<section\b[^>]*\bid=[\"']campaign-journal[\"'])"
        r"[\s\S]*?</main>",
        "</main>",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    # Defensive variant: if the second legacy main has attributes.
    text = re.sub(
        r"</main>\s*<main\b(?![^>]*\brpg-shell\b)[^>]*>\s*"
        r"(?=\s*<section\b[^>]*\bid=[\"']campaign-journal[\"'])"
        r"[\s\S]*?</main>",
        "</main>",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    # Defensive variant: if legacy sections were appended without a wrapping main.
    text = re.sub(
        r"(?<=</main>)\s*"
        r"<section\b[^>]*\bid=[\"']campaign-journal[\"'][\s\S]*?"
        r"<section\b[^>]*\bid=[\"']debug[\"'][\s\S]*?</section>",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    return text


SOCIAL_ACTION_WORDS = {
    "ask",
    "talk",
    "tell",
    "say",
    "speak",
    "question",
    "report",
    "explain",
    "share",
    "approach",
    "convince",
    "persuade",
}

RPG_PRIMARY_NAV_LINKS = [
    ("campaign-overview", "Overview"),
    ("verdict-cards", "Verdict"),
    ("adventure-timeline", "Adventure"),
    ("quest-board", "Quest Board"),
    ("npc-chronicle", "NPC Chronicle"),
    ("location-journey", "Journey"),
    ("player-sheet", "Player Sheet"),
    ("qa-dashboard", "QA Dashboard"),
]

RPG_EXTENDED_NAV_LINKS = [
    ("campaign-journal", "Journal"),
    ("quest-progress", "Quest Progress"),
    ("npc-evolution", "NPC Evolution"),
    ("hundred-turn-eval", "100-Turn Eval"),
    ("action-diversity", "Actions"),
    ("progress-timeline", "Progress"),
    ("background-result-timing", "Background Timing"),
    ("story-so-far", "Story"),
    ("arcs", "Arcs"),
    ("locations", "Locations"),
    ("variety", "Variety"),
    ("npcs", "NPC Cast"),
    ("inventory", "Inventory"),
    ("dialogue-coverage", "Dialogue"),
    ("performance", "Performance"),
    ("console-log", "Console"),
    ("timeline", "Timeline"),
    ("run-validity", "Shortcomings"),
    ("debug", "Debug"),
    ("technical-debug", "Technical Debug"),
]


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _nested_get(value: Dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _render_badge(text: Any, cls: str = "") -> str:
    return f'<span class="badge {html.escape(cls)}">{_esc(str(text))}</span>'


def _render_paragraphs(text: Any) -> str:
    chunks = [chunk.strip() for chunk in str(text or "").split("\n\n") if chunk.strip()]
    if not chunks:
        return '<p class="muted">No narrative summary available.</p>'
    return "\n".join(f"<p>{_esc(chunk)}</p>" for chunk in chunks)


def _render_table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return '<p class="muted">No data captured.</p>'
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_json_details(title: str, value: Any, *, open_by_default: bool = False) -> str:
    open_attr = " open" if open_by_default else ""
    return (
        f"<details class=\"tech-details\"{open_attr}>"
        f"<summary>{_esc(title)}</summary>"
        f"<pre>{_json(value)}</pre>"
        f"</details>"
    )


def _render_report_quick_links(model: Dict[str, Any]) -> str:
    journal = _safe_dict(model.get("player_journal_summary"))
    quests = _safe_dict(model.get("quest_progress_summary"))
    npc_evolution = _safe_dict(model.get("npc_evolution_report_summary"))
    journal_count = int(journal.get("entry_count") or 0)
    quest_count = int(quests.get("quest_count") or 0)
    npc_count = int(npc_evolution.get("npc_count") or 0)
    return f"""
    <section class="report-quick-links">
      <h2>Report Highlights</h2>
      <nav>
        <a href="#campaign-journal">Campaign Journal ({_esc(str(journal_count))})</a>
        <a href="#quest-progress">Quest Progress ({_esc(str(quest_count))})</a>
        <a href="#npc-evolution">NPC Evolution ({_esc(str(npc_count))})</a>
      </nav>
    </section>
    """


def _render_rpg_nav_links(primary_links, appendix_links=None):
    appendix_links = appendix_links or []

    def render_links(links):
        items = []
        for target, label in links:
            if not target or not label:
                continue
            items.append(f'<button onclick="document.getElementById(\'{html.escape(target)}\').scrollIntoView()" class="nav-link">{html.escape(label)}</button>')
        return "".join(items)

    primary_html = render_links(primary_links)
    appendix_html = render_links(appendix_links)

    appendix_block = ""
    if appendix_html:
        appendix_block = f"""
        <details class="rpg-nav-appendix" open>
          <summary>Appendix Sections</summary>
          <div class="rpg-nav-appendix-links">
            {appendix_html}
          </div>
        </details>
        """

    return f"""
    <nav class="rpg-nav" aria-label="Campaign report sections">
      <div class="rpg-nav-primary">
        {primary_html}
      </div>
      {appendix_block}
    </nav>
    """


def _extract_section_by_id(html: str, section_id: str) -> str:
    text = _safe_str(html)
    if not text.strip():
        return ""
    pattern = (
        rf'<section\b(?=[^>]*\bid=["\']{re.escape(section_id)}["\'])[^>]*>[\s\S]*?</section>'
    )
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _strip_outer_section_heading(section_html: str) -> str:
    text = _safe_str(section_html)
    if not text.strip():
        return ""
    text = re.sub(r"^<section\b[^>]*>", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"</section>\s*$", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"<h2[^>]*>.*?</h2>", "", text, count=1, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _wrap_promoted_legacy_section(
    *,
    section_id: str,
    title: str,
    body_html: str,
    badge: str = "",
    span_class: str = "span-12",
) -> str:
    if not _safe_str(body_html).strip():
        return ""
    badge_html = (
        f'<span class="rpg-badge neutral">{badge}</span>' if badge else ""
    )
    return f"""
    <section class="rpg-card rpg-promoted-section {span_class}" id="{section_id}">
      <div class="rpg-section-title">
        <h2>{title}</h2>
        {badge_html}
      </div>
      <div class="rpg-promoted-body">
        {body_html}
      </div>
    </section>
    """


def _build_promoted_legacy_sections(legacy_html: str) -> str:
    journal_html = _extract_section_by_id(legacy_html, "campaign-journal")
    quest_html = _extract_section_by_id(legacy_html, "quest-progress")
    evolution_html = _extract_section_by_id(legacy_html, "npc-evolution")

    promoted_sections = [
        _wrap_promoted_legacy_section(
            section_id="campaign-journal",
            title="Campaign Calendar & Player Journal",
            badge="Journal",
            body_html=_strip_outer_section_heading(journal_html),
        ),
        _wrap_promoted_legacy_section(
            section_id="quest-progress",
            title="Quest Progress",
            badge="Quest Board",
            body_html=_strip_outer_section_heading(quest_html),
        ),
        _wrap_promoted_legacy_section(
            section_id="npc-evolution",
            title="NPC Evolution",
            badge="Character Growth",
            body_html=_strip_outer_section_heading(evolution_html),
        ),
    ]
    return "\n".join(part for part in promoted_sections if part.strip())


def _strip_report_highlights_quick_links(html: str) -> str:
    text = _safe_str(html)
    if not text.strip():
        return ""
    text = re.sub(
        r'<section\b(?=[^>]*\bclass=["\'][^"\']*\breport-quick-links\b[^"\']*["\'])[\s\S]*?</section>',
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<section\b[^>]*>\s*<h2>\s*Report Highlights\s*</h2>[\s\S]*?</section>',
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _strip_unsafe_file_urls_from_report_html(html_text: str) -> str:
    """Make the report safe to open directly as a static file.

    The report should not require a local HTTP server. Chrome can warn when a
    file:// page tries to load another file:// URL, especially if it points back
    to autoplay-campaign-report.html. Internal navigation must use hash links,
    and artifact links should be relative filenames.
    """
    text = _safe_str(html_text)
    if not text:
        return ""

    # A base file URL makes otherwise harmless relative/hash links resolve
    # through file-origin navigation. Remove it.
    text = re.sub(
        r"<base\b[^>]*\bhref=[\"']file://[^\"']*[\"'][^>]*>\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove file-url meta refresh.
    text = re.sub(
        r"<meta\b(?=[^>]*http-equiv=[\"']refresh[\"'])(?=[^>]*file://)[^>]*>\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Rewrite self-links to this report into a normal internal top anchor.
    text = re.sub(
        r"href=([\"'])file://[^\"']*autoplay-campaign-report\.html(?:#[^\"']*)?\1",
        r'href="#campaign-overview"',
        text,
        flags=re.IGNORECASE,
    )

    # Never embed/iframe/object local file URLs from the static report.
    text = re.sub(
        r"<(?:iframe|embed|object)\b(?=[^>]*(?:src|data)=[\"']file://)[\s\S]*?</(?:iframe|embed|object)>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<(?:iframe|embed)\b(?=[^>]*src=[\"']file://)[^>]*>\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Convert local artifact file links to relative filenames.
    def replace_file_href(match) -> str:
        quote = match.group(1)
        url = match.group(2)
        filename = re.split(r"[\\/]", url)[-1]
        filename = filename.replace("%20", " ").strip()
        if not filename:
            return 'href="#"'
        # Prevent accidentally preserving report self-links after path trimming.
        if filename.lower().split("#", 1)[0] == "autoplay-campaign-report.html":
            return 'href="#campaign-overview"'
        return f"href={quote}{html.escape(filename)}{quote}"

    text = re.sub(
        r"href=([\"'])file://([^\"']*)\1",
        replace_file_href,
        text,
        flags=re.IGNORECASE,
    )

    # Remove script-driven local file navigation.
    text = re.sub(
        r"(?:window\.location|location\.href|top\.location|parent\.location)\s*=\s*[\"']file://[^\"']+[\"']\s*;?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"window\.open\(\s*[\"']file://[^\"']+[\"']\s*(?:,[^)]+)?\)\s*;?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Last-resort cleanup for Windows-style escaped file paths in JS strings.
    text = re.sub(
        r"(?:window\.location|location\.href|top\.location|parent\.location)\s*=\s*[\"']file:\\\\[^\"']+[\"']\s*;?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _finalize_campaign_report_html(html_text: str) -> str:
    """Apply final report sanitizers to a generated HTML string.

    Important: this function must receive the rendered HTML string, not the
    imported Python html module.
    """
    text = _safe_str(html_text)
    text = _strip_legacy_autoplay_report_tail(text)
    text = _strip_legacy_autoplay_report_partial(text)
    text = _strip_report_highlights_quick_links(text)
    text = _strip_unsafe_file_urls_from_report_html(text)
    return text


def _render_calendar_and_journal(calendar: Dict[str, Any], journal: Dict[str, Any]) -> str:
    calendar = _safe_dict(calendar)
    journal = _safe_dict(journal)
    end = _safe_dict(calendar.get("end"))
    entries = journal.get("entries") if isinstance(journal.get("entries"), list) else []
    entry_html = "".join(
        f"""
        <article class="journal-entry">
          <h4>{_esc(str(_safe_dict(entry).get('entry_id') or 'Journal Entry'))}</h4>
          <p><strong>Turns:</strong> {_esc(str(_safe_dict(entry).get('start_turn')))}–{_esc(str(_safe_dict(entry).get('end_turn')))}</p>
          {_render_journal_entry_text(str(_safe_dict(entry).get('text') or ''))}
        </article>
        """
        for entry in entries[-8:]
    )
    return f"""
    <section class="rpg-promoted-section" id="campaign-journal">
      <h2>Campaign Calendar & Player Journal</h2>
      <p><strong>Current campaign time:</strong>
        Year {_esc(str(end.get('year') or ''))},
        {_esc(str(end.get('season') or ''))},
        month {_esc(str(end.get('month') or ''))},
        day {_esc(str(end.get('day') or ''))},
        {_esc(str(end.get('time_label') or ''))}
        ({_esc(str(end.get('day_phase') or ''))})
      </p>
      <p><strong>Turns tracked:</strong> {_esc(str(calendar.get('turns_tracked') or 0))};
         <strong>Journal entries:</strong> {_esc(str(journal.get('entry_count') or 0))}</p>
      <div>{entry_html or '<p>No journal entries yet.</p>'}</div>
    </section>
    """


def _render_journal_entry_text(text: str) -> str:
    text = str(text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "<p></p>"
    html_parts = []
    for line in lines:
        if ":" in line:
            label, rest = line.split(":", 1)
            html_parts.append(
                f"<p><strong>{html.escape(label.strip())}:</strong>{html.escape(rest.strip())}</p>"
            )
        else:
            html_parts.append(f"<p>{html.escape(line)}</p>")
    return "".join(html_parts)


def _render_quest_progress(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    quests = summary.get("quests") if isinstance(summary.get("quests"), list) else []
    if not quests:
        return '<section id="quest-progress"><h2>Quest Progress</h2><p>No quest records found in this run.</p></section>'
    rows = "".join(
        _render_quest_row(_safe_dict(quest))
        for quest in quests
    )
    return f"""
    <section class="rpg-promoted-section" id="quest-progress">
      <h2>Quest Progress</h2>
      <p>Active: {_esc(str(summary.get('active_count') or 0))} ·
         Completed: {_esc(str(summary.get('completed_count') or 0))} ·
         Failed: {_esc(str(summary.get('failed_count') or 0))} ·
         Unknown: {_esc(str(summary.get('unknown_count') or 0))}</p>
      <table>
        <thead><tr><th>Quest</th><th>Status</th><th>Progress</th><th>Giver</th><th>Location</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _render_quest_row(quest: Dict[str, Any]) -> str:
    objectives = quest.get("objectives") if isinstance(quest.get("objectives"), list) else []
    objective_html = ""
    if objectives:
        objective_html = "<ul>" + "".join(
            "<li>"
            + _esc(
                f"{'✓' if _safe_dict(obj).get('completed') else '•'} "
                f"{_safe_dict(obj).get('summary') or _safe_dict(obj).get('title') or _safe_dict(obj).get('name')}"
            )
            + "</li>"
            for obj in objectives[:8]
        ) + "</ul>"
    progress = _esc(str(quest.get("progress") or ""))
    if objective_html:
        progress = progress + objective_html
    return (
        "<tr>"
        f"<td>{_esc(str(quest.get('title') or quest.get('quest_id')))}</td>"
        f"<td>{_esc(str(quest.get('status') or 'unknown'))}</td>"
        f"<td>{progress}</td>"
        f"<td>{_esc(str(quest.get('giver') or ''))}</td>"
        f"<td>{_esc(str(quest.get('location') or ''))}</td>"
        "</tr>"
    )


def _render_console_log_summary(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    if not summary:
        return """
        <section id="console-log">
          <h2>Console Log</h2>
          <p>No captured console log was found for this run.</p>
        </section>
        """
    turn_errors = summary.get("turn_errors") if isinstance(summary.get("turn_errors"), list) else []
    errors = summary.get("errors") if isinstance(summary.get("errors"), list) else []
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    ignored = summary.get("ignored_error_key_lines") if isinstance(summary.get("ignored_error_key_lines"), list) else []
    tail = summary.get("tail") if isinstance(summary.get("tail"), list) else []

    turn_error_html = "".join(f"<li>{_esc(str(line))}</li>" for line in turn_errors[:20])
    error_html = "".join(f"<li>{_esc(str(line))}</li>" for line in errors[:20])
    warning_html = "".join(f"<li>{_esc(str(line))}</li>" for line in warnings[:20])
    ignored_text = "\n".join(str(line) for line in ignored[:40])
    tail_text = "\n".join(str(line) for line in tail[-80:])
    return f"""
    <section class="rpg-promoted-section" id="console-log">
      <h2>Console Log</h2>
      <p><strong>Captured file:</strong> {_esc(str(summary.get("path") or "console-log.txt"))}</p>
      <p>
        Lines: {_esc(str(summary.get("line_count") or 0))} ·
        Errors: {_esc(str(summary.get("error_count") or 0))} ·
        Turn errors: {_esc(str(summary.get("turn_error_count") or 0))} ·
        Warnings: {_esc(str(summary.get("warning_count") or 0))} ·
        Ignored key/debug error fields: {_esc(str(summary.get("ignored_error_key_line_count") or 0))}
      </p>
      <h3>Turn Errors</h3>
      <ul>{turn_error_html or "<li>None.</li>"}</ul>
      <h3>Errors</h3>
      <ul>{error_html or "<li>None.</li>"}</ul>
      <h3>Warnings</h3>
      <ul>{warning_html or "<li>None.</li>"}</ul>
      <details>
        <summary>Ignored debug/key lines containing "error"</summary>
        <pre>{_esc(ignored_text or "None.")}</pre>
      </details>
      <details>
        <summary>Console tail</summary>
        <pre>{_esc(tail_text)}</pre>
      </details>
    </section>
    """


def _render_hundred_turn_eval(model: Dict[str, Any]) -> str:
    eval_summary = _safe_dict(model.get("hundred_turn_eval_summary"))

    action = _safe_dict(model.get("action_diversity_summary") or eval_summary.get("action_diversity_summary"))
    progress = _safe_dict(model.get("progress_timeline_summary") or eval_summary.get("progress_timeline_summary"))
    warnings = _safe_dict(model.get("long_run_warning_summary") or eval_summary.get("long_run_warning_summary"))

    warning_rows = ""
    for warning in warnings.get("warnings") if isinstance(warnings.get("warnings"), list) else []:
        warning = _safe_dict(warning)
        warning_rows += (
            "<tr>"
            f"<td>{html.escape(str(warning.get('severity') or 'warning'))}</td>"
            f"<td>{html.escape(str(warning.get('code') or ''))}</td>"
            f"<td>{html.escape(str(warning.get('message') or ''))}</td>"
            "</tr>"
        )
    if not warning_rows:
        warning_rows = "<tr><td colspan='3'>No long-run warnings.</td></tr>"

    return f"""
    <section class="rpg-promoted-section" id="hundred-turn-eval">
      <h2>100-Turn Evaluation</h2>
      <p><strong>Mode:</strong> {html.escape(str(eval_summary.get("readiness") or "smoke"))}
         · <strong>Turns:</strong> {html.escape(str(eval_summary.get("turn_count") or progress.get("turns") or 0))}
         · <strong>OK:</strong> {html.escape(str(eval_summary.get("ok", True)))}</p>
      <div class="metric-grid">
        <div class="metric-card"><strong>Meaningful progress rate</strong><br>{html.escape(str(progress.get("meaningful_progress_rate") or 0))}</div>
        <div class="metric-card"><strong>Story beat rate</strong><br>{html.escape(str(progress.get("story_beat_rate") or 0))}</div>
        <div class="metric-card"><strong>Max no-progress streak</strong><br>{html.escape(str(progress.get("max_no_progress_streak") or 0))}</div>
        <div class="metric-card"><strong>Max semantic-target repeat</strong><br>{html.escape(str(_safe_dict(action.get("max_same_semantic_target_streak")).get("streak") or 0))}</div>
      </div>
      <h3>Long-Run Warnings</h3>
      <table>
        <thead><tr><th>Severity</th><th>Code</th><th>Message</th></tr></thead>
        <tbody>{warning_rows}</tbody>
      </table>
    </section>
    """


def _render_action_diversity(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)

    def rows(items: Any) -> str:
        out = ""
        for item in items if isinstance(items, list) else []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label, count = item[0], item[1]
            else:
                continue
            out += f"<tr><td>{html.escape(str(label))}</td><td>{html.escape(str(count))}</td></tr>"
        return out or "<tr><td colspan='2'>No data.</td></tr>"

    return f"""
    <section class="rpg-promoted-section" id="action-diversity">
      <h2>Action Diversity</h2>
      <p>
        Unique actions: {html.escape(str(summary.get("unique_action_count") or 0))} ·
        Unique semantic actions: {html.escape(str(summary.get("unique_semantic_action_count") or 0))} ·
        Unique targets: {html.escape(str(summary.get("unique_target_count") or 0))} ·
        Unknown semantic rate: {html.escape(str(summary.get("unknown_semantic_rate") or 0))} ·
        Missing target rate: {html.escape(str(summary.get("missing_target_rate") or 0))}
      </p>
      <h3>Top Semantic Actions</h3>
      <table><thead><tr><th>Semantic Action</th><th>Count</th></tr></thead><tbody>{rows(summary.get("top_semantic_actions"))}</tbody></table>
      <h3>Top Semantic Targets</h3>
      <table><thead><tr><th>Semantic Target</th><th>Count</th></tr></thead><tbody>{rows(summary.get("top_semantic_targets"))}</tbody></table>
    </section>
    """


def _node_ids_from_progression_log(summary: Dict[str, Any]) -> List[str]:
    progression_log = _safe_list(_safe_dict(summary).get("scenario_progression_log"))
    rows: List[tuple[int, int, str]] = []

    for row_index, row in enumerate(progression_log):
        row = _safe_dict(row)
        turn_index = int(row.get("turn_index") or 0)

        node_ids: List[str] = []
        for node_id in _safe_list(row.get("matched_node_ids")):
            node_id = _safe_str(node_id)
            if node_id:
                node_ids.append(node_id)

        for node in _safe_list(row.get("matched_nodes")):
            node_id = _safe_str(_safe_dict(node).get("node_id"))
            if node_id:
                node_ids.append(node_id)

        for local_index, node_id in enumerate(node_ids):
            rows.append((turn_index, row_index * 1000 + local_index, node_id))

    ordered: List[str] = []
    seen = set()
    for _turn_index, _row_order, node_id in sorted(rows, key=lambda item: (item[0], item[1])):
        if node_id and node_id not in seen:
            ordered.append(node_id)
            seen.add(node_id)
    return ordered


def _turn_index_by_progression_node(summary: Dict[str, Any]) -> Dict[str, int]:
    progression_log = _safe_list(_safe_dict(summary).get("scenario_progression_log"))
    out: Dict[str, int] = {}

    for row in progression_log:
        row = _safe_dict(row)
        turn_index = int(row.get("turn_index") or 0)
        if turn_index <= 0:
            continue

        matched_ids: List[str] = []
        for node_id in _safe_list(row.get("matched_node_ids")):
            node_id = _safe_str(node_id)
            if node_id:
                matched_ids.append(node_id)

        for node in _safe_list(row.get("matched_nodes")):
            node_id = _safe_str(_safe_dict(node).get("node_id"))
            if node_id:
                matched_ids.append(node_id)

        for node_id in matched_ids:
            out.setdefault(node_id, turn_index)

    return out


def _graph_registry_node_order(summary: Dict[str, Any]) -> List[str]:
    summary = _safe_dict(summary)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    scenario_seed = _safe_str(
        summary.get("scenario_seed")
        or arc.get("scenario_seed")
        or "tavern_story_seed"
    )

    try:
        from app.rpg.progression.graph_registry import get_progression_graph_for_seed

        graph = get_progression_graph_for_seed(scenario_seed)
        if graph:
            return [_safe_str(node.node_id) for node in graph.nodes if _safe_str(node.node_id)]
    except Exception:
        return []

    return []


def _ordered_progression_graph_node_ids(summary: Dict[str, Any]) -> List[str]:
    summary = _safe_dict(summary)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    completed_nodes = _safe_dict(summary.get("progression_completed_nodes"))

    chronological = _node_ids_from_progression_log(summary)
    registry_order = _graph_registry_node_order(summary)

    # Arc summaries may store completed node ids as sorted lists. They are useful
    # as a membership source, but should not define visual order.
    arc_completed = [
        _safe_str(node_id)
        for node_id in _safe_list(arc.get("completed_node_ids"))
        if _safe_str(node_id)
    ]
    arc_remaining = [
        _safe_str(node_id)
        for node_id in _safe_list(arc.get("remaining_node_ids"))
        if _safe_str(node_id)
    ]
    completed_fallback = [
        _safe_str(node_id)
        for node_id in completed_nodes.keys()
        if _safe_str(node_id)
    ]

    ordered: List[str] = []
    seen = set()

    def add_many(values: List[str]) -> None:
        for value in values:
            value = _safe_str(value)
            if value and value not in seen:
                ordered.append(value)
                seen.add(value)

    # 1. Actual turn order for completed/reached nodes.
    add_many(chronological)

    # 2. Registry order for known nodes not yet reached. This keeps pending nodes
    # after completed nodes without alphabetizing the graph.
    completed_membership = set(chronological) | set(arc_completed) | set(completed_fallback)
    pending_registry = [node_id for node_id in registry_order if node_id not in completed_membership]
    add_many(pending_registry)

    # 3. Append any completed nodes absent from log, preserving registry order if possible.
    completed_missing_from_log = [
        node_id for node_id in registry_order
        if node_id in completed_membership and node_id not in seen
    ]
    add_many(completed_missing_from_log)

    # 4. Last-resort fallback: use arc/completed lists as-is, not sorted.
    add_many(arc_completed)
    add_many(arc_remaining)
    add_many(completed_fallback)

    return ordered


def _progression_graph_report_data(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    completed_nodes = _safe_dict(summary.get("progression_completed_nodes"))
    ordered_node_ids = _ordered_progression_graph_node_ids(summary)
    turn_by_node_id = _turn_index_by_progression_node(summary)
    completed_from_log = set(_node_ids_from_progression_log(summary))
    completed_from_arc = {
        _safe_str(node_id)
        for node_id in _safe_list(arc.get("completed_node_ids"))
        if _safe_str(node_id)
    }

    nodes: List[Dict[str, Any]] = []
    for index, node_id in enumerate(ordered_node_ids, start=1):
        node_id = _safe_str(node_id)
        status = (
            "completed"
            if node_id in completed_nodes
            or node_id in completed_from_log
            or node_id in completed_from_arc
            else "pending"
        )
        turn_index = int(turn_by_node_id.get(node_id) or 0)
        nodes.append(
            {
                "node_id": node_id,
                "label": node_id.replace("_", " "),
                "status": status,
                "turn_index": turn_index,
                "order": index,
            }
        )

    edges = [
        {
            "from": nodes[i]["node_id"],
            "to": nodes[i + 1]["node_id"],
        }
        for i in range(len(nodes) - 1)
    ]

    return {
        "ok": bool(nodes),
        "graph_id": _safe_str(arc.get("graph_id")),
        "arc_complete": bool(arc.get("arc_complete")),
        "expected_node_count": int(arc.get("expected_node_count") or len(nodes)),
        "completed_node_count": int(arc.get("completed_node_count") or len(completed_from_log)),
        "nodes": nodes,
        "edges": edges,
    }


def _render_progress_timeline(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    timeline = summary.get("timeline") if isinstance(summary.get("timeline"), list) else []
    rows = ""
    for item in timeline[-40:]:
        item = _safe_dict(item)
        rows += (
            "<tr>"
            f"<td>{html.escape(str(item.get('turn_index') or ''))}</td>"
            f"<td>{html.escape(str(item.get('semantic_action') or ''))}</td>"
            f"<td>{html.escape(str(item.get('target') or ''))}</td>"
            f"<td>{html.escape(str(item.get('location') or ''))}</td>"
            f"<td>{html.escape(str(item.get('meaningful_progress')))}</td>"
            f"<td>{html.escape(str(item.get('story_beat')))}</td>"
            f"<td>{html.escape(str(item.get('noop')))}</td>"
            f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
            "</tr>"
        )
    if not rows:
        rows = "<tr><td colspan='8'>No progress timeline data.</td></tr>"

    return f"""
    <section class="rpg-promoted-section" id="progress-timeline">
      <h2>Progress Timeline</h2>
      <p>
        Meaningful progress turns: {html.escape(str(summary.get("meaningful_progress_turns") or 0))} ·
        Story beat turns: {html.escape(str(summary.get("story_beat_turns") or 0))} ·
        No-op turns: {html.escape(str(summary.get("noop_turns") or 0))}
      </p>
      <table>
        <thead>
          <tr><th>Turn</th><th>Action</th><th>Target</th><th>Location</th><th>Progress</th><th>Story</th><th>No-op</th><th>Reason</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _render_progression_graph_section(summary: Dict[str, Any]) -> str:
    data = _progression_graph_report_data(summary)
    if not data.get("ok"):
        return """
        <section class="card">
          <h2>Scenario Progression Graph</h2>
          <p class="muted">No progression graph data was captured for this run.</p>
        </section>
        """

    nodes_html = []
    for node in _safe_list(data.get("nodes")):
        node = _safe_dict(node)
        status = _safe_str(node.get("status")) or "pending"
        turn = int(node.get("turn_index") or 0)
        turn_label = f"Turn {turn}" if turn else "Not reached"
        nodes_html.append(
            f"""
            <div class="graph-node graph-node-{html.escape(status)}">
              <div class="graph-node-index">{int(node.get("order") or 0)}</div>
              <div class="graph-node-body">
                <div class="graph-node-title">{html.escape(_safe_str(node.get("label")))}</div>
                <div class="graph-node-meta">{html.escape(turn_label)} · {html.escape(status)} · {html.escape(_safe_str(node.get("node_id")))}</div>
              </div>
            </div>
            """
        )

    edges_html = "".join('<div class="graph-edge">↓</div>' for _ in _safe_list(data.get("edges")))
    interleaved = []
    for index, node_html in enumerate(nodes_html):
        interleaved.append(node_html)
        if index < len(nodes_html) - 1:
            interleaved.append('<div class="graph-edge">↓</div>')

    mermaid_lines = ["graph TD"]
    for node in _safe_list(data.get("nodes")):
        node = _safe_dict(node)
        node_id = _safe_str(node.get("node_id"))
        label = _safe_str(node.get("label"))
        safe_id = "n_" + "".join(ch if ch.isalnum() else "_" for ch in node_id)
        mermaid_lines.append(f'  {safe_id}["{label}"]')
    for edge in _safe_list(data.get("edges")):
        edge = _safe_dict(edge)
        src = "n_" + "".join(ch if ch.isalnum() else "_" for ch in _safe_str(edge.get("from")))
        dst = "n_" + "".join(ch if ch.isalnum() else "_" for ch in _safe_str(edge.get("to")))
        mermaid_lines.append(f"  {src} --> {dst}")
    mermaid_source = "\n".join(mermaid_lines)

    return f"""
    <section class="card" id="scenario-progression-graph">
      <h2>Scenario Progression Graph</h2>
      <p class="muted">
        Graph: {html.escape(_safe_str(data.get("graph_id")))}
        · Completed {int(data.get("completed_node_count") or 0)} / {int(data.get("expected_node_count") or 0)}
        · Arc complete: {html.escape(str(bool(data.get("arc_complete"))))}
      </p>
      <p class="muted small">
        Nodes are ordered by first matched turn, with unreached graph nodes appended afterward.
      </p>
      <div class="progression-graph">
        {''.join(interleaved)}
      </div>
      <details class="debug-details">
        <summary>Mermaid graph source</summary>
        <pre>{html.escape(mermaid_source)}</pre>
      </details>
    </section>
    """


def _render_background_result_timing(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    events = summary.get("attachment_events") if isinstance(summary.get("attachment_events"), list) else []
    rows = ""
    for event in events[-40:]:
        event = _safe_dict(event)
        rows += (
            "<tr>"
            f"<td>{html.escape(str(event.get('source_turn') or ''))}</td>"
            f"<td>{html.escape(str(event.get('attach_turn') or ''))}</td>"
            f"<td>{html.escape(str(event.get('phase') or ''))}</td>"
            f"<td>{html.escape(str(event.get('lag_turns') or 0))}</td>"
            f"<td>{html.escape(str(event.get('job_id') or ''))}</td>"
            "</tr>"
        )
    if not rows:
        rows = "<tr><td colspan='5'>No background attachment timing data.</td></tr>"

    warnings = ""
    for warning in summary.get("warnings") if isinstance(summary.get("warnings"), list) else []:
        warning = _safe_dict(warning)
        warnings += (
            "<li>"
            f"<strong>{html.escape(str(warning.get('severity') or 'warning'))}</strong> "
            f"{html.escape(str(warning.get('code') or ''))}: "
            f"{html.escape(str(warning.get('message') or ''))}"
            "</li>"
        )

    return f"""
    <section class="rpg-promoted-section" id="background-result-timing">
      <h2>Background Result Timing</h2>
      <p>
        Submitted: {html.escape(str(summary.get('jobs_submitted') or 0))} ·
        Attached: {html.escape(str(summary.get('jobs_attached_total') or 0))} ·
        Pre-turn attached: {html.escape(str(summary.get('jobs_attached_pre_turn') or 0))} ·
        Final attached: {html.escape(str(summary.get('jobs_attached_final') or 0))} ·
        Pre-turn attach rate: {html.escape(str(summary.get('pre_turn_attach_rate') or 0))} ·
        Max lag turns: {html.escape(str(summary.get('max_attach_lag_turns') or 0))}
      </p>
      <ul>{warnings or '<li>No timing warnings.</li>'}</ul>
      <table>
        <thead><tr><th>Source turn</th><th>Attach turn</th><th>Phase</th><th>Lag</th><th>Job</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _render_npc_evolution_cards(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    cards = summary.get("cards") if isinstance(summary.get("cards"), list) else []
    if not cards:
        return '<section id="npc-evolution"><h2>NPC Evolution</h2><p>No NPC evolution arcs found yet.</p></section>'
    rows = []
    for card_any in cards:
        card = _safe_dict(card_any)
        axes = _safe_dict(card.get("axes"))
        axes_html = "".join(
            f"<tr><td>{_esc(str(axis))}</td><td>{_esc(str(value))}</td></tr>"
            for axis, value in sorted(axes.items())
        )
        memories = "".join(
            f"<li>{_esc(str(_safe_dict(item).get('summary') or item))}</li>"
            for item in (card.get("memories") if isinstance(card.get("memories"), list) else [])[-5:]
        )
        hooks = "".join(
            f"<li>{_esc(str(_safe_dict(item).get('summary') or item))}</li>"
            for item in (card.get("future_hooks") if isinstance(card.get("future_hooks"), list) else [])[-5:]
        )
        milestones = "".join(
            "<li>"
            + _esc(
                f"{_safe_dict(item).get('from', '')} → {_safe_dict(item).get('to', '')}"
                f" ({_safe_dict(item).get('reason', '')})"
            )
            + "</li>"
            for item in (card.get("milestones") if isinstance(card.get("milestones"), list) else [])[-5:]
        )
        rows.append(
            f"""
            <article class="npc-card">
              <h3>{_esc(str(card.get('npc_id') or 'Unknown NPC'))}</h3>
              <p><strong>Arc stage:</strong> {_esc(str(card.get('arc_stage') or 'stable'))}</p>
              <p><strong>Signals:</strong> {_esc(str(card.get('signal_count') or 0))}</p>
              <p><strong>Profile:</strong> {_esc(str(card.get('profile_path') or 'not loaded'))}</p>
              <h4>Axes</h4>
              <table><tbody>{axes_html}</tbody></table>
              <h4>Recent Memories</h4>
              <ul>{memories or '<li>None yet.</li>'}</ul>
              <h4>Future Hooks</h4>
              <ul>{hooks or '<li>None yet.</li>'}</ul>
              <h4>Milestones</h4>
              <ul>{milestones or '<li>No stage changes yet.</li>'}</ul>
            </article>
            """
        )
    return f"""
    <section class="rpg-promoted-section" id="npc-evolution">
      <h2>NPC Evolution</h2>
      <p>{_esc(str(summary.get('npc_count') or len(cards)))} NPC profile(s) tracked.</p>
      <div class="npc-card-grid">{''.join(rows)}</div>
    </section>
    """


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _contains_any(text: str, words: List[str]) -> bool:
    text_l = text.lower()
    return any(word.lower() in text_l for word in words)


def _title_case_from_text(text: str, *, fallback: str = "Entry") -> str:
    """Convert text to title case, falling back if too short."""
    text = _safe_str(text).strip()
    if not text or len(text) < 3:
        return fallback
    return text.title()


def _merge_report_contexts(
    *,
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    report_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge summary/metrics/report model into one render context.

    The report shell originally read mostly from autoplay-summary.json style
    summary/metrics. Some user-facing campaign data, especially formatted
    inventory/currency rows, is only present in the richer campaign report model.
    Merge those fields so top-level RPG sections do not show empty data when the
    model already has the real values.
    """
    merged: Dict[str, Any] = {}
    for source in (_safe_dict(metrics), _safe_dict(summary), _safe_dict(report_model)):
        for key, value in source.items():
            if key not in merged or merged.get(key) in (None, "", [], {}):
                merged[key] = value

    # Common nested model aliases seen in generated report artifacts.
    for key in ("model", "report_model", "campaign_report_model", "data"):
        nested = _safe_dict(merged.get(key))
        for nested_key, nested_value in nested.items():
            if nested_key not in merged or merged.get(nested_key) in (None, "", [], {}):
                merged[nested_key] = nested_value

    return merged


def _report_context_value(context: Dict[str, Any], *keys: str) -> Any:
    context = _safe_dict(context)
    for key in keys:
        if key in context and context.get(key) not in (None, "", [], {}):
            return context.get(key)
    return None


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _short_text(value: Any, limit: int = 220) -> str:
    text = _safe_str(value).strip()
    if len(text) <= int(limit or 220):
        return text
    return text[: max(0, int(limit or 220) - 1)].rstrip() + "…"


def _dedupe_texts(values: List[Any], *, limit: int = 0) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in _as_list(values):
        if isinstance(value, dict):
            text = _first_non_empty(
                value.get("summary"),
                value.get("text"),
                value.get("description"),
                value.get("message"),
                value.get("memory"),
                value.get("hook"),
                value.get("intent"),
                value.get("label"),
            )
        else:
            text = _safe_str(value)
        text = " ".join(text.strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if int(limit or 0) > 0 and len(result) >= int(limit or 0):
            break
    return result


def _dedupe_memory_key(text: str) -> str:
    key = _safe_str(text).lower()
    key = re.sub(r"\(turn\s+\d+\)", "", key, flags=re.IGNORECASE)
    key = re.sub(r"\bturn\s+\d+\b", "", key, flags=re.IGNORECASE)
    key = re.sub(r"\b\d{4}-\d{2}-\d{2}[^\s]*", "", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    key = " ".join(key.split())
    return key[:180]


def _dedupe_texts_fuzzy(values: List[Any], *, limit: int = 0) -> List[str]:
    seen = set()
    result: List[str] = []
    for text in _dedupe_texts(values, limit=0):
        key = _dedupe_memory_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if int(limit or 0) > 0 and len(result) >= int(limit or 0):
            break
    return result


def _normalize_report_target(value: Any) -> str:
    text = _safe_str(value).strip()
    if text.startswith("npc:") and len(text) > 4:
        return text[4:]
    return text


def _turn_int(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    return _num(row.get("turn_index") or row.get("turn") or row.get("source_turn"))


def _status_class(value: Any) -> str:
    text = _safe_str(value).lower()
    if text in {"pass", "passed", "good", "ok", "true", "healthy"}:
        return "good"
    if text in {"warn", "warning", "partial", "caution"}:
        return "warn"
    if text in {"fail", "failed", "bad", "false", "error"}:
        return "bad"
    return ""


def _status_badge_class(value: Any) -> str:
    text = str(value).strip().lower()
    if text in ("true", "ok", "pass", "passed", "success", "green"):
        return "pass"
    if text in ("false", "fail", "failed", "error", "red"):
        return "fail"
    if text in ("warn", "warning", "partial", "yellow"):
        return "warn"
    return "neutral"


def _yes_no(value: Any) -> str:
    return "PASS" if bool(value) else "FAIL"


def _pct(value: Any) -> str:
    try:
        value = float(value)
    except Exception:
        return "0%"
    if value <= 1.0:
        value *= 100.0
    return f"{max(0.0, min(100.0, value)):.0f}%"


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _seconds_from_ms(value: Any) -> str:
    try:
        return f"{float(value) / 1000.0:.2f}s"
    except Exception:
        return "0.00s"


def _number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0"


def _format_item_name(item: Any) -> str:
    if isinstance(item, str):
        return item
    item = _safe_dict(item)
    name = _first_non_empty(item.get("name"), item.get("item_id"), item.get("id"), item.get("type"))
    qty = item.get("qty") or item.get("quantity") or item.get("count") or item.get("amount")
    if qty:
        return f"{name} ×{qty}"
    return name


def _format_currency(currency: Any) -> str:
    currency = _safe_dict(currency)
    parts = []
    for key, value in currency.items():
        if isinstance(value, (int, float)) and value > 0:
            parts.append(f"{int(value)} {key}")
    return ", ".join(parts)


def _html_list(items: List[Any], *, empty: str = "None", limit: int = 10) -> str:
    items = [str(item) for item in _as_list(items) if item][:limit]
    if not items:
        return f"<p>{html.escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _infer_rpg_title_from_text(text: str, *, fallback: str = "Story Beat") -> str:
    text = _safe_str(text).strip()
    if not text:
        return fallback

    import re

    # Clean up the text for analysis
    text_lower = text.lower()
    if text_lower.startswith("player:"):
        lower_action = text_lower.split("player:", 1)[1].strip()
    else:
        lower_action = text_lower

    if any(term in lower_action for term in ("listen intently", "listen closely", "listen to bran")):
        return "Listen to Bran"
    if "bran" in lower_action and any(term in lower_action for term in ("lean in", "lower your voice", "quietly", "discreetly", "private")):
        return "Speak Privately with Bran"
    if "bran" in lower_action and any(term in lower_action for term in ("elaboration", "explain", "details", "more about", "follow up")):
        return "Press Bran for Details"
    if "bran" in lower_action and any(term in lower_action for term in ("unusual activity", "rumor", "rumors", "town")):
        return "Ask Bran About Rumors"
    if any(term in lower_action for term in ("ask bran", "question bran")):
        return "Question Bran"
    if any(term in lower_action for term in ("ask", "question", "inquire")) and "rumor" in lower_action:
        return "Ask About Rumors"
    if any(term in lower_action for term in ("lean in", "lower your voice", "whisper")):
        return "Speak Quietly"
    if any(term in lower_action for term in ("listen", "wait for", "hear him out")):
        return "Listen Carefully"
    if "traveler" in lower_action:
        return "Engage the Traveler"
    return _title_case_from_text(text, fallback=fallback)

    # Look for key RPG elements that would make good titles

    # Character conversations: "Bran says...", "The innkeeper tells..."
    char_speak_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+says?\b', text, re.IGNORECASE)
    if char_speak_match:
        name = char_speak_match.group(1).strip()
        if len(name) > 2 and name not in {"The", "They", "You", "We", "I"}:
            # Try to extract what they're saying
            remaining = text[len(char_speak_match.group(0)):].strip()
            if remaining:
                # Look for key topics
                if re.search(r'\bwitness\b|\bevidence\b|\bclue\b', remaining, re.IGNORECASE):
                    return f"{name}: Witness Info"
                elif re.search(r'\bbandit\b|\bthief\b|\brobber\b|\bcriminal\b', remaining, re.IGNORECASE):
                    return f"{name}: Bandit Report"
                elif re.search(r'\broad\b|\bpath\b|\btrail\b|\bdestination\b', remaining, re.IGNORECASE):
                    return f"{name}: Travel Info"
                elif re.search(r'\binn\b|\btavern\b|\bshop\b|\bstore\b|\bmerchant\b', remaining, re.IGNORECASE):
                    return f"{name}: Local Info"
                else:
                    return f"{name} Speaks"

    # Location arrivals: "The party arrives at the Rusty Flagon"
    location_match = re.search(r'\b(?:arrives?|enters?|reaches?|finds?|discovers?|visits?)\s+(?:at|in|the)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text, re.IGNORECASE)
    if location_match:
        location = location_match.group(1).strip()
        if len(location) > 3:
            return f"At {location}"

    # Discoveries and findings
    discovery_match = re.search(r'\b(?:discovers?|finds?|learns?|realizes?|sees?|notices?|observes?)\s+(?:that|about|of)\s+(.+?)(?:\s*[.,;]|$)', text, re.IGNORECASE)
    if discovery_match:
        discovery = discovery_match.group(1).strip()
        if len(discovery) > 8:
            # Shorten and capitalize
            short_discovery = discovery[:30] + "..." if len(discovery) > 30 else discovery
            return f"Discovery: {short_discovery.title()}"

    # Quest or mission related
    quest_match = re.search(r'\b(?:quest|mission|task|objective|goal|job)\b.*?\b(?:is|was|becomes?|continues?|progresses?|advances?)\s+(.+?)(?:\s*[.,;]|$)', text, re.IGNORECASE)
    if quest_match:
        quest_info = quest_match.group(1).strip()
        if len(quest_info) > 5:
            return "Quest Progress"

    # Combat or confrontation
    combat_match = re.search(r'\b(?:fights?|battles?|confronts?|attacks?|defends?)\s+(?:against|with)\s+(.+?)(?:\s*[.,;]|$)', text, re.IGNORECASE)
    if combat_match:
        opponent = combat_match.group(1).strip()
        if len(opponent) > 3:
            return f"Confrontation: {opponent.title()}"

    # NPC encounters
    npc_match = re.search(r'\b(?:meets?|encounters?|talks?\s+to|speaks?\s+to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text, re.IGNORECASE)
    if npc_match:
        npc_name = npc_match.group(1).strip()
        if len(npc_name) > 2 and npc_name not in {"The", "They", "You", "We", "I"}:
            return f"Meeting {npc_name}"

    # If we can't find a specific pattern, try to extract meaningful phrases
    # Look for sentences that seem like key plot points
    sentences = re.split(r'[.!?]+', text)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10 or len(sentence) > 60:
            continue

        # Skip sentences that are too generic
        if re.match(r'^(The\s+party|They|You|We|I)\s+(?:goes?|moves?|walks?|travels?|continues?|proceeds?)\b', sentence, re.IGNORECASE):
            continue

        # Look for sentences with proper names or specific nouns
        if re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', sentence):
            # Capitalize first letter and add ellipsis if it's a fragment
            title = sentence[0].upper() + sentence[1:]
            if not title.endswith('.') and not title.endswith('!') and not title.endswith('?'):
                title += "..."
            return title

    # As a last resort, return the fallback
    return fallback


def _is_generic_timeline_title(value: Any) -> bool:
    text = _safe_str(value).strip().lower()
    return text in {
        "",
        "story beat",
        "campaign event",
        "campaign beat",
        "player action",
        "turn event",
    }


def _timeline_title_from_body(body: Any, *, fallback: str = "Story Beat") -> str:
    text = _safe_str(body).strip()
    if not text:
        return fallback

    # Many story summaries are shaped like:
    # "Player: Ask Bran about any unusual activity or rumors in town. Result: ..."
    # Use the player-action prefix as the title source when present.
    player_match = re.search(
        r"\bPlayer:\s*(.+?)(?:\n|\. Result:| Result:|\. Outcome:| Outcome:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if player_match:
        candidate = player_match.group(1).strip()
        inferred = _infer_rpg_title_from_text(candidate, fallback=fallback)
        if not _is_generic_timeline_title(inferred):
            return inferred

    action_match = re.search(
        r"\b(?:Action|Player Action):\s*(.+?)(?:\n|\. Result:| Result:|\. Outcome:| Outcome:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if action_match:
        candidate = action_match.group(1).strip()
        inferred = _infer_rpg_title_from_text(candidate, fallback=fallback)
        if not _is_generic_timeline_title(inferred):
            return inferred

    inferred = _infer_rpg_title_from_text(text, fallback=fallback)
    if not _is_generic_timeline_title(inferred):
        return inferred

    return fallback


def _render_bar(label: str, value: Any, *, max_value: float | None = None, suffix: str = "") -> str:
    try:
        raw = float(value)
    except Exception:
        raw = 0.0
    width_str = _pct(raw if max_value is None else (raw / max_value if max_value else 0.0))
    width = float(width_str.rstrip('%')) if '%' in width_str else 0.0
    display = f"{raw:.2f}{suffix}" if isinstance(raw, float) else f"{raw}{suffix}"
    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{_esc(label)}</div>'
        '<div class="bar-track">'
        f'<div class="bar-fill" style="width:{width:.1f}%"></div>'
        '</div>'
        f'<div class="bar-value">{_esc(display)}</div>'
        '</div>'
    )


def _render_progress_bar(label: str, rate: Any) -> str:
    percent_str = _pct(rate)
    percent = float(percent_str.rstrip('%')) if '%' in percent_str else 0.0
    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{_esc(label)}</div>'
        '<div class="bar-track">'
        f'<div class="bar-fill" style="width:{percent:.1f}%"></div>'
        '</div>'
        f'<div class="bar-value">{percent_str}</div>'
        '</div>'
    )


def _render_key_value_table(rows: List[tuple[str, Any]]) -> str:
    return (
        '<table class="kv-table"><tbody>'
        + ''.join(f'<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>' for k, v in rows)
        + '</tbody></table>'
    )


def _render_chapter_status_cards(chapter_status: Dict[str, Any]) -> str:
    active = _safe_list(chapter_status.get("active_objectives"))
    completed = _safe_list(chapter_status.get("completed_objectives"))
    active_rows = [[title] for title in active]
    completed_rows = [[title] for title in completed]
    return f'''
    <div class="grid">
      <div class="metric"><div class="value">{_esc(chapter_status.get("campaign_title") or "Untitled")}</div><div>Campaign Title</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("current_stage") or "unknown")}</div><div>Current Stage</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("chapter_complete"))}</div><div>Chapter Complete</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("active_objective_count"))}</div><div>Active Objectives</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("completed_objective_count"))}</div><div>Completed Objectives</div></div>
    </div>
    <p class="section-lede"><strong>Recommendation:</strong> {_esc(chapter_status.get("recommendation"))}</p>
    <div class="two-col">
      <div>
        <h3>Active Objectives</h3>
        {_render_table(["Objective"], active_rows)}
      </div>
      <div>
        <h3>Completed Objectives</h3>
        {_render_table(["Objective"], completed_rows)}
      </div>
    </div>
    {_render_json_details("Chapter status JSON", chapter_status)}
    '''


def _inventory_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        state.get("inventory_state"),
        state.get("player_inventory"),
        _safe_dict(state.get("player_state")).get("inventory"),
        _safe_dict(state.get("party_state")).get("inventory"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return {
                "currency": _safe_dict(candidate.get("currency")),
                "items": _safe_list(candidate.get("items")),
            }
        if isinstance(candidate, list) and candidate:
            return {"items": candidate}
    return {"currency": {}, "items": []}


def _initial_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in transcript:
        before = _safe_dict(row.get("before_state"))
        if before:
            return before
        turn_result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(turn_result.get("initial_simulation_state"))
        if state:
            return state
    return {}


def build_pm_report_summary(model: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _safe_dict(model.get("metrics"))
    progress = _safe_dict(metrics.get("progress_quality"))
    dialogue = _safe_dict(model.get("dialogue_coverage"))
    runtime_diag = _safe_dict(model.get("runtime_narration_diagnostics"))
    chapter = _safe_dict(model.get("chapter_status"))
    shortcomings = _safe_list(model.get("shortcomings"))

    return {
        "overall_status": "partial" if shortcomings else "good",
        "story_status": "good" if int(chapter.get("active_objective_count") or 0) > 0 else "warn",
        "dialogue_status": "good" if float(dialogue.get("social_turn_missing_npc_response_rate") or 0.0) == 0.0 else "warn",
        "provider_status": "good" if int(runtime_diag.get("provider_valid_turns") or 0) > 0 else "warn",
        "performance_status": "good",
        "headline": "The campaign can progress through a complete tavern investigation branch and continue into the bandit-road chapter.",
        "top_risks": shortcomings[:5],
        "key_numbers": {
            "turns": _safe_dict(model.get("summary")).get("turns_executed"),
            "meaningful_turns": progress.get("meaningful_turns"),
            "npc_response_rate": dialogue.get("npc_response_rate"),
            "provider_valid_turns": runtime_diag.get("provider_valid_turns"),
            "provider_repaired_turns": runtime_diag.get("provider_repaired_turns"),
            "active_objectives": chapter.get("active_objective_count"),
        },
    }


def _build_campaign_chronicle_model(summary: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    metrics = _safe_dict(metrics)
    quality = _safe_dict(summary.get("quality_gate_summary") or metrics.get("quality_gate_summary"))
    background_timing = _safe_dict(
        summary.get("background_result_timing_summary")
        or metrics.get("background_result_timing_summary")
    )
    background_jobs = _safe_dict(summary.get("background_jobs") or metrics.get("background_jobs"))
    action_diversity = _safe_dict(
        summary.get("action_diversity_summary")
        or metrics.get("action_diversity_summary")
    )
    progress = _safe_dict(
        summary.get("progress_timeline_summary")
        or metrics.get("progress_timeline_summary")
    )
    long_run = _safe_dict(
        summary.get("long_run_warning_summary")
        or metrics.get("long_run_warning_summary")
    )
    journal = _safe_dict(summary.get("player_journal_summary") or metrics.get("player_journal_summary"))
    calendar = _safe_dict(summary.get("campaign_calendar_summary") or metrics.get("campaign_calendar_summary"))

    turn_count = (
        _num(summary.get("turn_count"))
        or _num(metrics.get("turn_count"))
        or _num(metrics.get("real_turn_runtime_count"))
        or _num(summary.get("real_turn_runtime_count"))
    )
    session_id = _first_non_empty(
        summary.get("session_id"),
        metrics.get("session_id"),
        summary.get("manual_run_id"),
        metrics.get("manual_run_id"),
    )
    seed = _first_non_empty(
        summary.get("scenario_seed"),
        metrics.get("scenario_seed"),
        summary.get("seed"),
        metrics.get("seed"),
    )

    return {
        "title": _first_non_empty(
            summary.get("campaign_title"),
            metrics.get("campaign_title"),
            "The Autoplay Campaign Chronicle",
        ),
        "subtitle": _first_non_empty(
            summary.get("campaign_subtitle"),
            "A deterministic RPG autoplay run rendered as a campaign chronicle and QA report.",
        ),
        "session_id": session_id,
        "seed": seed,
        "turn_count": turn_count,
        "quality_ok": bool(quality.get("ok", summary.get("ok", True))),
        "summary_ok": bool(summary.get("ok", quality.get("ok", True))),
        "warning_count": _num(long_run.get("warning_count")),
        "quality_gate_count": _num(quality.get("gate_count") or len(_safe_dict(quality.get("gates")))),
        "quality_failed_count": _num(quality.get("failed_count") or quality.get("failure_count")),
        "background_jobs_submitted": _num(background_timing.get("jobs_submitted") or background_jobs.get("jobs_submitted")),
        "background_jobs_attached_total": _num(background_timing.get("jobs_attached_total")),
        "background_jobs_attached_pre_turn": _num(background_timing.get("jobs_attached_pre_turn")),
        "background_jobs_attached_final": _num(background_timing.get("jobs_attached_final")),
        "background_pre_turn_attach_rate": background_timing.get("pre_turn_attach_rate") or 0,
        "background_missing_jobs": _num(background_timing.get("missing_job_count")),
        "max_semantic_streak": _safe_dict(action_diversity.get("max_same_semantic_target_streak")),
        "meaningful_progress_rate": progress.get("meaningful_progress_rate") or 0,
        "churn_only_rate": progress.get("churn_only_rate") or 0,
        "progress_event_count": _num(progress.get("progress_event_count")),
        "journal_entry_count": _num(journal.get("entry_count")),
        "calendar_turns_tracked": _num(calendar.get("turns_tracked")),
    }


def _render_rpg_hero(model: Dict[str, Any]) -> str:
    model = _safe_dict(model)
    verdict = "PASS" if bool(model.get("quality_ok")) else "FAIL"
    verdict_class = _status_badge_class(bool(model.get("quality_ok")))
    turn_count = _num(model.get("turn_count"))
    seed = _safe_str(model.get("seed")) or "default"
    session_id = _safe_str(model.get("session_id")) or "unknown"
    max_streak = _safe_dict(model.get("max_semantic_streak"))
    max_streak_label = _first_non_empty(max_streak.get("value"), max_streak.get("pair"), "n/a")
    max_streak_count = _num(max_streak.get("streak"))
    return f"""
    <header class="rpg-hero" id="campaign-overview">
      <div class="rpg-kicker">Campaign Chronicle · Autoplay Validation Report</div>
      <h1 class="rpg-title">{_esc(_safe_str(model.get('title')))}</h1>
      <div class="rpg-subtitle">{_esc(_safe_str(model.get('subtitle')))}</div>
      <div class="rpg-hero-meta">
        <span class="rpg-badge {verdict_class}">{_esc(verdict)}</span>
        <span class="rpg-pill">{_esc(str(turn_count))} Turns</span>
        <span class="rpg-pill">Seed: {_esc(seed)}</span>
        <span class="rpg-pill">Session: {_esc(session_id)}</span>
      </div>
      <div class="rpg-hero-report">
        <div class="rpg-hero-report-header">
          <div>
            <div class="rpg-kicker">Run Report</div>
            <h2>Autoplay Campaign Report</h2>
          </div>
          <span class="rpg-badge {verdict_class}">{_esc(verdict)}</span>
        </div>
        <div class="rpg-hero-stat-grid">
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Quality Gates</div>
            <div class="rpg-stat-value">{_esc(verdict)}</div>
          </div>
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Background Jobs</div>
            <div class="rpg-stat-value">{_esc(str(_num(model.get('background_jobs_submitted'))))}</div>
            <div class="rpg-muted-line">
              Pre-turn {_esc(str(_num(model.get('background_jobs_attached_pre_turn'))))}
              · Final {_esc(str(_num(model.get('background_jobs_attached_final'))))}
            </div>
          </div>
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Pre-Turn Attach Rate</div>
            <div class="rpg-stat-value">{_esc(_pct(model.get('background_pre_turn_attach_rate')))}</div>
          </div>
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Missing BG Jobs</div>
            <div class="rpg-stat-value">{_esc(str(_num(model.get('background_missing_jobs'))))}</div>
          </div>
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Meaningful Progress</div>
            <div class="rpg-stat-value">{_esc(_pct(model.get('meaningful_progress_rate')))}</div>
          </div>
          <div class="rpg-hero-stat">
            <div class="rpg-stat-label">Max Semantic Streak</div>
            <div class="rpg-stat-value">{_esc(str(max_streak_count))}</div>
            <div class="rpg-muted-line">{_esc(max_streak_label)}</div>
          </div>
        </div>
      </div>
    </header>
    """





def _render_autoplay_campaign_report_partial(summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    metrics = _safe_dict(metrics)
    quality = _safe_dict(summary.get("quality_gate_summary") or metrics.get("quality_gate_summary"))
    background = _safe_dict(summary.get("background_result_timing_summary") or metrics.get("background_result_timing_summary"))
    perf = _safe_dict(summary.get("performance_budget_summary") or metrics.get("performance_budget_summary"))
    bg_perf = _safe_dict(perf.get("background_llm"))
    action = _safe_dict(summary.get("action_diversity_summary") or metrics.get("action_diversity_summary"))
    progress = _safe_dict(summary.get("progress_timeline_summary") or metrics.get("progress_timeline_summary"))
    max_streak = _safe_dict(action.get("max_same_semantic_target_streak"))

    return f"""
    <section class="rpg-card rpg-promoted-section span-12" id="autoplay-campaign-report">
      <div class="rpg-section-title">
        <h2>Autoplay Campaign Report</h2>
        <span class="rpg-badge {_status_badge_class(quality.get('ok', True))}">
          {_esc(_yes_no(quality.get('ok', True)))}
        </span>
      </div>
      <p>
        This is the engineering summary for the same run shown in the campaign chronicle.
        It uses the RPG report theme but keeps the key validation numbers visible near the top.
      </p>
      <div class="rpg-stat-grid">
        <div class="rpg-stat">
          <div class="rpg-stat-label">Quality Gates</div>
          <div class="rpg-stat-value">{_esc(_yes_no(quality.get('ok', True)))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Background Submitted</div>
          <div class="rpg-stat-value">{_esc(str(background.get('jobs_submitted') or bg_perf.get('jobs_submitted') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Pre-Turn Attach Rate</div>
          <div class="rpg-stat-value">{_esc(_pct(background.get('pre_turn_attach_rate') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Missing BG Jobs</div>
          <div class="rpg-stat-value">{_esc(str(background.get('missing_job_count') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Meaningful Progress</div>
          <div class="rpg-stat-value">{_esc(_pct(progress.get('meaningful_progress_rate') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Max Semantic Streak</div>
          <div class="rpg-stat-value">{_esc(str(max_streak.get('streak') or 0))}</div>
          <div>{_esc(_safe_str(max_streak.get('value') or max_streak.get('pair') or 'n/a'))}</div>
        </div>
      </div>
    </section>
    """


def _render_rpg_verdict_cards(model: Dict[str, Any]) -> str:
    model = _safe_dict(model)
    quality_ok = bool(model.get("quality_ok"))
    warnings = _num(model.get("warning_count"))
    missing = _num(model.get("background_missing_jobs"))
    streak = _safe_dict(model.get("max_semantic_streak"))
    streak_value = _safe_str(streak.get("value") or streak.get("pair") or "n/a")
    streak_count = _num(streak.get("streak"))
    return f"""
    <section class="rpg-card rpg-promoted-section span-12" id="verdict-cards">
      <div class="rpg-section-title">
        <h2>Validation Snapshot</h2>
        <span class="rpg-badge {_status_badge_class(quality_ok)}">{html.escape(_yes_no(quality_ok))}</span>
      </div>
      <div class="rpg-stat-grid">
        <div class="rpg-stat">
          <div class="rpg-stat-label">Quality Gates</div>
          <div class="rpg-stat-value">{html.escape(_yes_no(quality_ok))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Warnings</div>
          <div class="rpg-stat-value">{html.escape(str(warnings))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Background Jobs</div>
          <div class="rpg-stat-value">{html.escape(str(_num(model.get('background_jobs_submitted'))))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Pre-Turn Attach Rate</div>
          <div class="rpg-stat-value">{html.escape(str(_pct(model.get('background_pre_turn_attach_rate'))))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Missing Background Jobs</div>
          <div class="rpg-stat-value">{html.escape(str(missing))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Max Semantic Streak</div>
          <div class="rpg-stat-value">{html.escape(str(streak_count))}</div>
          <div>{html.escape(streak_value)}</div>
        </div>
      </div>
    </section>
    """


def _nested_report_dict(root: Dict[str, Any], *path: str) -> Dict[str, Any]:
    value: Any = root
    for key in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(key)
    return value if isinstance(value, dict) else {}


def _strip_npc_prefix(value: Any) -> str:
    text = _safe_str(value).strip()
    if text.startswith("npc:") and len(text) > 4:
        return text[4:]
    return text


def _semantic_mapping_from_report_row(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    turn_contract = _safe_dict(row.get("turn_contract"))
    result = _safe_dict(row.get("result") or row.get("turn_result"))

    candidates = [
        _safe_dict(row.get("semantic_action_v2")),
        _safe_dict(row.get("semantic_action_record")),
        _nested_report_dict(turn_contract, "action", "metadata", "semantic_action"),
        _nested_report_dict(turn_contract, "action", "semantic_action"),
        _nested_report_dict(turn_contract, "action"),
        _nested_report_dict(turn_contract, "resolved_action", "semantic_action"),
        _nested_report_dict(turn_contract, "resolved_action"),
        _nested_report_dict(turn_contract, "resolved_result", "semantic_action"),
        _nested_report_dict(turn_contract, "resolved_result"),
        _nested_report_dict(result, "turn_contract", "action", "metadata", "semantic_action"),
        _nested_report_dict(result, "turn_contract", "action"),
    ]

    for mapping in candidates:
        if not mapping:
            continue
        action = _first_non_empty(
            mapping.get("semantic_action"),
            mapping.get("action_type"),
            mapping.get("action"),
            mapping.get("kind"),
            mapping.get("type"),
        )
        target = _first_non_empty(
            mapping.get("target_name"),
            mapping.get("target"),
            mapping.get("target_id"),
            mapping.get("provider_name"),
            mapping.get("provider_id"),
            mapping.get("object"),
        )
        if action or target:
            return {
                "action": action,
                "target": _strip_npc_prefix(target),
                "raw": mapping,
            }

    return {}


def _infer_timeline_action_from_text(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    text = " ".join(
        part for part in [
            _safe_str(row.get("player_input")),
            _safe_str(row.get("narration")),
            _safe_str(_safe_dict(row.get("turn_contract")).get("player_input")),
        ]
        if part
    )
    lower = text.lower()
    target = ""
    if "bran" in lower or "innkeeper" in lower or "bartender" in lower:
        target = "Bran"
    elif "traveler" in lower:
        target = "Cloaked Traveler"
    elif "patron" in lower:
        target = "Patron"
    elif "tavern" in lower or "room" in lower:
        target = "Tavern"

    if "trail" in lower or "clue" in lower:
        action = "inspect"
    elif any(term in lower for term in ("rent", "lodging", "room", "cot", "bed")):
        action = "rent_room"
    elif any(term in lower for term in ("buy", "pay", "order", "drink", "meal")):
        action = "service_inquiry"
    elif any(term in lower for term in ("ask", "question", "inquire", "press")):
        action = "ask"
    elif any(term in lower for term in ("search", "inspect", "examine", "trail", "marks", "clue")):
        action = "inspect"
    elif any(term in lower for term in ("scan", "observe", "watch", "listen", "look")):
        action = "observe"
    elif any(term in lower for term in ("leave", "travel", "road", "outside", "exit")):
        action = "travel"
    else:
        action = "player_action"

    return {
        "action": action,
        "target": target,
        "raw": {"text": text[:500]},
    }


def _human_timeline_action_label(action: Any, row: Dict[str, Any]) -> str:
    action_text = _safe_str(action).strip().lower()
    row = _safe_dict(row)
    raw = _safe_dict(_semantic_mapping_from_report_row(row).get("raw"))
    service_kind = _first_non_empty(
        raw.get("service_kind"),
        _safe_dict(raw.get("service_result")).get("service_kind"),
    )
    activity = _first_non_empty(raw.get("activity_label"), raw.get("summary"))

    if action_text == "service_inquiry" and service_kind == "lodging":
        return "Lodging Inquiry"
    if action_text == "service_inquiry":
        return "Service Inquiry"
    if action_text == "rent_room":
        return "Rent Room"
    if action_text == "social_activity":
        if activity and activity != "social_activity":
            return activity.replace("_", " ").title()
        return "Social Approach"
    if action_text == "observe":
        return "Observe the Scene"
    if action_text == "inspect":
        return "Inspect Clues"
    if action_text == "travel":
        return "Travel"
    if action_text == "ask":
        return "Ask a Question"
    if action_text == "use_item":
        return "Use Item"
    if action_text == "combat":
        return "Combat Action"
    if action_text and action_text != "unknown":
        return action_text.replace("_", " ").title()
    return "Player Action"


def _turn_title_from_row(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    semantic = _semantic_mapping_from_report_row(row)
    if not semantic:
        semantic = _infer_timeline_action_from_text(row)
    action = _first_non_empty(semantic.get("action"), "player_action")
    target = _first_non_empty(semantic.get("target"))
    title = _human_timeline_action_label(action, row)
    if target:
        return f"{title} · {target}"
    return title


def _row_narration_text(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    narration = row.get("narration")
    if isinstance(narration, dict):
        return _first_non_empty(narration.get("narration"), narration.get("text"), narration.get("summary"))
    return _first_non_empty(
        narration,
        row.get("narration_text"),
        _safe_dict(row.get("structured_narration")).get("narration"),
        _safe_dict(row.get("turn_contract")).get("player_input"),
        _safe_dict(_nested_report_dict(row, "turn_contract", "action", "metadata")).get("player_input"),
        _nested_report_dict(row, "turn_contract", "action", "metadata", "semantic_action").get("player_input"),
        row.get("player_input"),
    )


def _journal_timeline_beats(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    journal = _safe_dict(_safe_dict(summary).get("player_journal_summary"))
    beats: List[Dict[str, Any]] = []
    for entry in _as_list(journal.get("entries")):
        entry = _safe_dict(entry)
        start = _num(entry.get("start_turn"))
        end = _num(entry.get("end_turn"))
        text = _safe_str(entry.get("text"))
        inferred = _infer_rpg_title_from_text(text, fallback="Journal Entry")
        if inferred == "Journal Entry":
            title = f"Journal Entry · Turns {start}–{end}" if start or end else "Journal Entry"
        else:
            title = f"{inferred} · Turns {start}–{end}" if start or end else inferred
        beats.append(
            {
                "turn": end or start,
                "title": title,
                "body": _short_text(text, 420),
                "source": "journal",
            }
        )
    return beats


def _story_event_timeline_beats(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    story = _safe_dict(_safe_dict(summary).get("story_beat_summary"))
    beats: List[Dict[str, Any]] = []
    for beat in _as_list(story.get("beats")):
        beat = _safe_dict(beat)
        body = _first_non_empty(
            beat.get("story_summary"),
            beat.get("summary"),
            beat.get("text"),
            beat.get("description"),
        )
        explicit_title = _first_non_empty(
            beat.get("story_label"),
            beat.get("label"),
            beat.get("title"),
        )
        title = explicit_title or _timeline_title_from_body(body, fallback="Story Beat")
        if _is_generic_timeline_title(title):
            title = _timeline_title_from_body(
                _first_non_empty(
                    beat.get("player_input"),
                    beat.get("action"),
                    beat.get("summary"),
                    beat.get("text"),
                    beat.get("description"),
                    body,
                ),
                fallback="Story Event",
            )
        beats.append(
            {
                "turn": _num(beat.get("turn_index") or beat.get("turn")),
                "title": title,
                "body": _short_text(body, 360),
                "source": "story",
            }
        )
    return beats


def _turn_row_timeline_beats(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    beats: List[Dict[str, Any]] = []
    for row in _as_list(transcript):
        row = _safe_dict(row)
        turn = _turn_int(row)
        beats.append(
            {
                "turn": turn,
                "title": _turn_title_from_row(row),
                "body": _short_text(_row_narration_text(row), 320),
                "source": "turn",
            }
        )
    return beats


def _combined_adventure_beats(summary: Dict[str, Any], transcript: List[Dict[str, Any]], *, limit: int = 14) -> List[Dict[str, Any]]:
    beats = _story_event_timeline_beats(summary) + _journal_timeline_beats(summary)
    if not beats:
        beats = _turn_row_timeline_beats(transcript)
    finalized: List[Dict[str, Any]] = []
    for beat in beats:
        beat = _safe_dict(beat)
        title = _safe_str(beat.get("title"))
        body = _safe_str(beat.get("body"))
        if _is_generic_timeline_title(title):
            title = _timeline_title_from_body(body, fallback="Story Event")
        if _is_generic_timeline_title(title):
            title = "Story Event"
        if title or body:
            updated = dict(beat)
            updated["title"] = title
            finalized.append(updated)
    beats = finalized
    beats.sort(key=lambda beat: (_num(_safe_dict(beat).get("turn")), _safe_str(_safe_dict(beat).get("source"))))
    if len(beats) > int(limit or 14):
        return beats[:5] + [{"gap": True}] + beats[-max(0, int(limit or 14) - 5):]
    return beats


def _render_adventure_timeline(summary: Dict[str, Any], transcript: List[Dict[str, Any]], *, limit: int = 14) -> str:
    beats = _combined_adventure_beats(summary, transcript, limit=limit)
    if not beats:
        body = "<p>No turn timeline was available.</p>"
    else:
        items = []
        for beat in beats:
            beat = _safe_dict(beat)
            if beat.get("gap"):
                items.append('<li><div class="rpg-turn-label">…</div><div class="rpg-turn-body">Middle chronicle beats omitted from this top-level view. See Technical Debug for full data.</div></li>')
                continue
            turn = _num(beat.get("turn"))
            title = _first_non_empty(beat.get("title"), "Campaign Event")
            detail = _first_non_empty(beat.get("body"), "No event summary recorded.")
            source = _first_non_empty(beat.get("source"), "turn")
            items.append(
                "<li>"
                f'<div class="rpg-turn-label">Turn {html.escape(str(turn or "?"))}</div>'
                f'<div class="rpg-turn-title">{html.escape(title)}</div>'
                f'<div class="rpg-turn-body">{html.escape(detail[:360])}</div>'
                f'<div class="rpg-story-beat-source">Source: {html.escape(source)}</div>'
                "</li>"
            )
        body = f'<ol class="rpg-timeline">{"".join(items)}</ol>'
    return f"""
    <section class="rpg-card rpg-promoted-section span-8" id="adventure-timeline">
      <div class="rpg-section-title">
        <h2>Adventure Timeline</h2>
        <span class="rpg-badge neutral">Chronicle</span>
      </div>
      {body}
    </section>
    """


def _quest_evidence_turns(quest: Dict[str, Any], timeline: List[Dict[str, Any]]) -> List[int]:
    quest = _safe_dict(quest)
    qid = _first_non_empty(quest.get("quest_id"), quest.get("id"))
    turns: List[int] = []
    for event in _as_list(timeline):
        event = _safe_dict(event)
        if qid and _safe_str(event.get("quest_id")) != qid:
            continue
        turn = _num(event.get("turn_index") or event.get("turn"))
        if turn and turn not in turns:
            turns.append(turn)
    for key in ("evidence_turns", "turns", "updated_turns"):
        for turn in _as_list(quest.get(key)):
            try:
                value = int(turn)
            except Exception:
                continue
            if value and value not in turns:
                turns.append(value)
    return sorted(turns)


def _quest_objective_lines(quest: Dict[str, Any]) -> List[str]:
    quest = _safe_dict(quest)
    values: List[str] = []
    for key in ("objectives", "active_objectives", "current_objectives"):
        for objective in _as_list(quest.get(key)):
            if isinstance(objective, dict):
                label = _first_non_empty(
                    objective.get("title"),
                    objective.get("label"),
                    objective.get("objective"),
                    objective.get("summary"),
                    objective.get("id"),
                )
                status = _first_non_empty(objective.get("status"), objective.get("state"))
                if status:
                    label = f"{label} [{status}]"
                if label:
                    values.append(label)
            else:
                text = _safe_str(objective).strip()
                if text:
                    values.append(text)
    progress = _safe_str(quest.get("progress")).strip()
    if progress and progress not in values:
        values.append(progress)
    current = _first_non_empty(
        quest.get("objective"),
        quest.get("current_objective"),
        quest.get("next_objective"),
    )
    if current and current not in values:
        values.append(current)
    return values


def _quest_blocker_lines(quest: Dict[str, Any]) -> List[str]:
    quest = _safe_dict(quest)
    blockers: List[str] = []
    for key in ("blockers", "blocked_reasons", "missing_requirements", "warnings"):
        for item in _as_list(quest.get(key)):
            if isinstance(item, dict):
                text = _first_non_empty(item.get("summary"), item.get("message"), item.get("reason"), item.get("code"))
            else:
                text = _safe_str(item)
            if text:
                blockers.append(text)
    blocked = _first_non_empty(quest.get("blocked_reason"), quest.get("blocker"), quest.get("reason"))
    if blocked:
        blockers.append(blocked)
    return blockers


def _infer_quest_evidence_turns_from_transcript(
    quest: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    *,
    context: Optional[Dict[str, Any]] = None,
) -> List[int]:
    quest = _safe_dict(quest)
    title = _safe_str(quest.get("title") or quest.get("name") or quest.get("quest_id"))
    objective_text = " ".join(_quest_objective_lines(quest))
    haystack_terms = []
    for term in re.split(r"[^A-Za-z0-9']+", f"{title} {objective_text}"):
        term = term.strip().lower()
        if len(term) >= 4 and term not in {"quest", "active", "objective", "complete", "turn"}:
            haystack_terms.append(term)
    # Domain-specific terms seen in the current tavern/witness runs.
    haystack_terms.extend(["bran", "witness", "road", "bandit", "bandits", "heirloom", "tavern"])
    haystack_terms = sorted(set(haystack_terms))

    turns: List[int] = []
    for row in _as_list(transcript):
        row = _safe_dict(row)
        turn = _turn_int(row)
        if not turn:
            continue
        text = " ".join(
            [
                _safe_str(row.get("player_input")),
                _row_narration_text(row),
                str(row.get("turn_contract") or ""),
                str(row.get("runtime_state") or ""),
            ]
        ).lower()
        if any(term in text for term in haystack_terms):
            turns.append(turn)

    context = _safe_dict(context)
    for beat in _as_list(_safe_dict(context.get("story_beat_summary")).get("beats")):
        beat = _safe_dict(beat)
        turn = _num(beat.get("turn_index") or beat.get("turn"))
        text = str(beat).lower()
        if turn and any(term in text for term in haystack_terms):
            turns.append(turn)

    for entry in _as_list(_safe_dict(context.get("player_journal_summary")).get("entries")):
        entry = _safe_dict(entry)
        text = str(entry).lower()
        if any(term in text for term in haystack_terms):
            for key in ("start_turn", "end_turn", "turn", "turn_index"):
                value = _num(entry.get(key))
                if value:
                    turns.append(value)
    return sorted(set(turns))


def _quest_summary_from_latest_state(report_model: Dict[str, Any]) -> Dict[str, Any]:
    latest_state = _safe_dict(
        report_model.get("latest_state")
        or report_model.get("final_state")
        or report_model.get("final_authoritative_state")
    )
    quest_progress = _safe_dict(latest_state.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    if quests:
        return _quest_summary_from_quest_mapping(quests, source="latest_state.quest_progress")

    quest_log_state = _safe_dict(latest_state.get("quest_log_state"))
    quests = _safe_dict(quest_log_state.get("quests"))
    if quests:
        return _quest_summary_from_quest_mapping(quests, source="latest_state.quest_log_state")

    synthesized = _quest_summary_from_story_state(latest_state)
    if synthesized.get("quest_count"):
        return synthesized
    return {}


def _quest_summary_from_quest_mapping(quests: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    quests = _safe_dict(quests)
    rows: List[Dict[str, Any]] = []
    active_count = 0
    completed_count = 0
    for quest_id, quest_raw in sorted(quests.items()):
        quest = _safe_dict(quest_raw)
        objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
        objective_count = len(objectives)
        completed_objective_count = sum(
            1
            for obj in objectives
            if bool(obj.get("completed")) or _safe_str(obj.get("status")) == "completed"
        )
        status = _safe_str(quest.get("status") or ("completed" if objective_count and completed_objective_count >= objective_count else "active"))
        if status == "completed":
            completed_count += 1
        elif status == "active":
            active_count += 1
        rows.append(
            {
                "quest_id": _safe_str(quest.get("quest_id") or quest_id),
                "title": _safe_str(quest.get("title") or quest_id),
                "status": status,
                "completed": bool(quest.get("completed")) or status == "completed",
                "objective_count": objective_count,
                "completed_objective_count": completed_objective_count,
                "objectives": objectives,
            }
        )
    return {
        "quest_count": len(rows),
        "active_count": active_count,
        "completed_count": completed_count,
        "quests": rows,
        "source": source,
    }


def _quest_summary_from_story_state(latest_state: Dict[str, Any]) -> Dict[str, Any]:
    latest_state = _safe_dict(latest_state)
    facts = _safe_dict(latest_state.get("witness_search_facts"))
    arcs = _safe_dict(_safe_dict(latest_state.get("story_arc_milestone_state")).get("arcs"))
    witness_arc = _safe_dict(arcs.get("arc:witness_search") or arcs.get("witness_search"))
    milestones = [_safe_dict(row) for row in _safe_list(witness_arc.get("milestones"))]
    completed_ids = {
        _safe_str(row.get("milestone_id"))
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    }
    completed_titles = {
        _safe_str(row.get("title")).lower()
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    }
    find_done = (
        bool(facts.get("inspected_side_door"))
        or bool(facts.get("followed_road"))
        or "milestone:find_witness" in completed_ids
        or "find the witness" in completed_titles
    )
    report_done = (
        bool(facts.get("reported_to_bran"))
        or "milestone:report_findings_to_bran" in completed_ids
        or "report findings to bran" in completed_titles
        or "milestone:pursue_bandit_trail" in completed_ids
    )
    if not (find_done or report_done or facts):
        return {}
    witness_completed = bool(find_done and report_done)
    quests = [
        {
            "quest_id": "quest:witness_search",
            "title": "Witness Search",
            "status": "completed" if witness_completed else "active",
            "completed": witness_completed,
            "objective_count": 2,
            "completed_objective_count": int(find_done) + int(report_done),
            "objectives": [
                {
                    "objective_id": "objective:find_witness",
                    "summary": "Find the witness.",
                    "status": "completed" if find_done else "active",
                    "completed": find_done,
                },
                {
                    "objective_id": "objective:report_findings_to_bran",
                    "summary": "Report findings to Bran.",
                    "status": "completed" if report_done else "active",
                    "completed": report_done,
                },
            ],
        }
    ]
    if bool(facts.get("followed_road")) or "milestone:pursue_bandit_trail" in completed_ids:
        quests.append(
            {
                "quest_id": "quest:bandit_road",
                "title": "Bandit Road",
                "status": "active",
                "completed": False,
                "objective_count": 2,
                "completed_objective_count": 0,
                "objectives": [
                    {
                        "objective_id": "objective:inspect_road_tracks",
                        "summary": "Inspect the road for tracks or ambush signs.",
                        "status": "active",
                        "completed": False,
                    },
                    {
                        "objective_id": "objective:follow_bandit_road",
                        "summary": "Follow the bandit road trail.",
                        "status": "active",
                        "completed": False,
                    },
                ],
            }
        )
    return {
        "quest_count": len(quests),
        "active_count": sum(1 for row in quests if row["status"] == "active"),
        "completed_count": sum(1 for row in quests if row["status"] == "completed"),
        "quests": quests,
        "source": "latest_state.story_arc_milestone_state+witness_search_facts",
    }


def _render_quest_board(summary: Dict[str, Any], metrics: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    quest_summary = _safe_dict(
        _safe_dict(summary).get("quest_progress_summary")
        or _safe_dict(metrics).get("quest_progress_summary")
    )
    quests = _as_list(
        quest_summary.get("quests")
        or quest_summary.get("quest_rows")
        or quest_summary.get("items")
    )
    timeline = _as_list(quest_summary.get("timeline"))
    if quests:
        cards = ""
        for quest in quests[:12]:
            quest = _safe_dict(quest)
            title = _first_non_empty(quest.get("title"), quest.get("name"), quest.get("quest_id"), "Unknown Quest")
            status = _first_non_empty(quest.get("status"), quest.get("state"), "active")
            giver = _first_non_empty(quest.get("giver"), quest.get("quest_giver"), "Unknown")
            location = _first_non_empty(quest.get("location"), quest.get("source_location"), "")
            objectives = _quest_objective_lines(quest)
            blockers = _quest_blocker_lines(quest)
            evidence_turns = _quest_evidence_turns(quest, timeline)
            evidence_turns = sorted(
                set(evidence_turns)
                | set(_infer_quest_evidence_turns_from_transcript(quest, transcript, context=summary))
            )
            tags = "".join(
                f'<span class="rpg-tag">Turn {html.escape(str(turn))}</span>'
                for turn in evidence_turns[:8]
            )
            if not tags:
                tags = '<span class="rpg-tag">No evidence turns</span>'
            cards += f"""
            <article class="rpg-quest-card">
              <h3>{html.escape(title)}</h3>
              <div class="rpg-tag-row">
                <span class="rpg-badge {_status_badge_class(status)}">{html.escape(status)}</span>
                <span class="rpg-tag">Giver: {html.escape(giver)}</span>
                {f'<span class="rpg-tag">Location: {html.escape(location)}</span>' if location else ''}
              </div>
              <h4>Objectives</h4>
              {_html_list(objectives, empty="No objective details recorded.", limit=6)}
              <h4>Evidence Turns</h4>
              <div class="rpg-tag-row">{tags}</div>
              <h4>Blockers / Open Questions</h4>
              {_html_list(blockers, empty="No blockers recorded.", limit=4)}
            </article>
            """
        body = f'<div class="rpg-quest-grid">{cards}</div>'
    else:
        quest_count = _num(quest_summary.get("quest_count"))
        body = f"""
        <p>No expanded quest rows were available.</p>
        <div class="rpg-stat-grid">
          <div class="rpg-stat"><div class="rpg-stat-label">Quest Count</div><div class="rpg-stat-value">{html.escape(str(quest_count))}</div></div>
          <div class="rpg-stat"><div class="rpg-stat-label">Active</div><div class="rpg-stat-value">{html.escape(str(quest_summary.get('active_count') or 0))}</div></div>
          <div class="rpg-stat"><div class="rpg-stat-label">Completed</div><div class="rpg-stat-value">{html.escape(str(quest_summary.get('completed_count') or 0))}</div></div>
        </div>
        """

    return f"""
    <section class="rpg-card rpg-promoted-section span-4" id="quest-board">
      <div class="rpg-section-title">
        <h2>Quest Board</h2>
        <span class="rpg-badge neutral">Objectives</span>
      </div>
      {body}
    </section>
    """


def _npc_card_rows(summary: Dict[str, Any], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = _safe_dict(summary)
    metrics = _safe_dict(metrics)
    report_summary = _safe_dict(
        summary.get("npc_evolution_report_summary")
        or metrics.get("npc_evolution_report_summary")
    )
    cards = [_safe_dict(card) for card in _as_list(report_summary.get("cards")) if isinstance(card, dict)]
    if cards:
        return cards

    npc_summary = _safe_dict(
        summary.get("npc_evolution_summary")
        or summary.get("npc_profile_summary")
        or metrics.get("npc_evolution_summary")
        or metrics.get("npc_profile_summary")
    )
    rows = _as_list(npc_summary.get("npcs") or npc_summary.get("characters") or npc_summary.get("rows") or npc_summary.get("items"))
    return [_safe_dict(row) for row in rows if isinstance(row, dict)]


def _npc_memory_lines(card: Dict[str, Any]) -> List[str]:
    card = _safe_dict(card)
    return _dedupe_texts_fuzzy(_as_list(card.get("memories")), limit=8)


def _npc_future_hook_lines(card: Dict[str, Any]) -> List[str]:
    return _dedupe_texts_fuzzy(_as_list(_safe_dict(card).get("future_hooks")), limit=8)


def _npc_semantic_intent_lines(card: Dict[str, Any]) -> List[str]:
    return _dedupe_texts_fuzzy(_as_list(_safe_dict(card).get("semantic_intents")), limit=8)


def _npc_axes_summary(card: Dict[str, Any]) -> str:
    axes = _safe_dict(_safe_dict(card).get("axes"))
    if not axes:
        return ""
    parts = []
    for key, value in sorted(axes.items()):
        if isinstance(value, dict):
            val = value.get("value") or value.get("score") or value.get("current")
        else:
            val = value
        parts.append(f"{key}: {val}")
    return ", ".join(parts[:8])


def _npc_role_from_card(card: Dict[str, Any]) -> str:
    card = _safe_dict(card)
    role = _first_non_empty(
        card.get("role"),
        card.get("archetype"),
        card.get("title"),
        _safe_dict(card.get("profile")).get("role"),
        _safe_dict(card.get("profile")).get("archetype"),
    )
    if role and role.lower() != "npc":
        return role
    name = _first_non_empty(card.get("name"), card.get("npc_id"), card.get("id"))
    if name.lower() == "bran":
        return "Innkeeper"
    if "traveler" in name.lower():
        return "Traveler"
    if "guard" in name.lower():
        return "Guard"
    return role or "NPC"


def _render_npc_chronicle(summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    npcs = _npc_card_rows(summary, metrics)
    if npcs:
        cards = ""
        for npc in npcs[:8]:
            npc = _safe_dict(npc)
            name = _first_non_empty(npc.get("name"), npc.get("npc_id"), npc.get("id"), "Unknown NPC")
            role = _npc_role_from_card(npc)
            stage = _first_non_empty(npc.get("arc_stage"), npc.get("latest_stage"), npc.get("stage"), "stable")
            profile_path = _first_non_empty(npc.get("profile_path"), npc.get("path"))
            signal_count = _num(npc.get("signal_count") or npc.get("signals_consumed"))
            axes = _npc_axes_summary(npc)
            memories = _npc_memory_lines(npc)
            hooks = _npc_future_hook_lines(npc)
            intents = _npc_semantic_intent_lines(npc)
            cards += f"""
            <article class="rpg-character-card">
              <h3>{html.escape(name)}</h3>
              <div class="rpg-tag-row">
                <span class="rpg-tag">Role: {html.escape(role)}</span>
                <span class="rpg-tag">Stage: {html.escape(stage)}</span>
                <span class="rpg-tag">Signals: {html.escape(str(signal_count))}</span>
              </div>
              {f'<p><strong>Axes:</strong> {html.escape(axes)}</p>' if axes else ''}
              <h4>Memory Highlights</h4>
              {_html_list(memories, empty="No memory highlights recorded.", limit=4)}
              <h4>Intent / Relationship Signals</h4>
              {_html_list(intents, empty="No intent signals recorded.", limit=4)}
              <h4>Future Hooks</h4>
              {_html_list(hooks, empty="No future hooks recorded.", limit=4)}
              {f'<p class="rpg-muted-line">Profile: {html.escape(profile_path)}</p>' if profile_path else ''}
            </article>
            """
        body = f'<div class="rpg-npc-grid">{cards}</div>'
    else:
        body = "<p>No expanded NPC cards were available yet. This section is ready for N83 NPC evolution card data.</p>"

    return f"""
    <section class="rpg-card rpg-promoted-section span-12" id="npc-chronicle">
      <div class="rpg-section-title">
        <h2>NPC Chronicle</h2>
        <span class="rpg-badge neutral">Social State</span>
      </div>
      {body}
    </section>
    """


def _infer_campaign_location_name(summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    metrics = _safe_dict(metrics)
    candidates: List[str] = []

    for quest in _as_list(_safe_dict(summary.get("quest_progress_summary")).get("quests")):
        quest = _safe_dict(quest)
        loc = _first_non_empty(quest.get("location"), quest.get("source_location"))
        if loc:
            candidates.append(loc)

    for source in (
        summary.get("lore_worldbuilding_summary"),
        metrics.get("lore_worldbuilding_summary"),
        summary.get("story_beat_summary"),
        summary.get("player_journal_summary"),
    ):
        text = str(source)
        if "Rusty Flagon" in text:
            candidates.append("Rusty Flagon Tavern")
        elif "tavern" in text.lower():
            candidates.append("Tavern")

    for state_key in ("initial_state", "latest_state", "final_state", "simulation_state"):
        state = _safe_dict(summary.get(state_key) or metrics.get(state_key))
        loc = _first_non_empty(
            state.get("location"),
            state.get("current_location"),
            _safe_dict(state.get("location_state")).get("name"),
        )
        if loc:
            candidates.append(loc)

    for candidate in candidates:
        candidate = _safe_str(candidate).strip()
        if candidate and candidate.lower() != "unknown location":
            return candidate
    return ""


def _location_name_from_row(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    sim = _safe_dict(row.get("simulation_state"))
    runtime = _safe_dict(row.get("runtime_state"))
    turn_contract = _safe_dict(row.get("turn_contract"))
    return _first_non_empty(
        row.get("location"),
        row.get("location_name"),
        sim.get("location"),
        sim.get("current_location"),
        _safe_dict(sim.get("location_state")).get("name"),
        runtime.get("location"),
        runtime.get("current_location"),
        turn_contract.get("location"),
        "Unknown Location",
    )


_NPC_STRUCTURAL_KEYS = {
    "speaker",
    "line",
    "text",
    "dialogue",
    "npc",
    "npcs",
    "metadata",
    "summary",
    "description",
    "relationship",
    "relationships",
    "memory",
    "memories",
}


def _looks_like_npc_name(value: Any) -> bool:
    text = _safe_str(value).strip()
    if not text:
        return False
    if text.lower() in _NPC_STRUCTURAL_KEYS:
        return False
    if len(text) > 80:
        return False
    return any(ch.isalpha() for ch in text)


def _npcs_from_row(row: Dict[str, Any]) -> List[str]:
    row = _safe_dict(row)
    names: List[str] = []
    for source in (
        row.get("npc"),
        row.get("npcs"),
        _safe_dict(row.get("simulation_state")).get("npcs"),
        _safe_dict(row.get("runtime_state")).get("npcs"),
    ):
        if isinstance(source, dict):
            if _safe_str(source.get("speaker")):
                names.append(source.get("speaker"))
            for key, value in source.items():
                if isinstance(value, dict):
                    names.append(_first_non_empty(value.get("name"), key))
                elif isinstance(key, str) and _looks_like_npc_name(key):
                    names.append(key)
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    names.append(_first_non_empty(item.get("name"), item.get("npc_id"), item.get("id")))
                else:
                    names.append(_safe_str(item))
    return sorted({name for name in names if _looks_like_npc_name(name)})


def _services_from_row(row: Dict[str, Any]) -> List[str]:
    row = _safe_dict(row)
    values: List[str] = []

    for key in ("service_result", "merchant_result", "interaction_result"):
        result = _safe_dict(row.get(key))
        service = _first_non_empty(
            result.get("service_kind"),
            result.get("service"),
            result.get("service_id"),
            result.get("kind"),
        )
        if service:
            values.append(_normalize_service_label(service))

    semantic = _semantic_mapping_from_report_row(row)
    action = _safe_str(semantic.get("action"))
    raw = _safe_dict(semantic.get("raw"))
    service_kind = _first_non_empty(
        raw.get("service_kind"),
        raw.get("service"),
        raw.get("provider_service"),
        raw.get("kind"),
    )
    if service_kind:
        values.append(_normalize_service_label(service_kind))
    if action in ("service_inquiry", "rent_room", "buy_service", "purchase_service"):
        values.append(action)
    if action == "service_inquiry" and _contains_any(str(raw), ["lodging", "room", "inn"]):
        values.append("lodging")
    if action == "rent_room":
        values.append("lodging")

    # N83.1.2: actual report row shapes may bury semantic/service metadata
    # under turn_contract.action.metadata.semantic_action, result.turn_contract,
    # background attachments, or serialized debug dicts. Recursively scan the
    # row as a last-resort structured fallback.
    values.extend(_scan_service_labels(row))

    cleaned = []
    for value in values:
        label = _normalize_service_label(value)
        if label and label in _SERVICE_ACTION_NAMES and label not in cleaned:
            cleaned.append(label)

    # Stable, useful order for the visible report.
    order = ["service_inquiry", "rent_room", "lodging", "buy_service", "purchase_service"]
    return [label for label in order if label in cleaned]


_SERVICE_ACTION_NAMES = {
    "service_inquiry",
    "rent_room",
    "buy_service",
    "purchase_service",
    "lodging",
}


def _normalize_service_label(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    text = text.replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_]+", "", text)
    return text.lower()


def _service_labels_from_mapping(mapping: Dict[str, Any]) -> List[str]:
    mapping = _safe_dict(mapping)
    values: List[str] = []

    for key in (
        "action_type",
        "semantic_action",
        "action",
        "kind",
        "type",
        "service_kind",
        "service",
        "service_id",
        "provider_service",
        "interaction_type",
    ):
        label = _normalize_service_label(mapping.get(key))
        if label in _SERVICE_ACTION_NAMES:
            values.append(label)

    # If the action is service_inquiry/rent_room and metadata text mentions
    # lodging/room/inn, include lodging as the useful RPG service label.
    text = str(mapping).lower()
    if any(label in values for label in ("service_inquiry", "rent_room")):
        if any(term in text for term in ("lodging", "room", "inn", "bed")):
            values.append("lodging")

    if "rent_room" in text:
        values.append("rent_room")
        values.append("lodging")
    if "service_inquiry" in text:
        values.append("service_inquiry")
    if "lodging" in text:
        values.append("lodging")

    return values


def _scan_service_labels(value: Any, *, depth: int = 0) -> List[str]:
    if depth > 6:
        return []

    labels: List[str] = []

    if isinstance(value, dict):
        labels.extend(_service_labels_from_mapping(value))
        for nested in value.values():
            labels.extend(_scan_service_labels(nested, depth=depth + 1))
    elif isinstance(value, list):
        for item in value:
            labels.extend(_scan_service_labels(item, depth=depth + 1))
    elif isinstance(value, tuple):
        for item in value:
            labels.extend(_scan_service_labels(item, depth=depth + 1))
    elif isinstance(value, str):
        lower = value.lower()
        if "service_inquiry" in lower:
            labels.append("service_inquiry")
        if "rent_room" in lower:
            labels.append("rent_room")
            labels.append("lodging")
        if "lodging" in lower:
            labels.append("lodging")

    return labels


def _campaign_service_labels_from_context(summary: Dict[str, Any], metrics: Dict[str, Any], transcript: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    values.extend(_scan_service_labels(summary))
    values.extend(_scan_service_labels(metrics))
    values.extend(_scan_service_labels(transcript))

    cleaned = []
    for value in values:
        label = _normalize_service_label(value)
        if label and label in _SERVICE_ACTION_NAMES and label not in cleaned:
            cleaned.append(label)

    order = ["service_inquiry", "rent_room", "lodging", "buy_service", "purchase_service"]
    return [label for label in order if label in cleaned]


def _build_location_journey_rows(summary: Dict[str, Any], metrics: Dict[str, Any], transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    location_summary = _safe_dict(
        _safe_dict(summary).get("location_journey_summary")
        or _safe_dict(metrics).get("location_journey_summary")
    )
    expanded = _as_list(location_summary.get("locations") or location_summary.get("rows"))
    if expanded and isinstance(expanded[0], dict):
        return [_safe_dict(row) for row in expanded]

    inferred_location = _infer_campaign_location_name(summary, metrics)
    by_location: Dict[str, Dict[str, Any]] = {}
    for row in _as_list(transcript):
        row = _safe_dict(row)
        turn = _turn_int(row)
        location = _location_name_from_row(row)
        if location == "Unknown Location" and inferred_location:
            location = inferred_location
        bucket = by_location.setdefault(
            location,
            {
                "name": location,
                "turns": [],
                "events": [],
                "npcs": set(),
                "services": set(),
                "open_threads": [],
            },
        )
        if turn:
            bucket["turns"].append(turn)
        title = _turn_title_from_row(row)
        narration = _row_narration_text(row)
        if title or narration:
            bucket["events"].append(f"Turn {turn}: {title} — {_short_text(narration, 160)}")
        for npc in _npcs_from_row(row):
            bucket["npcs"].add(npc)
        for service in _services_from_row(row):
            bucket["services"].add(service)
        for hook in _as_list(row.get("followup_hooks")):
            text = _safe_str(hook if not isinstance(hook, dict) else hook.get("summary") or hook.get("hook"))
            if text:
                bucket["open_threads"].append(text)

    if not by_location and inferred_location:
        by_location[inferred_location] = {
            "name": inferred_location,
            "turns": [],
            "events": [],
            "npcs": set(),
            "services": set(),
            "open_threads": [],
        }

    rows: List[Dict[str, Any]] = []
    for bucket in by_location.values():
        turns = sorted(set(bucket["turns"]))
        rows.append(
            {
                "name": bucket["name"],
                "turns": turns,
                "turn_range": f"{turns[0]}–{turns[-1]}" if turns else "",
                "events": bucket["events"][:6],
                "npcs": sorted(bucket["npcs"]),
                "services": sorted(bucket["services"]),
                "open_threads": bucket["open_threads"][:6],
            }
        )
    return rows


def _render_location_journey(summary: Dict[str, Any], metrics: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    locations = _build_location_journey_rows(summary, metrics, transcript)
    if locations:
        campaign_services = _campaign_service_labels_from_context(summary, metrics, transcript)
        cards = ""
        path = " → ".join(html.escape(_safe_str(loc.get("name"))) for loc in locations[:12])
        for loc in locations[:8]:
            loc = _safe_dict(loc)
            loc_services = _as_list(loc.get("services"))
            if not loc_services and campaign_services:
                loc_services = campaign_services
            cards += f"""
            <article class="rpg-location-card">
              <h3>{html.escape(_first_non_empty(loc.get('name'), 'Unknown Location'))}</h3>
              <div class="rpg-tag-row">
                <span class="rpg-tag">Turns: {html.escape(_first_non_empty(loc.get('turn_range'), str(loc.get('turns') or '')))}</span>
              </div>
              <h4>Events</h4>
              {_html_list(_as_list(loc.get('events')), empty="No location events recorded.", limit=5)}
              <h4>NPCs Present</h4>
              {_html_list(_as_list(loc.get('npcs')), empty="No NPC presence recorded.", limit=6)}
              <h4>Services / Interactions</h4>
              {_html_list(loc_services, empty="No services recorded.", limit=5)}
              <h4>Open Threads</h4>
              {_html_list(_as_list(loc.get('open_threads')), empty="No open threads recorded.", limit=4)}
            </article>
            """
        body = f"<p><strong>Journey Path:</strong> {path}</p><div class=\"rpg-location-grid\">{cards}</div>"
    else:
        body = "<p>No location path was available yet. N83 can expand this with per-location events and NPC presence.</p>"

    return f"""
    <section class="rpg-card span-6" id="location-journey">
      <div class="rpg-section-title">
        <h2>Location Journey</h2>
        <span class="rpg-badge neutral">World Path</span>
      </div>
      {body}
    </section>
    """


def _currency_from_rows(rows: Any) -> Dict[str, Any]:
    currency: Dict[str, Any] = {}
    for row in _as_list(rows):
        if isinstance(row, (list, tuple)):
            key = _safe_str(row[0] if len(row) > 0 else "").strip()
            value = row[1] if len(row) > 1 else 0
            if key:
                currency[key] = value
            continue
        row = _safe_dict(row)
        key = _first_non_empty(row.get("currency"), row.get("name"), row.get("kind"), row.get("type"))
        if not key:
            continue
        value = row.get("amount")
        if value is None:
            value = row.get("value")
        if value is None:
            value = row.get("count")
        if value is None:
            value = row.get("quantity")
        currency[key] = value if value is not None else 0
    return currency


def _items_from_rows(rows: Any) -> List[Any]:
    items: List[Any] = []
    for row in _as_list(rows):
        if isinstance(row, str):
            if row.strip():
                items.append(row.strip())
            continue
        if isinstance(row, (list, tuple)):
            name = _safe_str(row[0] if len(row) > 0 else "").strip()
            if not name:
                continue
            quantity = row[1] if len(row) > 1 else None
            category = row[2] if len(row) > 2 else ""
            description = row[3] if len(row) > 3 else ""
            items.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "category": category,
                    "description": description,
                }
            )
            continue
        row = _safe_dict(row)
        name = _first_non_empty(row.get("name"), row.get("item_name"), row.get("item_id"), row.get("id"))
        if not name:
            continue
        item = dict(row)
        item["name"] = name
        items.append(item)
    return items


def _player_sheet_model(summary: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    context = _merge_report_contexts(summary=summary, metrics=metrics)
    summary = context
    metrics = context
    player = _safe_dict(
        summary.get("player_character_summary")
        or summary.get("player_progression_summary")
        or metrics.get("player_character_summary")
        or metrics.get("player_progression_summary")
    )
    progression_view = _safe_dict(
        summary.get("player_progression_view")
        or metrics.get("player_progression_view")
        or player.get("view")
    )
    inventory_end = _safe_dict(
        summary.get("inventory_end")
        or metrics.get("inventory_end")
        or player.get("inventory")
    )
    inventory_view = _safe_dict(
        summary.get("inventory_end_view")
        or metrics.get("inventory_end_view")
    )
    currency = (
        _safe_dict(inventory_end.get("currency"))
        or _safe_dict(inventory_view.get("currency"))
        or _currency_from_rows(inventory_view.get("currency_rows"))
        or _currency_from_rows(summary.get("currency_rows"))
        or _currency_from_rows(metrics.get("currency_rows"))
        or _currency_from_rows(_report_context_value(context, "inventory_currency_rows"))
        or _safe_dict(player.get("currency"))
    )
    items = (
        _as_list(inventory_end.get("items"))
        or _as_list(inventory_view.get("items"))
        or _items_from_rows(inventory_view.get("item_rows"))
        or _items_from_rows(summary.get("item_rows"))
        or _items_from_rows(metrics.get("item_rows"))
        or _items_from_rows(_report_context_value(context, "inventory_item_rows"))
        or _as_list(player.get("items"))
    )
    if not items and isinstance(inventory_end.get("items"), dict):
        items = list(_safe_dict(inventory_end.get("items")).values())
    latest_state = _safe_dict(summary.get("latest_state") or metrics.get("latest_state"))
    return {
        "name": _first_non_empty(player.get("name"), progression_view.get("name"), "Player Character"),
        "level": _first_non_empty(player.get("level"), progression_view.get("level"), latest_state.get("level"), "1"),
        "xp": _first_non_empty(player.get("xp"), progression_view.get("xp"), latest_state.get("xp"), "0"),
        "currency": currency,
        "items": items,
        "known_leads": _as_list(player.get("known_leads") or progression_view.get("known_leads")),
        "objectives": _as_list(player.get("objectives") or progression_view.get("objectives")),
        "reputation": _safe_dict(player.get("reputation") or progression_view.get("reputation")),
        "journal_entries": _num(_safe_dict(summary.get("player_journal_summary")).get("entry_count")),
    }


def _render_player_sheet(summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    player = _player_sheet_model(summary, metrics)
    items = [_format_item_name(item) for item in _as_list(player.get("items")) if _format_item_name(item)]
    reputation = _safe_dict(player.get("reputation"))
    body = f"""
      <div class="rpg-stat-grid">
        <div class="rpg-stat">
          <div class="rpg-stat-label">Character</div>
          <div class="rpg-stat-value">{html.escape(_safe_str(player.get('name')))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Level</div>
          <div class="rpg-stat-value">{html.escape(_safe_str(player.get('level')))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">XP</div>
          <div class="rpg-stat-value">{html.escape(_safe_str(player.get('xp')))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Currency</div>
          <div class="rpg-stat-value">{html.escape(_format_currency(player.get('currency')))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Inventory Items</div>
          <div class="rpg-stat-value">{html.escape(str(len(items)))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Journal Entries</div>
          <div class="rpg-stat-value">{html.escape(str(_num(player.get('journal_entries'))))}</div>
        </div>
      </div>
      <div class="rpg-two-col" style="margin-top: 14px;">
        <div class="rpg-mini-card">
          <h3>Inventory</h3>
          {_html_list(items, empty="Inventory is empty.", limit=12)}
        </div>
        <div class="rpg-mini-card">
          <h3>Known Leads / Objectives</h3>
          {_html_list(_as_list(player.get('known_leads')) + _as_list(player.get('objectives')), empty="No known leads recorded.", limit=10)}
        </div>
        <div class="rpg-mini-card">
          <h3>Reputation</h3>
          {_html_list([f"{key}: {value}" for key, value in reputation.items()], empty="No reputation entries recorded.", limit=8)}
        </div>
      </div>
    """
    return f"""
    <section class="rpg-card span-6" id="player-sheet">
      <div class="rpg-section-title">
        <h2>Player Sheet</h2>
        <span class="rpg-badge neutral">Character State</span>
      </div>
      {body}
    </section>
    """


def _render_qa_dashboard(summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    metrics = _safe_dict(metrics)
    quality = _safe_dict(summary.get("quality_gate_summary") or metrics.get("quality_gate_summary"))
    gates = _safe_dict(quality.get("gates"))
    background = _safe_dict(summary.get("background_result_timing_summary") or metrics.get("background_result_timing_summary"))
    perf = _safe_dict(summary.get("performance_budget_summary") or metrics.get("performance_budget_summary"))
    live = _safe_dict(perf.get("live_blocking"))
    reconciliation = _safe_dict(summary.get("quest_reconciliation_summary") or metrics.get("quest_reconciliation_summary"))

    gate_rows = ""
    for name, value in list(gates.items())[:40]:
        gate_rows += (
            "<tr>"
            f"<td>{html.escape(str(name))}</td>"
            f'<td><span class="rpg-badge {_status_badge_class(value)}">{html.escape(_yes_no(value))}</span></td>'
            "</tr>"
        )
    if not gate_rows:
        gate_rows = "<tr><td colspan='2'>No gate details available.</td></tr>"

    return f"""
    <section class="rpg-card span-12" id="qa-dashboard">
      <div class="rpg-section-title">
        <h2>QA Dashboard</h2>
        <span class="rpg-badge {_status_badge_class(quality.get('ok', True))}">{html.escape(_yes_no(quality.get('ok', True)))}</span>
      </div>
      <div class="rpg-stat-grid">
        <div class="rpg-stat">
          <div class="rpg-stat-label">Submitted BG Jobs</div>
          <div class="rpg-stat-value">{html.escape(str(background.get('jobs_submitted') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Pre-Turn Attach Rate</div>
          <div class="rpg-stat-value">{html.escape(_pct(background.get('pre_turn_attach_rate') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Missing BG Jobs</div>
          <div class="rpg-stat-value">{html.escape(str(background.get('missing_job_count') or 0))}</div>
        </div>
        <div class="rpg-stat">
          <div class="rpg-stat-label">Avg Live Blocking</div>
          <div class="rpg-stat-value">{html.escape(str(live.get('avg_human_playable_blocking_ms') or 0))}ms</div>
        </div>
                <div class="rpg-stat">
                    <div class="rpg-stat-label">Quest Reconciliation</div>
                    <div class="rpg-stat-value">{html.escape(str(reconciliation.get('count') or 0))}</div>
                </div>
                <div class="rpg-stat">
                    <div class="rpg-stat-label">Reconciliation Errors</div>
                    <div class="rpg-stat-value">{html.escape(str(len(_safe_list(reconciliation.get('errors')))))}</div>
                </div>
      </div>
      <h3>Quality Gates</h3>
      <table class="rpg-table">
        <thead><tr><th>Gate</th><th>Status</th></tr></thead>
        <tbody>{gate_rows}</tbody>
      </table>
    </section>
    """


def _legacy_section_group(title: str, html_content: str, *, open_by_default: bool = False) -> str:
    html_content = _strip_legacy_autoplay_report_partial(html_content)
    html_content = _prefix_legacy_section_ids(html_content)
    open_attr = " open" if open_by_default else ""
    return f"""
    <details class="rpg-debug-group"{open_attr}>
      <summary>{html.escape(title)}</summary>
      <div class="rpg-debug-group-body">
        {html_content}
      </div>
    </details>
    """


def _split_legacy_html_into_debug_groups(legacy_html: str) -> Dict[str, str]:
    text = _strip_legacy_autoplay_report_partial(legacy_html)
    if not text.strip():
        return {}

    buckets: Dict[str, List[str]] = {
        "quality": [],
        "background": [],
        "performance": [],
        "campaign": [],
        "timeline": [],
        "raw": [],
    }

    # Split before each top-level section/article that has an ID. This is
    # deliberately simple and robust for generated report HTML.
    parts = re.split(r'(?=<(?:section|article)\b[^>]*\bid="[^"]+"[^>]*>)', text)
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        lower = chunk.lower()
        if any(key in lower for key in ("quality", "hundred-turn", "action-diversity", "long-run")):
            buckets["quality"].append(chunk)
        elif any(key in lower for key in ("background", "deferred", "advisory", "narration job")):
            buckets["background"].append(chunk)
        elif any(key in lower for key in ("performance", "latency", "budget", "timing", "token", "prompt")):
            buckets["performance"].append(chunk)
        elif any(key in lower for key in ("campaign-journal", "quest", "npc", "location", "player", "lore", "story")):
            buckets["campaign"].append(chunk)
        elif any(key in lower for key in ("timeline", "calendar", "turn-by-turn", "turns")):
            buckets["timeline"].append(chunk)
        else:
            buckets["raw"].append(chunk)

    return {key: "\n".join(values) for key, values in buckets.items() if values}


def _wrap_technical_debug_groups(groups: Dict[str, str]) -> str:
    groups = _safe_dict(groups)
    ordered = [
        ("Quality Gates", groups.get("quality")),
        ("Background Pipeline", groups.get("background")),
        ("Performance", groups.get("performance")),
        ("Campaign Data", groups.get("campaign")),
        ("Timeline / Progress", groups.get("timeline")),
        ("Console / Raw Debug", groups.get("raw")),
    ]
    body = ""
    for title, content in ordered:
        if _safe_str(content).strip():
            body += _legacy_section_group(title, content)
    if not body:
        body = _legacy_section_group("Legacy Report", groups.get("legacy") or "")

    return f"""
    <section class="rpg-card dark span-12" id="technical-debug">
      <div class="rpg-section-title">
        <h2>Technical Debug</h2>
        <span class="rpg-badge neutral">Grouped Raw Data</span>
      </div>
      <p class="rpg-debug-note">
        Technical sections are grouped below. Legacy anchors are prefixed with
        <code>legacy-</code> so top-level RPG navigation remains stable.
        The themed Autoplay Campaign Report summary is promoted near the top of this page.
      </p>
      <div class="rpg-debug-grid">
        {body}
      </div>
    </section>
    """


def _wrap_technical_debug_section(existing_html: str) -> str:
    existing_html = _strip_legacy_autoplay_report_partial(existing_html)
    existing_html = _prefix_legacy_section_ids(existing_html)
    return f"""
    <section class="rpg-card dark span-12" id="technical-debug">
      <div class="rpg-section-title">
        <h2>Technical Debug</h2>
        <span class="rpg-badge neutral">Grouped Raw Data</span>
      </div>
      <p class="rpg-debug-note">
        Technical sections are grouped below. Legacy anchors are prefixed with
        <code>legacy-</code> so top-level RPG navigation remains stable.
      </p>
      <details class="rpg-debug">
        <summary>Show raw / legacy report sections</summary>
        <div class="rpg-debug-body">
          <p class="rpg-debug-note">
            Legacy report sections are preserved below with prefixed anchors
            such as <code>legacy-campaign-journal</code> to avoid conflicts with
            the RPG chronicle navigation above.
          </p>
          {existing_html}
        </div>
      </details>
    </section>
    """


def _latest_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(transcript):
        final_state = _safe_dict(row.get("final_authoritative_state"))
        if final_state:
            return final_state
        turn_result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(turn_result.get("simulation_state"))
        if state:
            return state
    return {}


def _latest_state_source(transcript: List[Dict[str, Any]]) -> str:
    for row in reversed(transcript):
        if _safe_dict(row.get("final_authoritative_state")):
            return "final_authoritative_state"
        turn_result = _safe_dict(row.get("turn_result"))
        if _safe_dict(turn_result.get("simulation_state")):
            return "turn_result.simulation_state"
    return "none"



def _story_arc_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    arcs = _safe_dict(_safe_dict(state.get("story_arc_state")).get("arcs"))
    rows = []
    for arc_id, arc in arcs.items():
        arc = _safe_dict(arc)
        row = dict(arc)
        row.setdefault("arc_id", arc_id)
        rows.append(row)
    return rows


def _milestone_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = _safe_dict(state.get("story_arc_milestone_state"))
    arcs = _safe_dict(root.get("arcs"))
    rows = []
    for arc_id, bucket in arcs.items():
        for milestone in _safe_list(_safe_dict(bucket).get("milestones")):
            if isinstance(milestone, dict):
                row = dict(milestone)
                row.setdefault("arc_id", arc_id)
                rows.append(row)
    return rows


def _journal_entries(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in _safe_list(_safe_dict(state.get("campaign_journal_state")).get("entries"))
        if isinstance(row, dict)
    ]


def _story_events(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in _safe_list(_safe_dict(state.get("story_event_queue_state")).get("queue"))
        if isinstance(row, dict)
    ]


def _npc_rows(state: Dict[str, Any], transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name: Dict[str, Dict[str, Any]] = {}

    # Known state roots vary across bundles; collect likely NPC/profile stores.
    candidate_roots = [
        _safe_dict(state.get("npc_profile_state")).get("profiles"),
        _safe_dict(state.get("npc_evolution_state")).get("npcs"),
        _safe_dict(state.get("social_state")).get("npcs"),
        _safe_dict(state.get("character_state")).get("npcs"),
        state.get("npcs"),
    ]
    for root in candidate_roots:
        if isinstance(root, dict):
            for key, value in root.items():
                value = _safe_dict(value)
                name = _first_non_empty(value.get("name"), value.get("npc_id"), key)
                if name:
                    by_name.setdefault(name, {}).update(value)
                    by_name[name].setdefault("name", name)
        elif isinstance(root, list):
            for value in root:
                value = _safe_dict(value)
                name = _first_non_empty(value.get("name"), value.get("npc_id"))
                if name:
                    by_name.setdefault(name, {}).update(value)
                    by_name[name].setdefault("name", name)

    # Also discover NPCs from dialogue.
    for row in transcript:
        dialogue = extract_dialogue(row)
        speaker = dialogue.get("speaker")
        if speaker:
            by_name.setdefault(speaker, {"name": speaker})
            by_name[speaker]["dialogue_turns"] = int(by_name[speaker].get("dialogue_turns") or 0) + 1

    return sorted(by_name.values(), key=lambda row: str(row.get("name") or ""))


def _player_progression(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        state.get("player_state"),
        state.get("character_stats"),
        _safe_dict(state.get("party_state")).get("player"),
        _safe_dict(state.get("runtime")).get("player"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _lore_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    lore = _safe_dict(state.get("lore_state"))
    rows = []
    for key in ("facts", "entries", "locations", "factions", "rumors"):
        value = lore.get(key)
        if isinstance(value, dict):
            for item_id, item in value.items():
                item = _safe_dict(item)
                rows.append({"type": key, "id": item_id, **item})
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    rows.append({"type": key, "id": item.get("id") or idx, **item})
                else:
                    rows.append({"type": key, "id": idx, "text": str(item)})
    return rows


def compute_dialogue_coverage(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_turns = len(timeline)
    social_turns = [row for row in timeline if row.get("social_action")]
    npc_response_turns = [
        row
        for row in timeline
        if _safe_dict(row.get("npc")).get("line")
    ]
    missing_social_turns = [
        row
        for row in social_turns
        if row.get("missing_npc_response")
    ]
    echoed_narration_turns = [
        row
        for row in timeline
        if row.get("echoed_narration")
    ]
    source_counts = Counter(
        _safe_str(row.get("dialogue_source") or "none")
        for row in timeline
    )
    hook_dialogue_turns = [
        row for row in timeline if row.get("dialogue_source") == "story_hook_display"
    ]
    base_dialogue_turns = [
        row
        for row in timeline
        if row.get("dialogue_source")
        in {
            "raw_ai_payload",
            "raw_npc",
            "conversation_beat",
            "real_runtime_provider",
            "real_runtime_fallback",
            "base_runtime_deterministic",
            "base_runtime_provider",
        }
    ]
    return {
        "total_turns": total_turns,
        "social_turn_count": len(social_turns),
        "npc_response_turn_count": len(npc_response_turns),
        "npc_response_rate": (len(npc_response_turns) / total_turns) if total_turns else 0.0,
        "social_turn_missing_npc_response_count": len(missing_social_turns),
        "social_turn_missing_npc_response_rate": (
            len(missing_social_turns) / len(social_turns) if social_turns else 0.0
        ),
        "echoed_narration_turn_count": len(echoed_narration_turns),
        "echoed_narration_rate": (
            len(echoed_narration_turns) / total_turns if total_turns else 0.0
        ),
        "dialogue_source_counts": dict(source_counts),
        "hook_dialogue_turn_count": len(hook_dialogue_turns),
        "base_runtime_dialogue_turn_count": len(base_dialogue_turns),
        "real_runtime_dialogue_turn_count": int(source_counts.get("real_runtime_provider") or 0)
        + int(source_counts.get("real_runtime_fallback") or 0),
        "real_runtime_provider_dialogue_turn_count": int(source_counts.get("real_runtime_provider") or 0),
        "real_runtime_fallback_dialogue_turn_count": int(source_counts.get("real_runtime_fallback") or 0),
        "missing_social_turns": [
            {
                "turn_index": row.get("turn_index"),
                "player_action": row.get("player_action"),
            }
            for row in missing_social_turns[:25]
        ],
        "echoed_narration_turns": [
            {
                "turn_index": row.get("turn_index"),
                "player_action": row.get("player_action"),
                "narration": row.get("narration"),
            }
            for row in echoed_narration_turns[:25]
        ],
    }


def compute_runtime_narration_diagnostics(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider_present = 0
    provider_attempted = 0
    provider_valid = 0
    provider_repaired = 0
    fallback_used = 0
    provider_errors = Counter()
    provider_original_errors = Counter()
    provider_repair_actions = Counter()
    provider_shapes = Counter()
    selected_methods = Counter()
    retry_count = 0
    attempt_count = 0
    for row in timeline:
        diag = _safe_dict(row.get("runtime_narration_diagnostics"))
        if not diag:
            continue
        if diag.get("provider_present"):
            provider_present += 1
        if diag.get("provider_attempted"):
            provider_attempted += 1
        if diag.get("provider_valid"):
            provider_valid += 1
        if diag.get("provider_repaired"):
            provider_repaired += 1
        if diag.get("fallback_used"):
            fallback_used += 1
        retry_count += int(diag.get("provider_retry_count") or 0)
        attempt_count += int(diag.get("provider_attempt_count") or 0)
        for err in _safe_list(diag.get("provider_errors")):
            provider_errors[str(err)] += 1
        for err in _safe_list(diag.get("provider_original_errors")):
            provider_original_errors[str(err)] += 1
        for action in _safe_list(diag.get("provider_repair_actions")):
            provider_repair_actions[str(action)] += 1
        shape = _safe_dict(diag.get("provider_shape"))
        if shape:
            provider_shapes[json.dumps(shape, sort_keys=True, default=str)] += 1
        call_diag = _safe_dict(diag.get("provider_call_diagnostics"))
        if call_diag.get("selected_method"):
            selected_methods[str(call_diag.get("selected_method"))] += 1
    return {
        "provider_present_turns": provider_present,
        "provider_attempted_turns": provider_attempted,
        "provider_valid_turns": provider_valid,
        "provider_repaired_turns": provider_repaired,
        "provider_attempt_count": attempt_count,
        "provider_retry_count": retry_count,
        "fallback_used_turns": fallback_used,
        "provider_error_counts": dict(provider_errors),
        "provider_original_error_counts": dict(provider_original_errors),
        "provider_repair_action_counts": dict(provider_repair_actions),
        "provider_shape_counts": dict(provider_shapes),
        "provider_selected_method_counts": dict(selected_methods),
    }


def build_story_so_far_paragraph(model: Dict[str, Any]) -> str:
    timeline = _safe_list(model.get("timeline"))
    milestones = _safe_list(model.get("milestones"))

    completed = [
        row
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    ]
    active = [
        row
        for row in milestones
        if _safe_str(row.get("status")) not in {"completed", "failed", "cancelled"}
    ]
    completed_titles = [
        _safe_str(row.get("title") or row.get("milestone_id"))
        for row in completed
        if _safe_str(row.get("title") or row.get("milestone_id"))
    ]
    active_titles = [
        _safe_str(row.get("title") or row.get("milestone_id"))
        for row in active
        if _safe_str(row.get("title") or row.get("milestone_id"))
    ]

    if not timeline:
        return "No campaign turns have been recorded yet."

    story_beats = []
    for row in timeline:
        for hook in _safe_list(row.get("fired_hooks")):
            hook = _safe_dict(hook)
            summary = _safe_str(hook.get("story_summary"))
            if summary:
                story_beats.append(summary)

    setup = (
        f"Across {len(timeline)} turns, the campaign followed an investigation that began inside "
        "the Rusty Flagon Tavern and gradually widened toward trouble on the road."
    )
    investigation = ""
    if story_beats:
        investigation = " ".join(story_beats[:6])
    else:
        fallback_beats = _safe_list(_safe_dict(model.get("story_beat_summary")).get("beats"))
        if fallback_beats:
            investigation = "Major story beats were reconstructed from turn activity:"
            for beat in fallback_beats[:5]:
                investigation += f"\n- Turn {beat.get('turn_index')}: {beat.get('summary')}"
        else:
            investigation = "The run recorded player activity, but no major story beats were captured."

    outcome_parts = []
    if completed_titles:
        outcome_parts.append("Completed objectives: " + ", ".join(completed_titles) + ".")
    if active_titles:
        outcome_parts.append("Active unresolved objectives: " + ", ".join(active_titles) + ".")
    if not outcome_parts:
        outcome_parts.append("By the end of the run, the campaign had no active objective, so the director should either declare a chapter boundary or seed the next branch.")

    return "\n\n".join([setup, investigation, " ".join(outcome_parts)])


def build_lore_setting_paragraph(state: Dict[str, Any]) -> str:
    director = _safe_dict(state.get("campaign_director_state"))
    lore_rows = _lore_rows(state)
    premise = _safe_str(director.get("premise"))
    dramatic_question = _safe_str(director.get("dramatic_question"))
    opening_tension = _safe_str(director.get("opening_tension"))
    lore_bits = []
    for row in lore_rows[:4]:
        title = _safe_str(row.get("title") or row.get("name"))
        text = _safe_str(row.get("text") or row.get("description") or row.get("summary"))
        if title and text:
            lore_bits.append(f"{title}: {text}")
        elif text:
            lore_bits.append(text)
        elif title:
            lore_bits.append(title)

    parts = []
    if premise:
        parts.append(premise)
    if opening_tension:
        parts.append(opening_tension)
    if dramatic_question:
        parts.append("The director's dramatic question is: " + dramatic_question)
    if lore_bits:
        parts.append("Setting details: " + " ".join(lore_bits))
    if not parts:
        return "No lore or director setup has been captured yet; the campaign seed should define premise, stakes, and setting context."
    return " ".join(parts)


def build_character_progression_paragraph(state: Dict[str, Any]) -> str:
    player = _player_progression(state)
    npc_progression = _safe_dict(_safe_dict(state.get("npc_progression_state")).get("npcs"))
    parts = []
    if player:
        stats = _safe_dict(player.get("stats"))
        stat_text = ""
        if stats:
            stat_text = (
                " Starting stats were "
                + ", ".join(f"{key} {value}" for key, value in sorted(stats.items()))
                + "."
            )
        parts.append(
            f"The player is level {player.get('level', 1)} with "
            f"{player.get('experience', 0)}/{player.get('experience_to_next_level', 100)} XP toward the next level."
            + stat_text
        )
        log = _safe_list(player.get("progression_log"))
        if log:
            readable = []
            for row in log[-5:]:
                row = _safe_dict(row)
                reason = _safe_str(row.get("summary") or row.get("reason"))
                amount = row.get("amount")
                if reason and amount:
                    readable.append(f"{reason} (+{amount} XP)")
                elif reason:
                    readable.append(reason)
            if readable:
                parts.append("Recent player progression: " + "; ".join(readable) + ".")
    else:
        parts.append("No player progression state is currently captured.")

    if npc_progression:
        npc_bits = []
        for npc_name, npc in npc_progression.items():
            npc = _safe_dict(npc)
            latest_log = _safe_list(npc.get("progression_log"))
            latest_summary = ""
            if latest_log:
                latest_summary = _safe_str(_safe_dict(latest_log[-1]).get("summary"))
            npc_bits.append(
                f"{npc_name} is at growth stage {npc.get('growth_stage', 'unknown')} with trust {npc.get('trust', 0)}"
                + (f" ({latest_summary})" if latest_summary else "")
            )
        parts.append("NPC progression: " + "; ".join(npc_bits) + ".")
    else:
        parts.append("No NPC progression state is currently captured.")
    return " ".join(part for part in parts if part.strip())


def build_chapter_status(state: Dict[str, Any], model_like: Dict[str, Any]) -> Dict[str, Any]:
    director = _safe_dict(state.get("campaign_director_state"))
    milestones = _safe_list(model_like.get("milestones"))
    completed = [
        row for row in milestones if _safe_str(row.get("status")) == "completed"
    ]
    active = [
        row
        for row in milestones
        if _safe_str(row.get("status")) not in {"completed", "failed", "cancelled"}
    ]
    arcs = _story_arc_rows(state)
    current_stage = ""
    if arcs:
        current_stage = _safe_str(arcs[0].get("stage"))
    chapter_complete = bool(completed and not active)
    recommendation = ""
    if chapter_complete:
        recommendation = (
            "The current chapter appears complete. The director should either declare a chapter boundary "
            "or seed a follow-up objective so long autoplay runs do not drift."
        )
    elif active:
        recommendation = "The campaign has active objectives and can continue from the current branch."
    else:
        recommendation = "No active objective was found; the director should seed the next actionable goal."
    return {
        "campaign_title": director.get("campaign_title") or "Untitled Campaign",
        "current_stage": current_stage,
        "completed_objective_count": len(completed),
        "active_objective_count": len(active),
        "completed_objectives": [
            row.get("title") or row.get("milestone_id") for row in completed
        ],
        "active_objectives": [
            row.get("title") or row.get("milestone_id") for row in active
        ],
        "chapter_complete": chapter_complete,
        "recommendation": recommendation,
    }


def build_player_progression_rows(state: Dict[str, Any]) -> Dict[str, Any]:
    player = _player_progression(state)
    stats = _safe_dict(player.get("stats"))
    log = _safe_list(player.get("progression_log"))
    return {
        "summary_rows": [
            ("Name", player.get("name") or "The Player"),
            ("Level", player.get("level", 1)),
            ("XP", f"{player.get('experience', 0)} / {player.get('experience_to_next_level', 100)}"),
            ("Progress Log Entries", len(log)),
        ],
        "stats_rows": [(str(k).title(), v) for k, v in sorted(stats.items())],
        "recent_progression_rows": [
            [
                row.get("turn_index", ""),
                row.get("type", ""),
                row.get("amount", ""),
                row.get("reason") or row.get("summary") or "",
                f"{row.get('level_before', '')} → {row.get('level_after', '')}" if row.get("level_after") is not None else "",
            ]
            for row in log[-8:]
            if isinstance(row, dict)
        ],
    }


def build_story_arc_report_rows(model: Dict[str, Any]) -> Dict[str, Any]:
    arcs = _safe_list(model.get("story_arcs"))
    milestones = _safe_list(model.get("milestones"))
    by_arc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for milestone in milestones:
        milestone = _safe_dict(milestone)
        by_arc[_safe_str(milestone.get("arc_id"))].append(milestone)
    rows = []
    for arc in arcs:
        arc = _safe_dict(arc)
        arc_id = _safe_str(arc.get("arc_id"))
        arc_milestones = by_arc.get(arc_id, [])
        completed = [m for m in arc_milestones if _safe_str(m.get("status")) == "completed"]
        active = [m for m in arc_milestones if _safe_str(m.get("status")) not in {"completed", "failed", "cancelled"}]
        rows.append(
            {
                "arc_id": arc_id,
                "title": arc.get("title") or arc_id,
                "stage": arc.get("stage"),
                "status": arc.get("status"),
                "pressure": arc.get("pressure", 0),
                "completed_count": len(completed),
                "active_count": len(active),
                "milestones": arc_milestones,
            }
        )
    return {
        "arcs": rows,
        "total_arcs": len(rows),
        "total_milestones": len(milestones),
    }


def build_inventory_rows(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    currency = _safe_dict(snapshot.get("currency"))
    items = _safe_list(snapshot.get("items"))
    return {
        "currency_rows": [[k, v] for k, v in sorted(currency.items())],
        "item_rows": [
            [
                _safe_dict(item).get("name") or _safe_dict(item).get("item_id") or "",
                _safe_dict(item).get("quantity", 1),
                _safe_dict(item).get("type", ""),
                _safe_dict(item).get("description", ""),
            ]
            for item in items
            if isinstance(item, dict)
        ],
    }


def build_location_journey_model(
    *,
    timeline: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    director = _safe_dict(state.get("campaign_director_state"))
    location_rows: Dict[str, Dict[str, Any]] = {}

    def ensure_location(name: str) -> Dict[str, Any]:
        key = name or "Unknown Location"
        location_rows.setdefault(
            key,
            {
                "name": key,
                "turns": [],
                "summary_bits": [],
                "npcs": set(),
                "objectives": set(),
                "events": [],
            },
        )
        return location_rows[key]

    # Seed known setting locations from lore/director.
    ensure_location("The Rusty Flagon Tavern")["summary_bits"].append(
        "The social hub where the witness investigation begins."
    )
    ensure_location("The Bandit Road")["summary_bits"].append(
        "The external danger path revealed after the witness report."
    )

    for row in timeline:
        action = _norm_text(row.get("player_action"))
        if "road" in action or "bandit" in action or "outside" in action:
            loc = ensure_location("The Bandit Road")
        else:
            loc = ensure_location("The Rusty Flagon Tavern")
        loc["turns"].append(row.get("turn_index"))
        narration = _safe_str(row.get("narration"))
        if narration:
            loc["summary_bits"].append(narration)
        npc = _safe_dict(row.get("npc"))
        if npc.get("speaker"):
            loc["npcs"].add(str(npc.get("speaker")))
        for hook in _safe_list(row.get("fired_hooks")):
            hook = _safe_dict(hook)
            if hook.get("story_label"):
                loc["events"].append(hook.get("story_label"))

    for milestone in _milestone_rows(state):
        title = _safe_str(milestone.get("title") or milestone.get("milestone_id"))
        if not title:
            continue
        text = _norm_text(title + " " + _safe_str(milestone.get("objective_text")))
        if "road" in text or "bandit" in text:
            ensure_location("The Bandit Road")["objectives"].add(title)
        else:
            ensure_location("The Rusty Flagon Tavern")["objectives"].add(title)

    locations = []
    for loc in location_rows.values():
        bits = []
        seen_bits = set()
        for bit in loc["summary_bits"]:
            bit = _safe_str(bit)
            if not bit or bit in seen_bits:
                continue
            seen_bits.add(bit)
            bits.append(bit)
            if len(bits) >= 4:
                break
        locations.append(
            {
                "name": loc["name"],
                "turn_range": (
                    f"{min(loc['turns'])}–{max(loc['turns'])}" if loc["turns"] else "setup"
                ),
                "turn_count": len(loc["turns"]),
                "summary": " ".join(bits) if bits else "No summary captured.",
                "npcs": sorted(loc["npcs"]),
                "objectives": sorted(loc["objectives"]),
                "events": loc["events"][:8],
            }
        )
    return {
        "locations": locations,
        "director_context": {
            "premise": director.get("premise"),
            "stakes": director.get("stakes"),
        },
    }


def extract_turn_ai_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort extraction of the raw/structured narration payload.

    This intentionally reads many shapes because narration output has evolved
    across bundles.
    """
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    result = _safe_dict(turn_result.get("result"))

    candidates = [
        raw_result.get("narration_result"),
        raw_result.get("narration_payload"),
        raw_result.get("narration_json"),
        raw_result.get("structured_narration"),
        raw_result.get("llm_narration"),
        _nested_get(raw_result, "result", "narration_result"),
        _nested_get(raw_result, "result", "narration_payload"),
        _nested_get(raw_result, "session", "runtime_state", "last_narration_payload"),
        _nested_get(raw_result, "session", "runtime_state", "last_structured_narration"),
        manual_summary.get("raw_narration_payload"),
        result.get("narration_payload"),
        _nested_get(turn_result, "deferred_narration_result", "narration_payload"),
        _nested_get(turn_result, "combined_background_llm_result", "narration_payload"),
        row.get("deferred_narration_result", {}).get("narration_payload") if isinstance(row.get("deferred_narration_result"), dict) else {},
        row.get("combined_background_llm_result", {}).get("narration_payload") if isinstance(row.get("combined_background_llm_result"), dict) else {},
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def extract_story_hook_display(row: Dict[str, Any]) -> Dict[str, Any]:
    hook_result = _safe_dict(row.get("story_hook_result"))
    display = _safe_dict(hook_result.get("display"))
    if display:
        return display
    fired_hooks = _safe_list(hook_result.get("fired_hooks"))
    for fired in reversed(fired_hooks):
        display = _safe_dict(_safe_dict(fired).get("display"))
        if display:
            return display
    return {}


def extract_base_response_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(row.get("base_response_payload"))
    if payload:
        return payload
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    payload = _safe_dict(manual_summary.get("base_response_payload"))
    if payload:
        return payload
    return {}


def extract_conversation_beat(row: Dict[str, Any]) -> Dict[str, str]:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    conversation_result = _safe_dict(
        raw_result.get("conversation_result")
        or _nested_get(raw_result, "result", "conversation_result")
    )
    beat = _safe_dict(conversation_result.get("beat"))
    if beat:
        return {
            "speaker": _first_nonempty(beat.get("speaker_name"), beat.get("speaker_id")),
            "line": _safe_str(beat.get("line")),
        }
    beats = _safe_list(conversation_result.get("beats"))
    for item in beats:
        beat = _safe_dict(item)
        if beat.get("line"):
            return {
                "speaker": _first_nonempty(beat.get("speaker_name"), beat.get("speaker_id")),
                "line": _safe_str(beat.get("line")),
            }
    return {}


def classify_dialogue_source(row: Dict[str, Any]) -> str:
    """Classify where the visible NPC dialogue came from."""
    ai_payload = extract_turn_ai_payload(row)
    if _safe_dict(ai_payload.get("npc")).get("line") and _safe_str(ai_payload.get("source")) == "provider_runtime_narration":
        return "real_runtime_provider"

    hook_display = extract_story_hook_display(row)
    if _safe_dict(hook_display.get("npc")).get("line"):
        return "story_hook_display"

    if _safe_dict(ai_payload.get("npc")).get("line"):
        if _safe_str(ai_payload.get("source")) == "deterministic_runtime_narration_fallback":
            return "real_runtime_fallback"
        return "raw_ai_payload"

    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    if _safe_dict(manual_summary.get("raw_npc")).get("line"):
        return "raw_npc"

    if extract_conversation_beat(row).get("line"):
        return "conversation_beat"

    base_response = extract_base_response_payload(row)
    if _safe_dict(base_response.get("npc")).get("line"):
        source = _safe_str(base_response.get("source"))
        if source == "provider_base_runtime_response":
            return "base_runtime_provider"
        return "base_runtime_deterministic"

    return "none"


def extract_dialogue(row: Dict[str, Any]) -> Dict[str, str]:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    ai_payload = extract_turn_ai_payload(row)
    hook_display = extract_story_hook_display(row)
    base_response = extract_base_response_payload(row)
    npc_payload = _safe_dict(ai_payload.get("npc"))
    hook_npc = _safe_dict(hook_display.get("npc"))
    base_npc = _safe_dict(base_response.get("npc"))
    raw_npc = _safe_dict(manual_summary.get("raw_npc"))
    conversation_beat = extract_conversation_beat(row)

    speaker = _first_nonempty(
        npc_payload.get("speaker") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_npc.get("speaker"),
        npc_payload.get("speaker"),
        base_npc.get("speaker"),
        raw_npc.get("speaker"),
        conversation_beat.get("speaker"),
        raw_result.get("npc_speaker"),
        _nested_get(raw_result, "npc", "speaker"),
        _nested_get(raw_result, "result", "npc", "speaker"),
        _nested_get(raw_result, "turn_contract", "npc", "speaker"),
        _nested_get(turn_result, "turn_contract", "npc", "speaker"),
    )
    line = _first_nonempty(
        npc_payload.get("line") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_npc.get("line"),
        npc_payload.get("line"),
        base_npc.get("line"),
        raw_npc.get("line"),
        conversation_beat.get("line"),
        raw_result.get("npc_line"),
        _nested_get(raw_result, "npc", "line"),
        _nested_get(raw_result, "result", "npc", "line"),
        _nested_get(raw_result, "turn_contract", "npc", "line"),
        _nested_get(turn_result, "turn_contract", "npc", "line"),
    )
    return {
        "speaker": speaker,
        "line": line,
    }


def extract_narration(row: Dict[str, Any]) -> str:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    ai_payload = extract_turn_ai_payload(row)
    hook_display = extract_story_hook_display(row)
    base_response = extract_base_response_payload(row)
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    return _first_nonempty(
        ai_payload.get("narration") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_display.get("narration"),
        ai_payload.get("narration"),
        base_response.get("narration"),
        turn_result.get("narration"),
        manual_summary.get("raw_narration"),
        raw_result.get("narration"),
        _nested_get(raw_result, "result", "narration"),
    )


def is_social_player_action(player_action: Any) -> bool:
    text = _norm_text(player_action)
    return any(word in text for word in SOCIAL_ACTION_WORDS)


def is_echoed_narration(*, player_action: Any, narration: Any) -> bool:
    player = _norm_text(player_action)
    narr = _norm_text(narration)
    if not player or not narr:
        return False
    return player == narr or narr in {player.rstrip("."), player + "."}


def build_campaign_report_model(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
) -> Dict[str, Any]:
    latest_state = _safe_dict(summary.get("latest_state") or metrics.get("latest_state"))
    latest_state_source = "summary.latest_state" if latest_state else ""
    if not latest_state:
        latest_state = _latest_state_from_transcript(transcript)
        latest_state_source = _latest_state_source(transcript)
    initial_state = _initial_state_from_transcript(transcript)
    quality = _safe_dict(metrics.get("progress_quality"))
    turn_count_for_rates = max(1, len(transcript))
    quality.setdefault("weak_progress_rate", float(quality.get("weak_progress_turns") or 0) / turn_count_for_rates)
    quality.setdefault("no_change_rate", float(quality.get("no_change_turns") or 0) / turn_count_for_rates)
    quality.setdefault("churn_only_rate", float(quality.get("churn_only_turns") or 0) / turn_count_for_rates)
    action_diversity = _safe_dict(metrics.get("action_diversity"))
    category_counts = Counter()
    hook_counts = Counter()
    npc_dialogue_counts = Counter()

    timeline = []
    for row in transcript:
        dialogue = extract_dialogue(row)
        narration = extract_narration(row)
        dialogue_source = classify_dialogue_source(row)
        player_action = _safe_str(row.get("player_action"))
        social_action = is_social_player_action(player_action)
        missing_npc_response = bool(social_action and not dialogue.get("line"))
        echoed_narration = is_echoed_narration(
            player_action=player_action,
            narration=narration,
        )
        progress_delta = _safe_dict(row.get("progress_delta"))
        progress_quality = _safe_dict(row.get("progress_quality"))
        hook_result = _safe_dict(row.get("story_hook_result"))
        fired_hooks = _safe_list(hook_result.get("fired_hooks"))
        for category in _safe_list(progress_delta.get("categories")):
            category_counts[str(category)] += 1
        for hook in fired_hooks:
            hook = _safe_dict(hook)
            if hook.get("hook_id"):
                hook_counts[str(hook.get("hook_id"))] += 1
        if dialogue.get("speaker"):
            npc_dialogue_counts[dialogue["speaker"]] += 1
        timeline.append(
            {
                "turn_index": row.get("turn_index"),
                "player_action": player_action,
                "narration": narration,
                "npc": dialogue,
                "dialogue_source": dialogue_source,
                "social_action": social_action,
                "missing_npc_response": missing_npc_response,
                "echoed_narration": echoed_narration,
                "progress_delta": progress_delta,
                "progress_quality": progress_quality,
                "fired_hooks": fired_hooks,
                "state_preservation_debug": row.get("state_preservation_debug") or {},
                "performance": row.get("performance") or {},
                "base_response_payload": row.get("base_response_payload") or {},
                "runtime_narration_diagnostics": _safe_dict(
                    _safe_dict(extract_turn_ai_payload(row)).get("runtime_narration_diagnostics")
                ),
            }
        )

    dialogue_coverage = compute_dialogue_coverage(timeline)
    runtime_narration_diagnostics = compute_runtime_narration_diagnostics(timeline)

    shortcomings = []
    if float(quality.get("meaningful_progress_rate") or 0.0) < 0.15 and transcript:
        shortcomings.append("Low meaningful progress rate; story may be stalling or progression hooks may be too sparse.")
    if int(quality.get("weak_progress_turns") or 0) > int(quality.get("meaningful_turns") or 0):
        shortcomings.append("Weak/journal-only progress exceeds meaningful progress; journal churn may be too generous.")
    if int(metrics.get("checkpoint_failure_count") or 0) > 0:
        shortcomings.append("One or more save/load checkpoints failed.")
    if int(metrics.get("state_bound_warning_count") or 0) > 0:
        shortcomings.append("State bounds warnings occurred; long-run state may be growing unsafely.")
    if not hook_counts:
        shortcomings.append("No story hooks fired; deterministic story progression may be missing.")
    if not npc_dialogue_counts:
        shortcomings.append("No NPC dialogue extracted; narration payload may not expose speaker/line fields.")
    if int(dialogue_coverage.get("social_turn_missing_npc_response_count") or 0) > 0:
        shortcomings.append(
            f"{dialogue_coverage.get('social_turn_missing_npc_response_count')} social turns had no extracted NPC response; "
            "base-runtime dialogue coverage is incomplete."
        )
    if int(dialogue_coverage.get("echoed_narration_turn_count") or 0) > 0:
        shortcomings.append(
            f"{dialogue_coverage.get('echoed_narration_turn_count')} turns appear to echo the player action as narration; "
            "the narration runtime may be falling back instead of generating scene response text."
        )
    source_counts = _safe_dict(dialogue_coverage.get("dialogue_source_counts"))
    deterministic_count = int(source_counts.get("base_runtime_deterministic") or 0)
    provider_count = int(source_counts.get("base_runtime_provider") or 0)
    if deterministic_count > 0 and provider_count == 0:
        shortcomings.append(
            "Some non-hook dialogue is supplied by fallback narration rather than valid provider narration; provider-backed runtime narration should be validated next."
        )
    if int(runtime_narration_diagnostics.get("provider_valid_turns") or 0) == 0:
        shortcomings.append(
            "Real runtime narration used deterministic fallback for all turns; provider-backed runtime narration is not active or not producing valid contract JSON."
        )
    elif int(runtime_narration_diagnostics.get("provider_repaired_turns") or 0) > 0:
        shortcomings.append(
            f"Provider runtime narration required contract repair on {runtime_narration_diagnostics.get('provider_repaired_turns')} turns; "
            "provider prompt/quality gates should be tightened."
        )
    if int(metrics.get("player_agent_exception_count") or 0) > 0:
        shortcomings.append(
            f"Player-agent exceptions occurred on {metrics.get('player_agent_exception_count')} turns; "
            "this run may reflect fallback action logic rather than real LLM player behavior."
        )
    if float(metrics.get("fallback_player_action_rate") or 0.0) >= 0.5:
        shortcomings.append(
            f"Fallback player action rate was {metrics.get('fallback_player_action_rate')}; "
            "storytelling evaluation should be treated cautiously until the LLM player-agent path is fixed."
        )

    model = {
        "summary": summary,
        "metrics": metrics,
        "health": health,
        "latest_state": latest_state,
        "latest_state_source": latest_state_source,
        "initial_state": initial_state,
        "inventory_start": _inventory_snapshot(initial_state),
        "inventory_end": _inventory_snapshot(latest_state),
        "timeline": timeline,
        "story_arcs": _story_arc_rows(latest_state),
        "milestones": _milestone_rows(latest_state),
        "journal_entries": _journal_entries(latest_state),
        "story_events": _story_events(latest_state),
        "npcs": _npc_rows(latest_state, transcript),
        "player_progression": _player_progression(latest_state),
        "lore": _lore_rows(latest_state),
        "category_counts": dict(category_counts),
        "hook_counts": dict(hook_counts),
        "npc_dialogue_counts": dict(npc_dialogue_counts),
        "action_diversity": action_diversity,
        "dialogue_coverage": dialogue_coverage,
        "runtime_narration_diagnostics": runtime_narration_diagnostics,
        "background_jobs": _safe_dict(metrics.get("background_jobs")),
        "provider_trace_summary": _safe_dict(metrics.get("provider_trace_summary")),
        "manual_harness_trace_summary": _safe_dict(metrics.get("manual_harness_trace_summary")),
        "turn_perf_trace_summary": _safe_dict(metrics.get("turn_perf_trace_summary")),
        "player_agent_trace_summary": _safe_dict(metrics.get("player_agent_trace_summary")),
        "deferred_narration_trace_summary": _safe_dict(metrics.get("deferred_narration_trace_summary")),
        "deferred_advisory_trace_summary": _safe_dict(metrics.get("deferred_advisory_trace_summary")),
        "performance_budget_summary": _safe_dict(metrics.get("performance_budget_summary")),
        "background_prompt_budget_summary": _safe_dict(metrics.get("background_prompt_budget_summary")),
        "combined_quality_shape_summary": _safe_dict(metrics.get("combined_quality_shape_summary")),
        "player_agent_prompt_budget_summary": _safe_dict(summary.get("player_agent_prompt_budget_summary")),
        "player_agent_cache_summary": _safe_dict(summary.get("player_agent_cache_summary")),
        "deferred_advisory_promotion_summary": _safe_dict(
            summary.get("deferred_advisory_promotion_summary")
            or metrics.get("deferred_advisory_promotion_summary")
        ),
        "npc_evolution_summary": _safe_dict(summary.get("npc_evolution_summary") or metrics.get("npc_evolution_summary")),
        "npc_evolution_profile_persistence_summary": _safe_dict(
            summary.get("npc_evolution_profile_persistence_summary")
            or metrics.get("npc_evolution_profile_persistence_summary")
        ),
        "npc_profile_load_summary": _safe_dict(
            summary.get("npc_profile_load_summary")
            or metrics.get("npc_profile_load_summary")
        ),
        "profile_grounded_output_summary": _safe_dict(
            summary.get("profile_grounded_output_summary")
            or metrics.get("profile_grounded_output_summary")
        ),
        "npc_arc_progression_summary": _safe_dict(
            summary.get("npc_arc_progression_summary")
            or metrics.get("npc_arc_progression_summary")
        ),
        "npc_evolution_report_summary": _safe_dict(
            summary.get("npc_evolution_report_summary")
            or metrics.get("npc_evolution_report_summary")
        ),
        "quest_progress_summary": _safe_dict(
            summary.get("quest_progress_summary")
            or metrics.get("quest_progress_summary")
        ),
        "quest_reconciliation_summary": _safe_dict(summary.get("quest_reconciliation_summary")),
        "quest_handoff_summary": _safe_dict(summary.get("quest_handoff_summary")),
        "objective_progression_summary": _safe_dict(summary.get("objective_progression_summary")),
        "final_state_field_coverage_summary": _safe_dict(summary.get("final_state_field_coverage_summary")),
        "strict_progress_health_summary": _safe_dict(summary.get("strict_progress_health_summary")),
        "post_transition_action_quality_summary": _safe_dict(summary.get("post_transition_action_quality_summary")),
        "repeated_affordance_loop_summary": _safe_dict(summary.get("repeated_affordance_loop_summary")),
        "pre_turn_advisory_promotion_performance_summary": _safe_dict(
            summary.get("pre_turn_advisory_promotion_performance_summary")
        ),
        "campaign_state_commit_summary": _safe_dict(summary.get("campaign_state_commit_summary")),
        "campaign_stale_state_summary": _safe_dict(summary.get("campaign_stale_state_summary")),
        "campaign_state_commit_performance_summary": _safe_dict(
            summary.get("campaign_state_commit_performance_summary")
        ),
        "handoff_progress_summary": _safe_dict(summary.get("handoff_progress_summary")),
        "scenario_progression_summary": _safe_dict(summary.get("scenario_progression_summary")),
        "behavioral_autoplay_eval_summary": _safe_dict(summary.get("behavioral_autoplay_eval_summary")),
        "story_beat_summary": _safe_dict(
            summary.get("story_beat_summary")
            or metrics.get("story_beat_summary")
        ),
        "manual_turn_error_summary": _safe_dict(
            summary.get("manual_turn_error_summary")
            or metrics.get("manual_turn_error_summary")
        ),
        "console_log_summary": _safe_dict(
            summary.get("console_log_summary")
            or metrics.get("console_log_summary")
        ),
        "action_diversity_summary": _safe_dict(
            summary.get("action_diversity_summary")
            or metrics.get("action_diversity_summary")
        ),
        "progress_timeline_summary": _safe_dict(
            summary.get("progress_timeline_summary")
            or metrics.get("progress_timeline_summary")
        ),
        "long_run_warning_summary": _safe_dict(
            summary.get("long_run_warning_summary")
            or metrics.get("long_run_warning_summary")
        ),
        "hundred_turn_eval_summary": _safe_dict(
            summary.get("hundred_turn_eval_summary")
            or metrics.get("hundred_turn_eval_summary")
        ),
        "background_result_timing_summary": _safe_dict(
            summary.get("background_result_timing_summary")
            or metrics.get("background_result_timing_summary")
        ),
        "background_drain_events": (
            summary.get("background_drain_events")
            or metrics.get("background_drain_events")
            or []
        ),
        "campaign_calendar_summary": _safe_dict(
            summary.get("campaign_calendar_summary")
            or metrics.get("campaign_calendar_summary")
        ),
        "player_journal_summary": _safe_dict(
            summary.get("player_journal_summary")
            or metrics.get("player_journal_summary")
        ),
        "player_journal_quality_summary": _safe_dict(
            summary.get("player_journal_quality_summary")
            or metrics.get("player_journal_quality_summary")
        ),
        "promotion_target_grounding_summary": _safe_dict(
            summary.get("promotion_target_grounding_summary")
            or metrics.get("promotion_target_grounding_summary")
        ),
        "quality_gate_summary": _safe_dict(summary.get("quality_gate_summary")),
        "shortcomings": shortcomings,
    }
    model["story_so_far_paragraph"] = build_story_so_far_paragraph(model)
    model["lore_setting_paragraph"] = build_lore_setting_paragraph(latest_state)
    model["character_progression_paragraph"] = build_character_progression_paragraph(latest_state)
    model["chapter_status"] = build_chapter_status(latest_state, model)
    model["player_progression_view"] = build_player_progression_rows(latest_state)
    model["story_arc_view"] = build_story_arc_report_rows(model)
    model["inventory_start_view"] = build_inventory_rows(_safe_dict(model["inventory_start"]))
    model["inventory_end_view"] = build_inventory_rows(_safe_dict(model["inventory_end"]))
    model["location_journey"] = build_location_journey_model(
        timeline=timeline,
        state=latest_state,
    )
    model["pm_summary"] = build_pm_report_summary(model)
    return model


def render_campaign_report_html(
    model: Optional[Dict[str, Any]] = None,
    *,
    summary: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
    report_model: Optional[Dict[str, Any]] = None,
) -> str:
    # Handle backward compatibility: if called with single model parameter
    if model is not None and summary is None and metrics is None and transcript is None:
        summary = _safe_dict(model.get("summary"))
        metrics = _safe_dict(model.get("metrics"))
        transcript = _as_list(model.get("transcript"))
        # report_model is the same as model for backward compatibility
        if report_model is None:
            report_model = model

    report_context = _merge_report_contexts(
        summary=summary,
        metrics=metrics,
        report_model=report_model,
    )
    summary = report_context
    metrics = report_context
    # Reconstruct model dict for backward compatibility
    model = {
        "summary": summary,
        "metrics": metrics,
        "transcript": transcript,
        "timeline": _as_list(report_context.get("timeline")),
        **report_context,  # Include all merged context
    }
    health = _safe_dict(model.get("health"))
    progress_quality = _safe_dict(metrics.get("progress_quality"))
    performance = _safe_dict(metrics.get("performance"))
    story_variety = _safe_dict(metrics.get("story_variety"))
    latest_state = _safe_dict(model.get("latest_state"))
    chapter_status = _safe_dict(model.get("chapter_status"))
    pm_summary = _safe_dict(model.get("pm_summary"))
    pm_status = _status_class(pm_summary.get("overall_status"))
    chronicle_model = _build_campaign_chronicle_model(report_context, report_context)

    timeline_html = []
    for row in _as_list(report_context.get("timeline")):
        npc = _safe_dict(row.get("npc"))
        fired_hooks = _safe_list(row.get("fired_hooks"))
        hook_badges = " ".join(_render_badge(_safe_dict(h).get("hook_id"), "hook") for h in fired_hooks)
        categories = " ".join(
            _render_badge(category, "category")
            for category in _safe_list(_safe_dict(row.get("progress_delta")).get("categories"))
        )
        quality = _safe_str(_safe_dict(row.get("progress_quality")).get("quality"))
        timeline_html.append(
            f"""
            <article class="turn-card">
               <div class="turn-header">
                 <h3>Turn {_esc(row.get("turn_index"))}</h3>
                 <div>
                   {_render_badge(quality or "unknown", "quality")}
                   {_render_badge(str(_safe_dict(row.get("performance")).get("turn_total_ms", "")) + " ms", "category")}
                 </div>
               </div>
              <div class="player-action"><strong>Player:</strong> {_esc(row.get("player_action"))}</div>
              <div class="narration"><strong>Narration:</strong> {_esc(row.get("narration") or "[no narration extracted]")}</div>
              <div class="npc-line"><strong>NPC:</strong> {_esc(npc.get("speaker") or "[none]")} — {_esc(npc.get("line") or "[no NPC line extracted]")}</div>
              <div class="badges">
                {_render_badge("dialogue:" + _safe_str(row.get("dialogue_source") or "none"), "category")}
                {categories} {hook_badges}
                {_render_badge("missing_npc_response", "quality") if row.get("missing_npc_response") else ""}
                {_render_badge("echoed_narration", "quality") if row.get("echoed_narration") else ""}
              </div>
              <details>
                <summary>Turn debug</summary>
                <pre>{_json(row)}</pre>
              </details>
            </article>
            """
        )

    npc_rows = [
        [
            row.get("name") or row.get("npc_id"),
            row.get("role") or row.get("occupation"),
            row.get("dialogue_turns", 0),
            row.get("history") or row.get("backstory") or "",
            row.get("biography") or row.get("bio") or "",
            row.get("growth") or row.get("arc") or "",
        ]
        for row in _safe_list(model.get("npcs"))
    ]

    css = """
   :root {
      --bg: #0b1020;
      --panel: #ffffff;
      --panel2: #f6f8fc;
      --ink: #172033;
      --text: #172033;
      --muted: #64748b;
      --accent: #315efb;
      --accent2: #7c3aed;
      --good: #12805c;
      --warn: #b7791f;
      --bad: #c2410c;
      --border: #d9e1f2;
      --shadow: 0 20px 60px rgba(15, 23, 42, 0.12);
      --rpg-bg: #15110d;
      --rpg-panel: #211a14;
      --rpg-panel-2: #2a2119;
      --rpg-parchment: #f1e3c8;
      --rpg-parchment-2: #e6d0aa;
      --rpg-ink: #24170d;
      --rpg-muted: #7d6b55;
      --rpg-gold: #c79a3b;
      --rpg-gold-2: #e2bf6d;
      --rpg-red: #a64235;
      --rpg-green: #4d8a54;
      --rpg-blue: #4b6f8f;
      --rpg-shadow: rgba(0, 0, 0, 0.35);
    }
   body {
     margin: 0;
     font-family: Inter, Segoe UI, Arial, sans-serif;
     background: linear-gradient(135deg, #edf3ff 0%, #f8fafc 45%, #f5f3ff 100%);
     color: var(--text);
     line-height: 1.5;
   }
   header {
     padding: 34px 42px;
     border-bottom: 1px solid var(--border);
     background: rgba(255,255,255,0.88);
     position: sticky;
     top: 0;
     z-index: 3;
     backdrop-filter: blur(16px);
     box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
   }
   h1, h2, h3 { margin: 0 0 12px; }
   h1 { font-size: 30px; letter-spacing: -0.03em; }
   h2 { font-size: 22px; letter-spacing: -0.02em; }
   h3 { font-size: 16px; color: var(--ink); }
   main { padding: 30px; max-width: 1500px; margin: 0 auto; }
   section {
     background: rgba(255,255,255,0.94);
     border: 1px solid var(--border);
     border-radius: 24px;
     padding: 24px;
     margin-bottom: 24px;
     box-shadow: var(--shadow);
   }
   .grid {
     display: grid;
     grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
     gap: 16px;
   }
   .metric {
     background: var(--panel2);
     border: 1px solid var(--border);
     border-radius: 18px;
     padding: 16px;
   }
    .metric .value { font-size: 28px; font-weight: 850; color: var(--accent); letter-spacing: -0.03em; }
    .bar-row {
      display: grid;
      grid-template-columns: 220px minmax(160px, 1fr) 90px;
      gap: 12px;
      align-items: center;
      margin: 10px 0;
    }
    .bar-label { font-weight: 700; color: #334155; }
    .bar-track {
      height: 12px;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #dbe3ef;
    }
    .bar-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      border-radius: 999px;
    }
    .bar-value { color: var(--muted); font-variant-numeric: tabular-nums; text-align: right; }
    .section-lede {
      color: var(--muted);
      font-size: 15px;
      max-width: 980px;
      margin-top: -4px;
    }
    .card-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .story-card {
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
    }
    .story-card h3 { margin-bottom: 6px; }
    .kv-table th { width: 220px; }
    .muted { color: var(--muted); }
    .small { font-size: 0.85rem; }
   .good { color: var(--good); }
   .warn { color: var(--warn); }
   .bad { color: var(--bad); }
   .hero {
     background: linear-gradient(135deg, #1d4ed8, #7c3aed);
     color: white;
     border: 0;
   }
   .hero .muted { color: rgba(255,255,255,0.78); }
   .hero .metric { background: rgba(255,255,255,0.14); border-color: rgba(255,255,255,0.22); color: white; }
   .hero .metric .value { color: white; }
   .status-pill {
     display: inline-block;
     padding: 6px 11px;
     border-radius: 999px;
     font-weight: 700;
     font-size: 12px;
     background: #e0e7ff;
     color: #3730a3;
     margin-left: 6px;
   }
   .status-pill.good { background: #dcfce7; color: #166534; }
   .status-pill.warn { background: #fef3c7; color: #92400e; }
   .status-pill.bad { background: #fee2e2; color: #991b1b; }
   table {
     width: 100%;
     border-collapse: collapse;
     overflow: hidden;
     border-radius: 14px;
   }
   th, td {
     border-bottom: 1px solid var(--border);
     padding: 10px 12px;
     text-align: left;
     vertical-align: top;
   }
    th { color: #334155; background: #eef2ff; }
    tr:nth-child(even) td { background: #f8fafc; }
    .npc-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .npc-card, .journal-entry { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin: 8px 0; background: #fafafa; }
    .npc-card h3 { margin-top: 0; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 10px 0; }
    .metric-card { border: 1px solid #ddd; border-radius: 8px; padding: 10px; background: #fafafa; }
    .report-quick-links {
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 12px;
      margin: 16px 0;
      background: #f8fafc;
    }
    .report-quick-links nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .report-quick-links a {
      display: inline-block;
      padding: 6px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      background: white;
      text-decoration: none;
    }
    #campaign-journal, #quest-progress, #npc-evolution {
      scroll-margin-top: 20px;
    }
    .header-journal-link {
      font-weight: 700;
    }
    .turn-card {
     background: var(--panel2);
     border: 1px solid var(--border);
     border-radius: 18px;
     padding: 16px;
     margin-bottom: 14px;
   }
   .turn-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
   .player-action, .narration, .npc-line { margin: 10px 0; }
   .badge {
     display: inline-block;
     padding: 4px 9px;
     border-radius: 999px;
     background: #e2e8f0;
     color: #334155;
     font-size: 12px;
     margin: 2px;
     border: 1px solid var(--border);
   }
   .badge.hook { background: #dcfce7; color: #166534; }
   .badge.category { background: #dbeafe; color: #1d4ed8; }
   .badge.quality { background: #fef3c7; color: #92400e; }
   pre {
     white-space: pre-wrap;
     overflow-x: auto;
     background: #0f172a;
     border: 1px solid var(--border);
     border-radius: 14px;
     padding: 12px;
     color: #d7ddff;
   }
   details { margin-top: 10px; }
   summary { cursor: pointer; color: var(--accent); font-weight: 700; }
   nav a { color: var(--accent); margin-right: 16px; text-decoration: none; }
   .tech-details {
     background: #f8fafc;
     border: 1px solid var(--border);
     border-radius: 16px;
     padding: 12px 14px;
     margin-top: 12px;
   }
   .two-col {
     display: grid;
     grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
     gap: 18px;
   }
    @media (max-width: 900px) {
      .two-col { grid-template-columns: 1fr; }
      header { position: static; }
    }

      body {
        margin: 0;
        background:
          radial-gradient(circle at top left, rgba(199, 154, 59, 0.16), transparent 28rem),
          linear-gradient(180deg, #120d09 0%, #1c150f 45%, #100c09 100%);
        color: var(--rpg-parchment);
        font-family: Georgia, "Times New Roman", serif;
      }

      .rpg-shell {
        max-width: 1480px;
        margin: 0 auto;
        padding: 28px;
      }

      .rpg-hero {
        border: 1px solid rgba(226, 191, 109, 0.55);
        background:
          linear-gradient(135deg, rgba(33, 26, 20, 0.96), rgba(42, 33, 25, 0.9)),
          radial-gradient(circle at 80% 10%, rgba(199, 154, 59, 0.18), transparent 24rem);
        box-shadow: 0 18px 50px var(--rpg-shadow);
        border-radius: 22px;
        padding: 30px;
        position: relative;
        overflow: hidden;
      }

      .rpg-hero::after {
        content: "";
        position: absolute;
        inset: 12px;
        border: 1px solid rgba(226, 191, 109, 0.22);
        border-radius: 16px;
        pointer-events: none;
      }

      .rpg-kicker {
        color: var(--rpg-gold-2);
        letter-spacing: 0.16em;
        text-transform: uppercase;
        font-size: 0.78rem;
        margin-bottom: 8px;
      }

      .rpg-title {
        margin: 0;
        font-size: clamp(2.2rem, 4vw, 4.2rem);
        line-height: 0.95;
        color: #fff6df;
        text-shadow: 0 2px 0 rgba(0,0,0,0.5);
      }

      .rpg-subtitle {
        margin-top: 12px;
        color: var(--rpg-parchment-2);
        font-size: 1.05rem;
        max-width: 900px;
      }

      .rpg-hero-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 20px;
      }

      .rpg-hero-report {
        position: relative;
        z-index: 1;
        margin-top: 24px;
        padding: 18px;
        border: 1px solid rgba(226, 191, 109, 0.28);
        border-radius: 18px;
        background:
          linear-gradient(180deg, rgba(0, 0, 0, 0.22), rgba(0, 0, 0, 0.10)),
          rgba(255, 255, 255, 0.035);
      }

      .rpg-hero-report-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 14px;
      }

      .rpg-hero-report-header h2 {
        margin: 0;
        color: #fff6df;
        font-size: 1.55rem;
      }

      .rpg-hero-stat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
        gap: 10px;
      }

      .rpg-hero-stat {
        border: 1px solid rgba(226, 191, 109, 0.18);
        background: rgba(0, 0, 0, 0.22);
        border-radius: 14px;
        padding: 12px;
      }

      .rpg-hero-stat .rpg-stat-label {
        color: rgba(241, 227, 200, 0.72);
      }

      .rpg-hero-stat .rpg-stat-value {
        color: #fff6df;
      }

      .rpg-hero-stat .rpg-muted-line {
        color: rgba(241, 227, 200, 0.72);
      }

      .rpg-pill {
        border: 1px solid rgba(226, 191, 109, 0.35);
        background: rgba(0,0,0,0.22);
        color: #fff1d0;
        padding: 8px 12px;
        border-radius: 999px;
        font-size: 0.9rem;
      }

      .rpg-nav {
        position: sticky;
        top: 0;
        z-index: 50;
        margin: 18px 0 24px;
        padding: 10px;
        border: 1px solid rgba(226, 191, 109, 0.22);
        border-radius: 16px;
        background: rgba(21, 17, 13, 0.92);
        backdrop-filter: blur(8px);
        box-shadow: 0 10px 25px rgba(0,0,0,0.25);
      }

      .rpg-nav a {
        display: inline-block;
        color: var(--rpg-parchment);
        text-decoration: none;
        padding: 8px 10px;
        margin: 2px;
        border-radius: 10px;
        font-size: 0.92rem;
      }

      .rpg-nav a:hover {
        background: rgba(199, 154, 59, 0.18);
        color: #fff6df;
      }

      .rpg-nav {
        display: block;
      }

      .rpg-nav-primary,
      .rpg-nav-appendix-links {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
      }

      .rpg-nav-primary {
        padding-bottom: 6px;
      }

      .rpg-nav-appendix {
        margin-top: 6px;
        border-top: 1px solid rgba(226, 191, 109, 0.16);
        padding-top: 8px;
      }

      .rpg-nav-appendix > summary {
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: #fff1d0;
        border: 1px solid rgba(226, 191, 109, 0.22);
        background: rgba(255,255,255,0.035);
        border-radius: 999px;
        padding: 7px 11px;
        font-weight: 700;
        list-style: none;
      }

      .rpg-nav-appendix > summary::-webkit-details-marker {
        display: none;
      }

      .rpg-nav-appendix > summary::before {
        content: "▸";
        color: var(--rpg-gold);
        font-size: 0.8rem;
      }

      .rpg-nav-appendix[open] > summary::before {
        content: "▾";
      }

      .rpg-nav-appendix-links {
        margin-top: 9px;
      }

      .rpg-nav-appendix-links a {
        font-size: 0.84rem;
        opacity: 0.92;
      }

      .rpg-nav-primary a {
        font-size: 0.94rem;
      }

      .rpg-nav a {
        border: 1px solid rgba(226, 191, 109, 0.18);
        background: rgba(255,255,255,0.02);
        font-weight: 600;
      }

      .rpg-promoted-section {
        background:
          linear-gradient(180deg, rgba(241, 227, 200, 0.99), rgba(233, 214, 180, 0.985));
        color: var(--rpg-ink);
      }

      .rpg-promoted-section h2,
      .rpg-promoted-section h3,
      .rpg-promoted-section h4,
      .rpg-promoted-section strong,
      .rpg-promoted-section li,
      .rpg-promoted-section p,
      .rpg-promoted-section td,
      .rpg-promoted-section th,
      .rpg-promoted-section code {
        color: var(--rpg-ink);
      }

      .rpg-promoted-section .rpg-promoted-body {
        color: var(--rpg-ink);
      }

      .rpg-promoted-section .journal-entry,
      .rpg-promoted-section .npc-card,
      .rpg-promoted-section .metric-card {
        background: rgba(255, 249, 238, 0.92);
        color: var(--rpg-ink);
        border: 1px solid rgba(120, 83, 30, 0.22);
        border-radius: 14px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
      }

      .rpg-promoted-section table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 10px;
        background: rgba(255, 250, 242, 0.88);
        color: var(--rpg-ink);
        border-radius: 12px;
        overflow: hidden;
      }

      .rpg-promoted-section th,
      .rpg-promoted-section td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(120, 83, 30, 0.18);
        text-align: left;
      }

      .rpg-promoted-section a {
        color: #6b3f0b;
        font-weight: 700;
      }

      .rpg-promoted-section a:hover {
        color: #8a5315;
      }

      .rpg-promoted-section summary {
        color: var(--rpg-ink);
      }

      .rpg-promoted-section pre {
        background: rgba(33, 26, 20, 0.94);
        color: var(--rpg-parchment);
        border: 1px solid rgba(226, 191, 109, 0.2);
      }

      .report-quick-links {
        display: none !important;
      }

      .rpg-grid {
        display: grid;
        grid-template-columns: repeat(12, minmax(0, 1fr));
        gap: 18px;
      }

      .rpg-card {
        grid-column: span 12;
        background:
          linear-gradient(180deg, rgba(241, 227, 200, 0.98), rgba(230, 208, 170, 0.98));
        color: var(--rpg-ink);
        border: 1px solid rgba(120, 83, 30, 0.35);
        border-radius: 18px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.28);
        padding: 20px;
      }

      .rpg-card.dark {
        background: linear-gradient(180deg, rgba(42, 33, 25, 0.98), rgba(33, 26, 20, 0.98));
        color: var(--rpg-parchment);
        border-color: rgba(226, 191, 109, 0.28);
      }

      .rpg-card h2,
      .rpg-card h3 {
        margin-top: 0;
      }

      .rpg-section-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        border-bottom: 1px solid rgba(120, 83, 30, 0.25);
        padding-bottom: 10px;
        margin-bottom: 16px;
      }

      .rpg-section-title h2 {
        margin: 0;
        font-size: 1.45rem;
      }

      .rpg-stat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 12px;
      }

      .rpg-stat {
        background: rgba(255,255,255,0.36);
        border: 1px solid rgba(120, 83, 30, 0.18);
        border-radius: 14px;
        padding: 14px;
      }

      .rpg-stat.dark {
        background: rgba(0,0,0,0.18);
        border-color: rgba(226, 191, 109, 0.18);
      }

      .rpg-stat-label {
        color: var(--rpg-muted);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }

      .rpg-stat-value {
        font-size: 1.45rem;
        font-weight: 700;
        margin-top: 4px;
      }

      .rpg-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }

      .rpg-badge.pass { background: rgba(77, 138, 84, 0.18); color: #184f23; border: 1px solid rgba(77, 138, 84, 0.45); }
      .rpg-badge.warn { background: rgba(199, 154, 59, 0.22); color: #68480e; border: 1px solid rgba(199, 154, 59, 0.55); }
      .rpg-badge.fail { background: rgba(166, 66, 53, 0.18); color: #7b2018; border: 1px solid rgba(166, 66, 53, 0.45); }
      .rpg-badge.neutral { background: rgba(75, 111, 143, 0.14); color: #284b68; border: 1px solid rgba(75, 111, 143, 0.35); }

      .rpg-card.dark .rpg-badge.pass { color: #d8f1d9; }
      .rpg-card.dark .rpg-badge.warn { color: #ffe4a1; }
      .rpg-card.dark .rpg-badge.fail { color: #ffd5cf; }
      .rpg-card.dark .rpg-badge.neutral { color: #d8e8f6; }

      .rpg-timeline {
        position: relative;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .rpg-timeline li {
        position: relative;
        margin: 0 0 14px 0;
        padding: 0 0 0 34px;
      }

      .rpg-timeline li::before {
        content: "";
        position: absolute;
        left: 8px;
        top: 4px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--rpg-gold);
        box-shadow: 0 0 0 4px rgba(199,154,59,0.18);
      }

      .rpg-timeline li::after {
        content: "";
        position: absolute;
        left: 13px;
        top: 20px;
        width: 2px;
        height: calc(100% + 4px);
        background: rgba(120, 83, 30, 0.25);
      }

      .rpg-timeline li:last-child::after {
        display: none;
      }

      .rpg-turn-label {
        color: var(--rpg-muted);
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      .rpg-turn-title {
        font-weight: 700;
        margin-top: 2px;
      }

      .rpg-turn-body {
        margin-top: 4px;
        color: #3b2a1d;
      }

      .rpg-two-col {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 16px;
      }

      .rpg-mini-card {
        background: rgba(255,255,255,0.34);
        border: 1px solid rgba(120, 83, 30, 0.18);
        border-radius: 14px;
        padding: 14px;
      }

      .rpg-mini-card h3 {
        margin: 0 0 8px;
      }

      .rpg-table {
        width: 100%;
        border-collapse: collapse;
        overflow: hidden;
        border-radius: 12px;
      }

      .rpg-table th,
      .rpg-table td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(120, 83, 30, 0.18);
        vertical-align: top;
      }

      .rpg-table th {
        text-align: left;
        color: #5a3b16;
        background: rgba(199,154,59,0.18);
        font-size: 0.84rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      details.rpg-debug {
        background: rgba(0,0,0,0.18);
        border: 1px solid rgba(226,191,109,0.2);
        border-radius: 14px;
        margin: 12px 0;
        padding: 12px 14px;
      }

      details.rpg-debug > summary {
        cursor: pointer;
        color: #fff1d0;
        font-weight: 700;
      }

      .rpg-debug-body {
        margin-top: 12px;
      }

      pre, code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }

      pre {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }

      @media (min-width: 980px) {
        .rpg-card.span-4 { grid-column: span 4; }
        .rpg-card.span-6 { grid-column: span 6; }
        .rpg-card.span-8 { grid-column: span 8; }
        .rpg-card.span-12 { grid-column: span 12; }
      }

      html {
        scroll-behavior: smooth;
      }

      .rpg-shell [id] {
        scroll-margin-top: 94px;
      }

      .rpg-nav {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
      }

      .rpg-nav a {
        border: 1px solid rgba(226, 191, 109, 0.18);
        background: rgba(255, 255, 255, 0.04);
        white-space: nowrap;
      }

      .rpg-nav a::before {
        content: "◆";
        color: var(--rpg-gold);
        font-size: 0.65rem;
        margin-right: 7px;
      }

      .rpg-nav a:hover,
      .rpg-nav a:focus {
        outline: none;
        border-color: rgba(226, 191, 109, 0.48);
        background: rgba(199, 154, 59, 0.22);
      }

      .rpg-card.dark .rpg-section-title {
        border-bottom-color: rgba(226, 191, 109, 0.24);
      }

      .rpg-card.dark .rpg-section-title h2,
      .rpg-card.dark h2,
      .rpg-card.dark h3 {
        color: #fff6df;
      }

      .rpg-debug-body {
        color: var(--rpg-ink);
      }

      .rpg-debug-body section,
      .rpg-debug-body article,
      .rpg-debug-body .turn-card,
      .rpg-debug-body .metric,
      .rpg-debug-body .card,
      .rpg-debug-body .panel {
        background: rgba(241, 227, 200, 0.98) !important;
        color: var(--rpg-ink) !important;
        border-color: rgba(120, 83, 30, 0.28) !important;
      }

      .rpg-debug-body h1,
      .rpg-debug-body h2,
      .rpg-debug-body h3,
      .rpg-debug-body h4,
      .rpg-debug-body h5,
      .rpg-debug-body p,
      .rpg-debug-body li,
      .rpg-debug-body td,
      .rpg-debug-body th,
      .rpg-debug-body div,
      .rpg-debug-body span {
        color: inherit;
      }

      .rpg-debug-body h2,
      .rpg-debug-body h3,
      .rpg-debug-body h4 {
        color: #3a240f !important;
      }

      .rpg-debug-body a {
        color: #5b3a0b !important;
        font-weight: 700;
        text-decoration: underline;
        text-underline-offset: 2px;
      }

      .rpg-debug-body table {
        background: rgba(255,255,255,0.38);
        color: var(--rpg-ink);
      }

      .rpg-debug-body pre,
      .rpg-debug-body code {
        background: rgba(36, 23, 13, 0.08);
        color: #24170d;
      }

      .rpg-debug-body .muted,
      .rpg-debug-body .small,
      .rpg-debug-body .subtle {
        color: #6c5136 !important;
      }

      .rpg-debug-body details {
        background: rgba(255,255,255,0.22);
        color: var(--rpg-ink);
      }

      .rpg-debug-note {
        background: rgba(199, 154, 59, 0.16);
        border: 1px solid rgba(120, 83, 30, 0.22);
        border-radius: 12px;
        padding: 10px 12px;
        margin: 0 0 14px;
        color: #3a240f !important;
      }

      .rpg-muted-line {
        color: #6c5136;
        font-size: 0.92rem;
      }

      .rpg-compact-list {
        margin: 8px 0 0;
        padding-left: 20px;
      }

      .rpg-compact-list li {
        margin: 4px 0;
      }

      .rpg-tag-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 8px;
      }

      .rpg-tag {
        display: inline-flex;
        border: 1px solid rgba(120, 83, 30, 0.25);
        background: rgba(255, 255, 255, 0.35);
        color: #4b331d;
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 0.78rem;
        font-weight: 700;
      }

      .rpg-card.dark .rpg-tag {
        color: #fff1d0;
        border-color: rgba(226, 191, 109, 0.25);
        background: rgba(0, 0, 0, 0.18);
      }

      .rpg-npc-grid,
      .rpg-location-grid,
      .rpg-quest-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 14px;
      }

      .rpg-character-card,
      .rpg-location-card,
      .rpg-quest-card {
        background: rgba(255, 255, 255, 0.34);
        border: 1px solid rgba(120, 83, 30, 0.2);
        border-radius: 16px;
        padding: 15px;
      }

      .rpg-character-card h3,
      .rpg-location-card h3,
      .rpg-quest-card h3 {
        margin: 0 0 6px;
      }

      .rpg-kv-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 8px;
        margin-top: 10px;
      }

      .rpg-kv {
        background: rgba(255, 255, 255, 0.28);
        border-radius: 10px;
        padding: 8px;
      }

      .rpg-kv-label {
        color: #755c3f;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      .rpg-kv-value {
        margin-top: 3px;
        font-weight: 700;
      }

      .rpg-debug-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
        gap: 12px;
      }

      details.rpg-debug-group {
        background: rgba(241, 227, 200, 0.98);
        color: var(--rpg-ink);
        border: 1px solid rgba(120, 83, 30, 0.28);
        border-radius: 14px;
        padding: 12px 14px;
      }

      details.rpg-debug-group > summary {
        cursor: pointer;
        font-weight: 800;
        color: #3a240f;
      }

      .rpg-debug-group-body {
        margin-top: 12px;
      }

      .rpg-story-beat-source {
        font-size: 0.8rem;
        color: #765c3c;
        margin-top: 3px;
      }

      /*
       * Safety net: old legacy report shells should not appear as standalone
       * report headers inside the RPG report. The Python sanitizer removes
       * them; these rules prevent visual theme leakage if one slips through.
       */
      .rpg-debug-body > header,
      .rpg-debug-group-body > header,
      .rpg-debug-body section.hero,
      .rpg-debug-group-body section.hero {
        display: none !important;
      }

.progression-graph {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-top: 1rem;
}

.graph-node {
  display: grid;
  grid-template-columns: 2.25rem 1fr;
  gap: 0.75rem;
  align-items: center;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 0.9rem;
  padding: 0.75rem;
  background: rgba(15, 23, 42, 0.58);
}

.graph-node-index {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  background: rgba(148, 163, 184, 0.18);
  border: 1px solid rgba(148, 163, 184, 0.32);
}

.graph-node-title {
  font-weight: 750;
  letter-spacing: 0.01em;
}

.graph-node-meta {
  margin-top: 0.2rem;
  font-size: 0.85rem;
  opacity: 0.75;
}

.graph-node-completed {
  border-color: rgba(34, 197, 94, 0.45);
  background: linear-gradient(135deg, rgba(22, 163, 74, 0.20), rgba(15, 23, 42, 0.60));
}

.graph-node-pending {
  border-color: rgba(234, 179, 8, 0.40);
  background: linear-gradient(135deg, rgba(234, 179, 8, 0.12), rgba(15, 23, 42, 0.60));
}

.graph-edge {
  text-align: center;
  opacity: 0.5;
  font-size: 1.2rem;
  line-height: 1;
}
    """
    arc_cards_html = "".join(
        '<div class="story-card">'
        f'<h3>{_esc(arc.get("title"))}</h3>'
        f'<p><strong>Stage:</strong> {_esc(arc.get("stage"))} · <strong>Status:</strong> {_esc(arc.get("status"))}</p>'
        f'<p><strong>Completed Objectives:</strong> {_esc(arc.get("completed_count"))} · <strong>Active Objectives:</strong> {_esc(arc.get("active_count"))}</p>'
        f'{_render_bar("Arc Pressure", arc.get("pressure", 0), max_value=100)}'
        '</div>'
        for arc in _safe_list(_safe_dict(model.get("story_arc_view")).get("arcs"))
    )
    milestone_pm_rows = [
        [
            row.get("arc_id"),
            row.get("title"),
            row.get("status"),
            row.get("priority"),
            row.get("completed_turn_index"),
        ]
        for row in _safe_list(model.get("milestones"))
    ]
    player_view = _safe_dict(model.get("player_progression_view"))
    inventory_start_view = _safe_dict(model.get("inventory_start_view"))
    inventory_end_view = _safe_dict(model.get("inventory_end_view"))
    location_cards_html = "".join(
        '<div class="story-card">'
        f'<h3>{_esc(loc.get("name"))}</h3>'
        f'<p><strong>Turns:</strong> {_esc(loc.get("turn_range"))} · <strong>Turn Count:</strong> {_esc(loc.get("turn_count"))}</p>'
        f'<p>{_esc(loc.get("summary"))}</p>'
        f'<p><strong>NPCs:</strong> {_esc(", ".join(_safe_list(loc.get("npcs"))) or "None captured")}</p>'
        f'<p><strong>Objectives:</strong> {_esc(", ".join(_safe_list(loc.get("objectives"))) or "None captured")}</p>'
        f'{_render_json_details("Location events", loc.get("events"))}'
        '</div>'
        for loc in _safe_list(_safe_dict(model.get("location_journey")).get("locations"))
    )
    progress_quality_bars = "\n".join(
        [
            _render_progress_bar("Meaningful Progress Rate", progress_quality.get("meaningful_progress_rate")),
            _render_progress_bar("Churn-only Rate", progress_quality.get("churn_only_rate")),
            _render_progress_bar("Weak Progress Rate", progress_quality.get("weak_progress_rate")),
            _render_progress_bar("No-change Rate", progress_quality.get("no_change_rate")),
        ]
    )
    stage_values = [
        _safe_dict(v).get("total_ms", 0) / 1000.0
        for v in _safe_dict(performance.get("stage_summary")).values()
    ]
    max_stage_seconds = max(stage_values or [1.0])
    performance_stage_bars = "\n".join(
        _render_bar(
            key.replace("_ms", "").replace("_", " ").title(),
            _safe_dict(value).get("total_ms", 0) / 1000.0,
            max_value=max_stage_seconds,
            suffix="s",
        )
        for key, value in _safe_dict(performance.get("stage_summary")).items()
    )
    legacy_report_sections = f"""
      {_render_calendar_and_journal(model.get("campaign_calendar_summary") or {}, model.get("player_journal_summary") or {})}
      {_render_quest_progress(_quest_summary_from_latest_state(model) or _safe_dict(model.get("quest_progress_summary")) or {})}
      {_render_npc_evolution_cards(model.get("npc_evolution_report_summary") or {})}
      {_render_hundred_turn_eval(model)}
      {_render_action_diversity(model.get("action_diversity_summary") or {})}
      {_render_progress_timeline(model.get("progress_timeline_summary") or {})}
      {_render_background_result_timing(model.get("background_result_timing_summary") or {})}


    <section class="rpg-promoted-section" id="story-so-far">
    <h2>Story So Far</h2>
    <p class="section-lede">A readable summary of what happened in the campaign before the technical diagnostics.</p>
    {_render_paragraphs(model.get("story_so_far_paragraph"))}
    {_render_json_details("Story timeline summary inputs", {"milestones": model.get("milestones"), "journal_entries": model.get("journal_entries"), "hook_counts": model.get("hook_counts")})}
  </section>

  <section class="rpg-promoted-section" id="setting">
    <h2>Lore, Setting, and Director Setup</h2>
    <p class="section-lede">The premise, stakes, and setting context that frame the campaign run.</p>
    {_render_paragraphs(model.get("lore_setting_paragraph"))}
    <div class="card-list">
      {''.join(
        f'<div class="story-card"><h3>{_esc(row.get("title") or row.get("name") or row.get("id"))}</h3><p>{_esc(row.get("text") or row.get("description") or row.get("summary"))}</p></div>'
        for row in _safe_list(model.get("lore"))
      )}
    </div>
    {_render_json_details("Director state JSON", _safe_dict(latest_state.get("campaign_director_state")))}
  </section>

  <section class="rpg-promoted-section" id="arcs">
    <h2>Story Arc Status</h2>
    <p class="section-lede">A product/story view of campaign branches, active objectives, and completed beats.</p>
    <div class="card-list">
      {arc_cards_html}
    </div>
    <h3>Objectives / Milestones</h3>
    {_render_table(["Arc", "Objective", "Status", "Priority", "Completed Turn"], milestone_pm_rows)}
    {_render_json_details("Story arcs JSON", model.get("story_arcs"))}
    {_render_json_details("Milestones JSON", model.get("milestones"))}
   </section>

  {_render_progression_graph_section(summary)}

  <section class="rpg-promoted-section" id="locations">
    <h2>Location Journey</h2>
    <p class="section-lede">Where the run traveled, what happened there, who was involved, and what objectives were tied to each place.</p>
    <div class="card-list">
      {location_cards_html}
    </div>
    {_render_json_details("Location journey JSON", model.get("location_journey"))}
  </section>

  <section class="rpg-promoted-section" id="variety">
    <h2>Story Variety</h2>
    <p class="section-lede">Identifies which campaign seed ran and gives stable signatures for comparing story setups across multiple autoplay runs.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(story_variety.get("resolved_seed"))}</div><div>Resolved Seed</div></div>
      <div class="metric"><div class="value">{_esc(story_variety.get("randomized"))}</div><div>Randomized</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(story_variety.get("story_signature")).get("signature_hash"))}</div><div>Story Signature</div></div>
      <div class="metric"><div class="value">{_esc(story_variety.get("branch_signature_hash"))}</div><div>Branch Signature</div></div>
    </div>
    {_render_json_details("Story variety JSON", story_variety)}
  </section>

    <section class="rpg-promoted-section" id="run-validity">
    <h2>Run Validity</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(metrics.get("player_agent_exception_count"))}</div><div>Player-Agent Exceptions</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("fallback_player_actions"))}</div><div>Fallback Player Actions</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("fallback_player_action_rate"))}</div><div>Fallback Action Rate</div></div>
    </div>
    <p class="muted">A high fallback rate means this campaign reflects deterministic fallback action selection more than true LLM-player behavior.</p>
  </section>

  <section class="rpg-promoted-section" id="chapter-status">
    <h2>Chapter Status</h2>
    <p class="section-lede">Current campaign chapter, active story goals, completed goals, and recommended next direction.</p>
    {_render_chapter_status_cards(chapter_status)}
  </section>

  <section class="rpg-promoted-section" id="product-evaluation">
    <h2>Product Evaluation</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(pm_summary.get("story_status"))}</div><div>Story Continuity</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("dialogue_status"))}</div><div>Dialogue Coverage</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("provider_status"))}</div><div>Provider Narration</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("performance_status"))}</div><div>Performance</div></div>
    </div>
    <h3>Top Risks / Follow-ups</h3>
    {("<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in _safe_list(pm_summary.get("top_risks"))) + "</ul>") if _safe_list(pm_summary.get("top_risks")) else '<p class="good">No major PM-level risks detected.</p>'}
  </section>
  """
    body_sections = f"""
  <section class="rpg-promoted-section" id="player">
    <h2>Player Character Progression / Stats</h2>
    <p class="section-lede">A readable snapshot of level, XP, core stats, and progression events.</p>
    {_render_paragraphs(model.get("character_progression_paragraph"))}
    <div class="two-col">
      <div>
        <h3>Character Summary</h3>
        {_render_key_value_table(_safe_list(player_view.get("summary_rows")))}
      </div>
      <div>
        <h3>Starting Stats</h3>
        {_render_table(["Stat", "Value"], _safe_list(player_view.get("stats_rows")))}
      </div>
    </div>
    <h3>Recent Progression Events</h3>
    {_render_table(["Turn", "Type", "Amount", "Reason", "Level"], _safe_list(player_view.get("recent_progression_rows")))}
    {_render_json_details("Player progression JSON", model.get("player_progression"))}
  </section>

  <section class="rpg-promoted-section" id="inventory">
    <h2>Inventory: Start vs End</h2>
    <p class="muted">Shows whether the campaign changed carried items, currency, or inventory-like state during the run.</p>
    <div class="two-col">
      <div>
        <h3>Starting Inventory</h3>
        <h4>Currency</h4>
        {_render_table(["Currency", "Amount"], _safe_list(inventory_start_view.get("currency_rows")))}
        <h4>Items</h4>
        {_render_table(["Item", "Qty", "Type", "Description"], _safe_list(inventory_start_view.get("item_rows")))}
      </div>
      <div>
        <h3>Ending Inventory</h3>
        <h4>Currency</h4>
        {_render_table(["Currency", "Amount"], _safe_list(inventory_end_view.get("currency_rows")))}
        <h4>Items</h4>
        {_render_table(["Item", "Qty", "Type", "Description"], _safe_list(inventory_end_view.get("item_rows")))}
      </div>
    </div>
    {_render_json_details("Raw inventory start/end JSON", {"start": model.get("inventory_start"), "end": model.get("inventory_end")})}
   </section>

  <section class="rpg-promoted-section" id="npcs">
    <h2>NPC Cast, Biography, and Growth</h2>
    <p class="muted">A product/story view of who appeared, why they matter, and how their relationship or role changed.</p>
    {_render_table(["Name", "Role", "Dialogue Turns", "History", "Biography", "Growth / Arc"], npc_rows)}
    {_render_json_details("NPC dialogue counts", model.get("npc_dialogue_counts"))}
    {_render_json_details("NPC progression state", _safe_dict(_safe_dict(latest_state.get("npc_progression_state")).get("npcs")))}
  </section>

  <section class="rpg-promoted-section" id="dialogue-coverage">
    <h2>Dialogue Coverage</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("npc_response_turn_count"))}</div><div>Turns with NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("social_turn_missing_npc_response_count"))}</div><div>Social Turns Missing NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("hook_dialogue_turn_count"))}</div><div>Hook Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("base_runtime_dialogue_turn_count"))}</div><div>Base Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("real_runtime_dialogue_turn_count"))}</div><div>Real Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("real_runtime_provider_dialogue_turn_count"))}</div><div>Provider Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("echoed_narration_turn_count"))}</div><div>Echoed Narration Turns</div></div>
    </div>
    <details>
      <summary>Dialogue coverage debug</summary>
      <pre>{_json(model.get("dialogue_coverage"))}</pre>
      </details>
    </section>

  <section class="rpg-promoted-section" id="performance">
    <h2>Performance Metrics</h2>
    <p class="section-lede">Runtime speed and where time is spent. Playability latency separates the blocking turn path from background narration/checkpoint/report work.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_number(performance.get("campaign_wall_seconds"), 2))}s</div><div>Campaign Wall Time</div></div>
      <div class="metric"><div class="value">{_esc(performance.get("turns_per_second"))}</div><div>Turns / Second</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_turn_ms")))}</div><div>Average Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_turn_ms")))}</div><div>p95 Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_turn_ms")))}</div><div>Max Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("artifact_write_ms")))}</div><div>Report Write Time</div></div>
    </div>
    <h3>Playability Latency</h3>
    <p class="muted">
      Autoplay blocking includes the LLM player-agent. Human-equivalent blocking excludes the player-agent because a real player supplies the action.
    </p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_human_playable_blocking_ms")))}</div><div>Avg Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_human_playable_blocking_ms")))}</div><div>p95 Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_human_playable_blocking_ms")))}</div><div>Max Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_playable_blocking_ms")))}</div><div>Avg Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_playable_blocking_ms")))}</div><div>p95 Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_playable_blocking_ms")))}</div><div>Max Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("background_jobs")).get("total_jobs"))}</div><div>Background Jobs</div></div>
      <div class="metric"><div class="value">{_esc(_number(_safe_dict(model.get("background_jobs")).get("background_job_seconds"), 2))}s</div><div>Background Worker Time</div></div>
    </div>
    <h3>Evaluation Wall Time</h3>
    {performance_stage_bars}
    {_render_json_details("Stage summary JSON", performance.get("stage_summary") or {})}
    {_render_json_details("Provider trace summary JSON", model.get("provider_trace_summary") or {})}
    {_render_json_details("Manual harness trace summary JSON", model.get("manual_harness_trace_summary") or {})}
    {_render_json_details("Session turn trace summary JSON", model.get("turn_perf_trace_summary") or {})}
    {_render_json_details("Player-agent trace summary JSON", model.get("player_agent_trace_summary") or {})}
    {_render_json_details("Deferred narration trace summary JSON", model.get("deferred_narration_trace_summary") or {})}
    {_render_json_details("Deferred advisory trace summary JSON", model.get("deferred_advisory_trace_summary") or {})}
    {_render_json_details("Performance budget summary JSON", model.get("performance_budget_summary") or {})}
    {_render_json_details("Background prompt budget summary JSON", model.get("background_prompt_budget_summary") or {})}
    {_render_json_details("Combined quality shape summary JSON", model.get("combined_quality_shape_summary") or {})}
    {_render_json_details("Player-agent prompt budget summary JSON", model.get("player_agent_prompt_budget_summary") or {})}
    {_render_json_details("Player-agent cache summary JSON", model.get("player_agent_cache_summary") or {})}
    {_render_json_details("Deferred advisory promotion summary JSON", model.get("deferred_advisory_promotion_summary") or {})}
    {_render_json_details("NPC evolution summary JSON", model.get("npc_evolution_summary") or {})}
    {_render_json_details("NPC evolution profile persistence summary JSON", model.get("npc_evolution_profile_persistence_summary") or {})}
    {_render_json_details("NPC profile load summary JSON", model.get("npc_profile_load_summary") or {})}
    {_render_json_details("Profile-grounded output summary JSON", model.get("profile_grounded_output_summary") or {})}
    {_render_json_details("NPC arc progression summary JSON", model.get("npc_arc_progression_summary") or {})}
    {_render_json_details("Promotion target grounding summary JSON", model.get("promotion_target_grounding_summary") or {})}
    {_render_json_details("Quality gate summary JSON", model.get("quality_gate_summary") or {})}
    {_render_json_details("Scenario progression summary JSON", model.get("scenario_progression_summary") or {})}
    {_render_json_details("Behavioral autoplay eval summary JSON", model.get("behavioral_autoplay_eval_summary") or {})}
    {_render_json_details("Slowest turns JSON", performance.get("slowest_turns") or [])}
     {_render_json_details("Background job summary JSON", model.get("background_jobs") or {})}
  </section>

  <section class="rpg-promoted-section" id="quality">
    <h2>Progress Quality & Action Diversity</h2>
    <p class="section-lede">How often the campaign produced meaningful story/game progress versus weak progress, churn, or no visible change.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(progress_quality.get("churn_only_turns"))}</div><div>Churn-only Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("weak_progress_turns"))}</div><div>Weak Progress Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("no_change_turns"))}</div><div>No-change Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("action_diversity")).get("action_diversity_rate"))}</div><div>Action Diversity Rate</div></div>
    </div>
    <h3>Progress Distribution</h3>
    {progress_quality_bars}
    {_render_json_details("Progress category counts", model.get("category_counts"))}
    <h3>Hook Counts</h3>
    {_render_json_details("Hook counts", model.get("hook_counts"))}
  </section>

    {_render_qa_dashboard(summary, metrics)}

  <section class="rpg-promoted-section" id="runtime-narration-diagnostics">
    <h2>Runtime Narration Diagnostics</h2>
    <p class="muted">Provider validity, repair, fallback, and method-call diagnostics.</p>
    {_render_json_details("Runtime narration diagnostics JSON", model.get("runtime_narration_diagnostics"))}
   </section>

    <section class="rpg-promoted-section" id="timeline">
    <h2>Turn-by-Turn Story Timeline with AI/NPC Responses</h2>
    {''.join(timeline_html)}
   </section>

    {_render_console_log_summary(model.get("console_log_summary") or {})}
    {_render_json_details("Console log summary JSON", model.get("console_log_summary") or {})}

    <section class="rpg-promoted-section" id="debug">
      <h2>Raw Debug Appendix</h2>
      <p><strong>Latest state source:</strong> {_esc(model.get("latest_state_source"))}</p>
      {_render_json_details("Story beat fallback summary JSON", model.get("story_beat_summary") or {})}
      {_render_json_details("Player journal quality summary JSON", model.get("player_journal_quality_summary") or {})}
      {_render_json_details("Manual turn error summary JSON", model.get("manual_turn_error_summary") or {})}
      {_render_json_details("100-turn eval summary JSON", model.get("hundred_turn_eval_summary") or {})}
      {_render_json_details("Action diversity summary JSON", model.get("action_diversity_summary") or {})}
      {_render_json_details("Progress timeline summary JSON", model.get("progress_timeline_summary") or {})}
      {_render_json_details("Long-run warning summary JSON", model.get("long_run_warning_summary") or {})}
{_render_json_details("Background result timing summary JSON", model.get("background_result_timing_summary") or {})}
{_render_json_details("Background drain events JSON", {"events": model.get("background_drain_events") or []})}
      {_render_json_details("Latest Simulation State", latest_state)}
      {_render_json_details("Summary JSON", summary)}
      {_render_json_details("Metrics JSON", metrics)}
    </section>"""

    primary_links = [
        ("campaign-overview", "Overview"),
        ("verdict-cards", "Validation"),
        ("autoplay-campaign-report", "Run Report"),
        ("story-so-far", "Story"),
        ("chapter-status", "Chapter"),
        ("performance", "Performance"),
        ("timeline", "Timeline"),
    ]
    appendix_links = [
        ("campaign-journal", "Journal"),
        ("quest-progress", "Quests"),
        ("npc-evolution", "NPC Evolution"),
        ("hundred-turn-eval", "100-Turn Eval"),
        ("action-diversity", "Action Diversity"),
        ("progress-timeline", "Progress Timeline"),
        ("background-result-timing", "Background Timing"),
        ("story-so-far", "Story So Far"),
        ("setting", "Setting"),
        ("arcs", "Story Arcs"),
        ("locations", "Locations"),
        ("variety", "Variety"),
        ("run-validity", "Run Validity"),
        ("chapter-status", "Chapter Status"),
        ("product-evaluation", "Product Evaluation"),
        ("player", "Player"),
        ("inventory", "Inventory"),
        ("npcs", "NPC Cast"),
        ("dialogue-coverage", "Dialogue Coverage"),
        ("adventure-timeline", "Adventure Timeline"),
        ("quest-board", "Quest Board"),
        ("npc-chronicle", "NPC Chronicle"),
        ("console-log", "Console Log"),
        ("runtime-narration-diagnostics", "Runtime Diagnostics"),
        ("debug", "Debug"),
    ]
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_esc(_safe_str(chronicle_model.get("title")) or "Autoplay Campaign Report")}</title>
    <style>
{css}
    </style>
</head>
<body>
    <main class="rpg-shell">
        {_render_rpg_hero(chronicle_model)}
        {_render_rpg_nav_links(primary_links, appendix_links)}
        {_render_rpg_verdict_cards(chronicle_model)}
        {_render_autoplay_campaign_report_partial(summary, metrics)}
        {legacy_report_sections}
        {body_sections}
    </main>
</body>
</html>"""
    return _finalize_campaign_report_html(html_doc)


def write_campaign_report(
    *,
    output_dir: Path,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_campaign_report_model(
        transcript=transcript,
        summary=summary,
        metrics=metrics,
        health=health,
    )
    model_path = output_dir / "autoplay-campaign-report.json"
    html_path = output_dir / "autoplay-campaign-report.html"
    model_path.write_text(
        json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    html = render_campaign_report_html(
        summary=_safe_dict(model.get("summary")),
        metrics=_safe_dict(model.get("metrics")),
        transcript=_as_list(model.get("transcript")),
        report_model=model if isinstance(model, dict) else None,
    )
    html = _finalize_campaign_report_html(html)
    if "status-pill" in html or "<h2>Executive Summary</h2>" in html:
        html = re.sub(
            r"<header\b[^>]*>\s*.*?Autoplay Campaign Report.*?\bstatus-pill\b.*$",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    html = _finalize_campaign_report_html(html)
    if len(_safe_str(html).strip()) < 1000:
        raise RuntimeError(
            "campaign_report_html_empty_or_too_small: "
            f"bytes={len(_safe_str(html).encode('utf-8'))}"
        )
    if "<!doctype html>" not in html.lower():
        raise RuntimeError("campaign_report_html_missing_doctype")
    if "<style" not in html.lower():
        raise RuntimeError("campaign_report_html_missing_style_block")
    if "rpg-shell" not in html:
        raise RuntimeError("campaign_report_html_missing_rpg_shell")
    html_path.write_text(html, encoding="utf-8")
    return {
        "campaign_report_json": str(model_path),
        "campaign_report_html": str(html_path),
    }








