# Chat generative UI — security review (GUI-5.4 gate)

**Date:** 2026-10-18 · **Branch:** `generative-ui` · **Scope:** every change made for the [chat generative UI roadmap](OMNIX_CHAT_GENERATIVE_UI_ROADMAP.md), GUI-0 to GUI-6.

The roadmap requires a security review before Phase 5 is marked done. This one was done inline against the branch diff. It checks each place where model output, retrieved content or a browser request crosses into rendering, storage or authority.

## Findings

| Area | What was checked | Result |
|---|---|---|
| Script injection (Markdown) | GFM tables, task lists and alerts in `renderMarkdownHtml` escape every source string. Cell, item and alert text go through `renderInline`, which escapes it. Alignment is a fixed `data-align` value, never model text. | No issue. Tests escape HTML in every new construct (`markdownRenderer.test.ts`). |
| Script injection (blocks) | Block components render model strings as React text nodes. The only HTML injection is Markdown spans through the escaping renderer. Links are built only from `http`, `https` and `mailto` URLs without spaces or quotes, and open with `rel="noopener noreferrer"`. Nothing the model writes is executed. | No issue. Source and provenance links reject `javascript:` (test). The server also drops unsafe source URLs (`safe_url`). |
| Untrusted retrieved content | Bound values (`source:<n>`, `context:<n>`) come from this turn's context items, which are untrusted web data. They are frozen as text with their source named, and their URLs pass the same link rules. | No issue. Provenance shows these values as "Sourced", naming the source. |
| Widget authority | A `choices` button sends exactly its visible label through the normal send path. A `form` only fills the composer. `ui_action` is validated at admission (`generative_ui/actions.py`) against the source reply in the same session: the block must exist, the option label must equal the message, and values must match their fields. Anything else is stripped and the text becomes an ordinary message. Nothing reads `ui_action` to take an action; it only rebuilds widget state. A spec that tries to add a separate message field is refused at compile time. | No issue. Forged block ids, cross-session sources, label/content mismatches, out-of-range values and all four send routes are tested (`test_generative_ui_actions.py`). |
| Request bounds | `ChatUiAction` limits ids, `option_index` (0–5), the number of values (8), key length (32) and string values (200 chars) before validation. | Hardened during this review: string values were previously bounded only after validation. |
| Trading authority | `price_chart` reaches trading only through `CHAT_MARKET_SYMBOLS` (a read-only catalog lookup) and the web's `fetchChatPriceBars` (one `GET /api/trading/bars`). Boundary tests fail on any import of order, alert, watchlist, strategy, paper or broker paths, in Python and on the web. | No issue. |
| Denial of service | Fence scanning and JSON repair run in linear time (a 100 KB reply is tested). There are at most 8 blocks, 32 KB per block and 128 KB per payload; long series are downsampled; most block strings are truncated. The symbol lookup runs in a daemon thread capped at 3 s, so a stalled provider cannot hold the reply. | Accepted. A provider that hangs leaves one parked daemon thread per affected reply. |
| History leakage to models | Turns where UI is disabled (live voice, character, agent, deep research, memory commands, models not enabled, setting off) see replies as `ui.text`. That covers in-memory and PostgreSQL history search and the legacy JSON store. | No issue (`test_projection.py`, `test_prompting.py`). |
| Setting route | `POST /api/chat/sessions/{id}/rich-replies` uses the same tenant-scoped store as the research-mode route. An unknown session returns 404 and an unknown value returns 422. | No issue. |
| Development page | The fixture gallery is registered only when `import.meta.env.DEV`. A production build contains neither the page nor the fixtures (verified against `web/dist`). | No issue. |

No open findings.
