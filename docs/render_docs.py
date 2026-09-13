from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FENCE = chr(96) * 3
GUIDE_SOURCES = [
    DOCS / "README.md",
    DOCS / "FEATURES.md",
    DOCS / "ARCHITECTURE.md",
    DOCS / "SETUP.md",
    DOCS / "DEVELOPMENT.md",
    DOCS / "OPERATIONS.md",
    DOCS / "HERMES_SIDECAR_SETUP.md",
    ROOT / "README.md",
    ROOT / "SPEC.md",
]


def slugify(value: str, used: dict[str, int]) -> str:
    plain = re.sub(r"\x60([^\x60]+)\x60", r"\1", value)
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "section"
    count = used.get(slug, 0)
    used[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count + 1}"


def rewrite_link(href: str) -> str:
    parsed = urlsplit(href.strip())
    if parsed.scheme or parsed.netloc or parsed.path.startswith("#"):
        return href
    path = parsed.path
    if path.lower().endswith(".md"):
        path = path[:-3] + ".html"
    return urlunsplit(("", "", path, parsed.query, parsed.fragment))


def render_inline(value: str) -> str:
    placeholders: list[tuple[str, str]] = []

    def hold(fragment: str) -> str:
        token = f"@@MDTOKEN{len(placeholders)}@@"
        placeholders.append((token, fragment))
        return token

    value = re.sub(
        r"\x60([^\x60]+)\x60",
        lambda match: hold(f"<code>{html.escape(match.group(1))}</code>"),
        value,
    )

    def render_image(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1).strip(), quote=True)
        src = rewrite_link(match.group(2))
        return hold(
            f'<img class="guide-image" src="{html.escape(src, quote=True)}" alt="{alt}" loading="lazy">'
        )

    value = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", render_image, value)

    def render_link(match: re.Match[str]) -> str:
        raw_label = match.group(1)
        code_label = re.fullmatch(r"`([^`]+)\.md`", raw_label.strip(), flags=re.IGNORECASE)
        if code_label:
            raw_label = f"`{code_label.group(1)}.html`"
        elif raw_label.strip().lower().endswith(".md"):
            raw_label = raw_label.strip()[:-3] + ".html"
        label = render_inline(raw_label)
        href = rewrite_link(match.group(2))
        return hold(f'<a href="{html.escape(href, quote=True)}">{label}</a>')

    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", render_link, value)
    escaped = html.escape(value)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<![\w_])_([^_]+)_(?![\w_])", r"<em>\1</em>", escaped)

    # Link labels can contain inline code, so an outer placeholder may contain
    # an inner placeholder. Resolve in passes until nested fragments are done.
    for _ in range(len(placeholders) + 1):
        changed = False
        for token, fragment in placeholders:
            if token in escaped:
                escaped = escaped.replace(token, fragment)
                changed = True
        if not changed:
            break
    return escaped


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def render_diagram(kind: str) -> str | None:
    diagrams = {
        "architecture": (
            "Platform architecture",
            "The browser calls one gateway, which coordinates authoritative state, artifacts, and optional services.",
            """
<div class="diagram diagram-architecture" aria-label="Browser to FastAPI gateway to PostgreSQL, artifact storage, and optional services">
  <div class="diagram-lane">
    <div class="diagram-node diagram-node-primary"><span class="diagram-kicker">CLIENT</span><strong>Omnix Web</strong><small>React, typed API, Query, UI state, event client</small></div>
    <span class="diagram-arrow" aria-hidden="true">→</span>
    <div class="diagram-node diagram-node-primary"><span class="diagram-kicker">BOUNDARY</span><strong>FastAPI gateway</strong><small>Routes, contracts, services, jobs, events, policy</small></div>
  </div>
  <div class="diagram-drop" aria-hidden="true">↓</div>
  <div class="diagram-branches">
    <div class="diagram-node"><span class="diagram-kicker">AUTHORITATIVE</span><strong>PostgreSQL</strong><small>Structured state, migrations, recovery</small></div>
    <div class="diagram-node"><span class="diagram-kicker">DURABLE OUTPUTS</span><strong>Assets and blobs</strong><small>Media, reports, exports, model resources</small></div>
    <div class="diagram-node"><span class="diagram-kicker">OPTIONAL BOUNDARIES</span><strong>Providers and workers</strong><small>LLM, TTS, STT, image, Hermes, market data</small></div>
  </div>
</div>""",
        ),
        "job-lifecycle": (
            "Shared job lifecycle",
            "Long-running work becomes observable, cancellable, retryable, and linked to durable outputs.",
            """
<div class="diagram diagram-steps" aria-label="Job lifecycle from input through routing, execution, events, storage, and review">
  <div class="diagram-step"><span>01</span><strong>Input</strong><small>Prompt, file, session, or schedule</small></div>
  <div class="diagram-step"><span>02</span><strong>Route</strong><small>Domain, provider, model, capability</small></div>
  <div class="diagram-step"><span>03</span><strong>Run</strong><small>Stages, resources, progress, logs</small></div>
  <div class="diagram-step"><span>04</span><strong>Stream</strong><small>SSE or WebSocket state updates</small></div>
  <div class="diagram-step"><span>05</span><strong>Store</strong><small>PostgreSQL record plus asset references</small></div>
  <div class="diagram-step"><span>06</span><strong>Review</strong><small>Render, accept, retry, or recover</small></div>
</div>""",
        ),
        "agent-flow": (
            "Governed agent flow",
            "Model reasoning proposes work; deterministic Omnix code owns grants, evidence, acceptance, and recovery.",
            """
<div class="diagram diagram-steps diagram-agent" aria-label="Governed agent flow from request through plan, grants, execution, evidence, and acceptance">
  <div class="diagram-step"><span>01</span><strong>Request</strong><small>Normalize the objective and revision</small></div>
  <div class="diagram-step"><span>02</span><strong>Plan</strong><small>Build and review the TaskGraph</small></div>
  <div class="diagram-step"><span>03</span><strong>Grant</strong><small>Issue narrow capabilities and scopes</small></div>
  <div class="diagram-step"><span>04</span><strong>Execute</strong><small>Run in the bounded workspace</small></div>
  <div class="diagram-step"><span>05</span><strong>Evidence</strong><small>Validate the candidate for this revision</small></div>
  <div class="diagram-step"><span>06</span><strong>Accept</strong><small>Review, recover, or stop</small></div>
</div>""",
        ),
        "service-topology": (
            "Local service topology",
            "The core loop is small; model-heavy and integration workloads can remain separate processes or environments.",
            """
<div class="diagram diagram-service" aria-label="Browser and launcher connect to the gateway, which connects to PostgreSQL, workers, and providers">
  <div class="diagram-lane">
    <div class="diagram-node diagram-node-primary"><span class="diagram-kicker">5173 / 5055</span><strong>Web and launcher</strong><small>Browser UI plus optional Windows control dashboard</small></div>
    <span class="diagram-arrow" aria-hidden="true">→</span>
    <div class="diagram-node diagram-node-primary"><span class="diagram-kicker">8000</span><strong>FastAPI gateway</strong><small>API, events, orchestration, diagnostics</small></div>
  </div>
  <div class="diagram-drop" aria-hidden="true">↓</div>
  <div class="diagram-branches">
    <div class="diagram-node"><span class="diagram-kicker">5432</span><strong>PostgreSQL</strong><small>Authoritative structured persistence</small></div>
    <div class="diagram-node"><span class="diagram-kicker">5101 / 5201 / 5301</span><strong>ML workers</strong><small>TTS, STT, and image services with explicit readiness</small></div>
    <div class="diagram-node"><span class="diagram-kicker">CONFIGURED URLS</span><strong>Providers and sidecars</strong><small>LLM, Hermes, market data, and governed integrations</small></div>
  </div>
</div>""",
        ),
        "documentation-pipeline": (
            "Documentation pipeline",
            "Markdown remains editable source material; generated HTML gives local browser readers a complete, navigable guide set.",
            """
<div class="diagram diagram-steps diagram-pipeline" aria-label="Markdown sources are rendered into HTML guides and opened through the documentation portal">
  <div class="diagram-step"><span>01</span><strong>Write</strong><small>Edit the Markdown guide or source contract</small></div>
  <div class="diagram-step"><span>02</span><strong>Render</strong><small>Run <code>python docs/render_docs.py</code></small></div>
  <div class="diagram-step"><span>03</span><strong>Publish</strong><small>Update the matching HTML guide pages</small></div>
  <div class="diagram-step"><span>04</span><strong>Browse</strong><small>Use the portal, links, search, and print view</small></div>
</div>""",
        ),
    }
    entry = diagrams.get(kind.strip().lower())
    if entry is None:
        return None
    title, summary, markup = entry
    safe_kind = re.sub(r"[^a-z0-9-]+", "-", kind.lower()).strip("-")
    title_id = f"diagram-{safe_kind}-title"
    return (
        f'<figure class="doc-diagram" aria-labelledby="{title_id}">'
        f'<figcaption id="{title_id}"><strong>{html.escape(title)}</strong>'
        f'<span>{html.escape(summary)}</span></figcaption>{markup}</figure>'
    )


