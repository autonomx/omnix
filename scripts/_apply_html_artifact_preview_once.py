from pathlib import Path

path = Path("src/apps/web/src/features/chatbot/OmnixRunCard.tsx")
text = path.read_text(encoding="utf-8")

import_anchor = "import { omnixApiClient } from '../../api/client';\nimport { renderMarkdownHtml } from './markdownRenderer';\n"
import_replacement = "import { omnixApiClient } from '../../api/client';\nimport { HtmlArtifactPreviews } from './HtmlArtifactPreview';\nimport { renderMarkdownHtml } from './markdownRenderer';\n"
if text.count(import_anchor) != 1:
    raise RuntimeError("OmnixRunCard import anchor changed")
text = text.replace(import_anchor, import_replacement, 1)

jsx_anchor = """          {changedFiles.length ? (\n            <div className=\"assistant-runtime-changed-files\">\n"""
if text.count(jsx_anchor) != 1:
    raise RuntimeError("OmnixRunCard changed-files anchor changed")

preview_block = """          <HtmlArtifactPreviews runId={id} paths={changedFiles.map((file) => file.path)} />\n          {changedFiles.length ? (\n            <div className=\"assistant-runtime-changed-files\">\n"""
text = text.replace(jsx_anchor, preview_block, 1)
path.write_text(text, encoding="utf-8")
print("wired HtmlArtifactPreviews into OmnixRunCard")