def render_markdown(source: str) -> tuple[str, str]:
    lines = source.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    used_slugs: dict[str, int] = {}
    first_heading = ""

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    def add_code(code_lines: list[str], language: str = "") -> None:
        class_name = f' class="language-{html.escape(language, quote=True)}"' if language else ""
        code = html.escape("\n".join(code_lines))
        output.append(
            '<div class="code-wrap"><button class="copy-code" type="button">Copy</button>'
            f"<pre><code{class_name}>{code}</code></pre></div>"
        )

    index = 0
    while index < len(lines):
        line = lines[index]

        fence = re.match(r"^\s*" + re.escape(FENCE) + r"\s*(.*?)\s*$", line)
        if fence:
            flush_paragraph()
            close_list()
            fence_info = fence.group(1)
            fence_parts = fence_info.split()
            language = fence_parts[0] if fence_parts else ""
            diagram_kind = fence_parts[1] if language == "omnix-diagram" and len(fence_parts) > 1 else ""
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not re.match(r"^\s*" + re.escape(FENCE) + r"\s*$", lines[index]):
                code_lines.append(lines[index])
                index += 1
            diagram = render_diagram(diagram_kind)
            if language == "omnix-diagram" and diagram:
                output.append(diagram)
            else:
                add_code(code_lines, language)
            if index < len(lines):
                index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            text = heading.group(2)
            heading_id = slugify(text, used_slugs)
            if not first_heading and level == 1:
                first_heading = re.sub(r"\x60([^\x60]+)\x60", r"\1", text)
            output.append(f'<h{level} id="{heading_id}">{render_inline(text)}</h{level}>')
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            flush_paragraph()
            close_list()
            headers = split_table_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(split_table_row(lines[index]))
                index += 1
            output.append('<div class="table-wrap"><table><thead><tr>')
            output.extend(f"<th>{render_inline(cell)}</th>" for cell in headers)
            output.append("</tr></thead><tbody>")
            for row in rows:
                output.append("<tr>")
                for cell in row:
                    output.append(f"<td>{render_inline(cell)}</td>")
                output.append("</tr>")
            output.append("</tbody></table></div>")
            continue

        if re.match(r"^\s{4}", line) and line.strip():
            flush_paragraph()
            close_list()
            code_lines: list[str] = []
            while index < len(lines):
                current = lines[index]
                if current.startswith("    "):
                    code_lines.append(current[4:])
                    index += 1
                elif not current.strip():
                    code_lines.append("")
                    index += 1
                else:
                    break
            while code_lines and not code_lines[-1]:
                code_lines.pop()
            add_code(code_lines)
            continue

        blockquote = re.match(r"^\s*>\s?(.*)$", line)
        if blockquote:
            flush_paragraph()
            close_list()
            quote_lines: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*>\s?(.*)$", lines[index])
                if not match:
                    break
                quote_lines.append(match.group(1))
                index += 1
            output.append(f"<blockquote>{render_inline(' '.join(quote_lines))}</blockquote>")
            continue

        image_block = re.fullmatch(r"\s*!\[([^\]]*)\]\(([^)]+)\)\s*", line)
        if image_block:
            flush_paragraph()
            close_list()
            alt = html.escape(image_block.group(1).strip(), quote=True)
            src = rewrite_link(image_block.group(2))
            output.append(
                '<figure class="guide-figure">'
                f'<img class="guide-image" src="{html.escape(src, quote=True)}" alt="{alt}" loading="lazy">'
                f'<figcaption>{render_inline(image_block.group(1).strip())}</figcaption>'
                '</figure>'
            )
            index += 1
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            kind = "ul" if unordered else "ol"
            item = (unordered or ordered).group(1)
            flush_paragraph()
            if list_type != kind:
                close_list()
                list_type = kind
                output.append(f"<{kind}>")
            output.append(f"<li>{render_inline(item)}</li>")
            index += 1
            continue

        if re.fullmatch(r"\s*([-*_])(?:\s*\1){2,}\s*", line):
            flush_paragraph()
            close_list()
            output.append("<hr>")
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            index += 1
            continue

        paragraph.append(line.strip())
        index += 1

    flush_paragraph()
    close_list()
    return "\n".join(output), first_heading or "Omnix guide"


def page_links(current: Path) -> str:
    pages = [
        (DOCS / "index.html", "Docs home"),
        (DOCS / "README.html", "Overview"),
        (DOCS / "FEATURES.html", "Features"),
        (DOCS / "ARCHITECTURE.html", "Architecture"),
        (DOCS / "SETUP.html", "Setup"),
        (DOCS / "DEVELOPMENT.html", "Development"),
        (DOCS / "OPERATIONS.html", "Operations"),
        (DOCS / "HERMES_SIDECAR_SETUP.html", "Hermes"),
        (ROOT / "README.html", "Repository README"),
        (ROOT / "SPEC.html", "Platform spec"),
    ]
    links: list[str] = []
    for path, label in pages:
        href = Path(os.path.relpath(path, current.parent)).as_posix()
        links.append(f'<a href="{href}">{label}</a>')
    return "\n".join(links)


def wrap_page(source: Path, output_path: Path, body: str, title: str) -> str:
    css_href = "docs/guide.css" if output_path.parent == ROOT else "guide.css"
    home_href = "docs/index.html" if output_path.parent == ROOT else "index.html"
    source_label = "Repository guide" if source.parent == ROOT else "Omnix guide"
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <meta name="description" content="{safe_title} - Omnix documentation">
  <title>{safe_title} | Omnix Documentation</title>
  <link rel="stylesheet" href="{css_href}">
</head>
<body>
  <div class="guide-shell">
    <header class="guide-header">
      <a class="guide-brand" href="{home_href}"><span class="guide-mark" aria-hidden="true">O</span><span>Omnix Docs</span></a>
      <nav class="guide-nav" aria-label="Guide navigation">
        {page_links(output_path)}
      </nav>
    </header>
    <main class="guide-main">
      <div class="guide-meta"><span class="eyebrow">{source_label}</span><span class="pill">HTML-rendered reference</span></div>
      <article class="markdown-body">
        {body}
      </article>
    </main>
    <footer class="guide-footer">
      <a href="{home_href}">&larr; Back to documentation home</a>
      <span>Markdown is the source; this page is generated for browser reading.</span>
    </footer>
  </div>
  <script>
    document.querySelectorAll(".copy-code").forEach(button => {{
      button.addEventListener("click", async () => {{
        const code = button.parentElement.querySelector("code");
        const text = code ? code.textContent : "";
        let copied = false;
        try {{
          if (navigator.clipboard && navigator.clipboard.writeText) {{
            await Promise.race([
              navigator.clipboard.writeText(text).then(() => {{ copied = true; }}),
              new Promise(resolve => window.setTimeout(resolve, 500))
            ]);
          }}
        }} catch (_) {{}}
        if (!copied) {{
          const helper = document.createElement("textarea");
          helper.value = text;
          helper.setAttribute("readonly", "");
          helper.style.position = "fixed";
          helper.style.opacity = "0";
          document.body.appendChild(helper);
          helper.select();
          document.execCommand("copy");
          helper.remove();
        }}
        const label = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => {{ button.textContent = label; }}, 1200);
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    for source in GUIDE_SOURCES:
        if not source.exists():
            raise FileNotFoundError(source)
        body, title = render_markdown(source.read_text(encoding="utf-8"))
        output_path = source.with_suffix(".html")
        output_path.write_text(
            wrap_page(source, output_path, body, title),
            encoding="utf-8",
            newline="\n",
        )
        print(f"rendered {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
