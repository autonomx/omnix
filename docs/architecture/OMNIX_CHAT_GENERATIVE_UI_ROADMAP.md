# Omnix Chat Generative UI — Implementation Roadmap

**Status:** Proposed (revision 2, after code review)
**Date:** 2026-10-11
**Base:** `main` at `cbba27a9fea98e07c6601a3a1dc7cdfc3c5d291b`
**Surfaces:** assistant chat (`web/src/features/assistant/chat`), chat generation and admission (`src/app/platform/chat`)
**Work-package prefix:** `GUI-`
**Reference:** Thesys, "How ChatGPT's intelligent UI works" — https://www.openui.com/blog/how-chatgpt-intelligent-ui-works (reverse-engineered from ChatGPT's web client, October 2026)

## 1. Executive decision

Omnix chat replies should be able to show what prose can't: headline numbers, charts, pinned market data, citation chips and suggested next steps. Everything Markdown already expresses stays Markdown.

Omnix adopts the shape of ChatGPT's design: a fixed component catalog, server-side validation, a text fallback, data filled in by the server rather than retyped by the model, and widget actions limited to the user's own messages. It does **not** adopt ChatGPT's model-written JavaScript ("DIL" compiled into a program and run in a locked-down worker):

1. **Markdown first.** GFM tables, task lists and GitHub alerts are rendered properly. These cost no prompt tokens and have no JSON failure mode. They work on every provider and read fine in history and speech.
2. **Declarative blocks only where Markdown can't reach.** The model writes JSON component specs in fenced blocks. Omnix code validates them against a typed catalog and React renders them. Nothing the model writes is executed in the Omnix page.
3. **The server is authoritative.** Parsing, validation, normalization, binding and the text and speech projections happen once, deterministically, before the reply is committed. The result is stored on the message. The browser re-validates as defence in depth.
4. **Graceful degradation is mandatory.** Every block has a text fallback. An unknown, malformed or oversized block becomes text, never an error or a blank space.
5. **No authority is widened, directly or by proxy.** A widget never executes anything, and it never sends words the user didn't see. A button sends exactly its label, and a form fills the composer for the user to send.

The reason for rejecting the program model: the article's captures show expression errors failing silently (a dashboard's metric switch turned $6,930 into $256,410). ChatGPT also has to recompile partial programs during streaming. The typed web chat is job-based. The streaming routes (live voice and API clients) need no UI while streaming, because Omnix compiles only the finished reply. Most of ChatGPT's runtime machinery therefore buys Omnix nothing. The value is in the catalog, validation and binding.

---

## 2. Reference design: what we adopt and what we reject

| ChatGPT mechanism | Omnix decision | Notes |
|---|---|---|
| Model writes Markdown + JSX-like tags + JS (DIL) | **Replace** with Markdown + fenced JSON blocks (` ```omnix-ui `) | Provider-agnostic: no native tool calling needed |
| Native `table`, `text`, `box` and similar components | **Replace** with GFM Markdown (tables, task lists, alerts) | GUI-0.3 |
| Server compiles each partial response | **Replace** with one deterministic compile of the finished reply | Shared by every save path (GUI-1.4) |
| Catalog of ~70 native components | **Adopt**, starting with 5 blocks | `stats`, `chart`, `price_chart`, `sources`, `choices` (+ `form` prefill) |
| Validation drops bad props and records diagnostics | **Adopt**; diagnostics are stored and measured per provider/model | |
| `fallbackMarkdown` | **Adopt** as two projections: `text` (copy, memory, search, summaries) and `speech` (audio) | §6.4 |
| Locked-down worker running model JS | **Reject** | |
| Reconciler ops with function IDs | **Reject** | React renders validated specs |
| Server-resolved components and tool-result references | **Adopt** as `{"bind": …}` references and server-validated queries | GUI-4 |
| `GenUI.issueNewTurn` | **Adopt, narrowed**: the button sends exactly its label; forms prefill the composer | GUI-5 |
| AppBlock (self-contained HTML app) | **Deferred** until a concrete Omnix use case exists | §9 "Later" |
| Design tokens | **Adopt**: props take tokens, never raw CSS | |

ChatGPT limitations we design around:
- **Model doesn't see UI state.** Choice and form messages are ordinary, readable user text.
- **State lost on reload.** Submitted state is rebuilt from the follow-up message (GUI-5.3).
- **Regenerate instead of edit.** Block supersession is on the "Later" list.

---

## 3. Current Omnix baseline

Facts verified on the base commit.

### Save paths
There are two. Both end in `_commit_chat_reply` ([generation_jobs.py](../../src/app/platform/chat/generation_jobs.py)), which calls `chat_store.complete_streamed_reply` inside the job's completion transaction and `chat_job_commit_lock`.

- **Job path (typed web chat):**
  - `POST /api/chat/sessions/{id}/messages` and `POST /api/assistant/context/chat/sessions/{id}/messages` lead to `_run_chat_generation_job`, then `_commit_chat_reply(..., before_commit=...)`.
  - `before_commit` runs **inside** the lock and transaction ([generation_jobs.py:842-850](../../src/app/platform/chat/generation_jobs.py#L842-L850)).
  - The client tracks the job ([useChatJob.ts](../../web/src/features/assistant/chat/useChatJob.ts)) and refetches the session when it ends.
- **Stream path (live voice, API clients):**
  - `POST /api/chat/sessions/{id}/messages/stream` ([core_chat_routes.py:150](../../src/app/composition/gateway/kernel_routes/core_chat_routes.py#L150)) and `POST /api/assistant/context/chat/sessions/{id}/messages/stream` lead to `stream_chat_turn` ([admission.py:134](../../src/app/platform/chat/admission.py#L134)).
  - That emits `text_chunk` events and then commits through `_commit_chat_reply` with **no** `before_commit` ([admission.py:190](../../src/app/platform/chat/admission.py#L190), [admission.py:204](../../src/app/platform/chat/admission.py#L204)). An `annotate_reply(metadata)` hook exists and is used by the assistant-context route.
  - In the web app only `useStreamedVoiceTurns.ts` uses these routes. It sends chunks to speech **before** anything is committed.

At compile time the only message id available is the **user** message's (`reply_to_message_id`). The assistant message is created by `complete_streamed_reply`.

### Other writers of assistant replies
These are outside the two paths above (Appendix A):
- `character_store.py`: character greetings and replies;
- `prompt_store.py`: memory commands;
- `research/jobs.py:258`: research reports.

### Message contract
`ChatMessage` ([conversation/contracts.py](../../src/app/conversation/contracts.py)) is `id, role, content, created_at, metadata: dict[str, Any]`. `content` is `TEXT` with no length cap found. Storing compiled UI in `metadata` needs no migration.

### Send contract
`SendChatMessageRequest` ([platform/chat/models.py:221](../../src/app/platform/chat/models.py#L221)) has no field for widget actions. Any addition regenerates OpenAPI and the web contracts and affects all four send routes.

### Settings
- **There is no server-side assistant settings document.** `AssistantSettings` is client-only and persisted to `localStorage` ([chatbotWorkspaceModel.ts:271](../../web/src/features/assistant/chat/chatbotWorkspaceModel.ts#L271)). It reaches the server only per request, the way `coding_approval_policy` rides on `SendChatMessageRequest`. A flag kept there would make what the model sees in history depend on which browser the user is in.
- **Per-session overrides need no migration.** `research_mode_override` lives in the session's `settings` JSONB: written by `_settings` ([chat_store.py:574](../../src/app/platform/chat/persistence/chat_store.py#L574)) and read back by `_summary_fields` ([chat_store.py:593](../../src/app/platform/chat/persistence/chat_store.py#L593)). Its set-route, `POST /api/chat/sessions/{id}/research-mode` ([research_mode_routes.py](../../src/app/platform/chat/research_mode_routes.py)), is the template for `rich_replies` (GUI-3.1).

### Projection seam
`project_message_content(message, MessageContentPurpose)` ([platform/chat/models.py](../../src/app/platform/chat/models.py)) has purposes `MODEL, MEMORY, SUMMARY, SEARCH, TRANSCRIPT, AUDIT, EXPORT`. Today it handles interrupted voice replies. It is used by `compaction.py`, `history_search.py` and `prompt_assembly.py`.

### Renderer
[markdownRenderer.ts](../../web/src/features/assistant/chat/markdownRenderer.ts) is a hand-written, escaping subset: headings, flat lists, quotes, fences, rules, links, citations. **No tables, task lists or alerts.** [ChatMessageItem.tsx](../../web/src/features/assistant/chat/ChatMessageItem.tsx) injects its HTML string.

### Frontend readers of raw content
- Copy and PCM stream (`useChatMessageActions.ts:51`, `:62`).
- Play (`ChatMessageItem.tsx`).
- Streamed voice turns (`useStreamedVoiceTurns.ts:85`).
- `data-raw-content`, read by research-report download ([researchProgressController.ts:187](../../web/src/features/assistant/chat/researchProgressController.ts#L187)). **It must stay raw.**

### JSON parsing
`decode_json_object` ([providers/structured/parsing.py:42](../../src/app/providers/structured/parsing.py#L42)) is deliberately strict: it strips fences, extracts the `{…}` span, and does no semantic repair. **It must not be loosened.** Tolerant parsing for UI blocks lives in `generative_ui/parser.py`.

### Assistant tools
Execution goes through proposals and a separate approve step. The ledger (`assistant_tools/ledger.py`) records only `result_summary: str`. There are no structured, same-turn tool results to bind to.

### Dependencies and theme
- `zod` ^4.2 and `lightweight-charts` ^5.1 (the trading wrapper is `web/src/features/trading/chart/chartAdapter.ts`).
- Theme tokens are the `--omnix-*` variables in `web/src/theme-presets.css`.

### Gates
CI runs no web tests: Vitest runs locally (DECISIONS 2026-10-10 "CI"), and roadmap slices are verified locally.

---

## 4. Invariants

These hold across every phase and are enforced by tests:

1. **`content` is the model's raw output and is never rewritten.** Compiled UI lives in `metadata.ui`. Audit and export see raw text, and `data-raw-content` stays raw.
2. **The compile is pure, versioned, and runs outside the commit lock.** `compile_chat_ui(content, scope)` is deterministic for a given `compiler_version` and scope. Any I/O (binding resolution, symbol validation) happens before `_commit_chat_reply`. Only the finished payload is attached inside the transaction.
3. **Compiling is decoupled from enablement.** Every save path compiles whenever the reply contains an `omnix-ui` fence, and compiling returns `None` otherwise, so ordinary replies are unchanged. Settings control prompting, not compiling.
4. **Only validated specs render.** The client renders `metadata.ui` and never parses fences out of `content`. A message without `metadata.ui` renders exactly as today.
5. **The model sees raw block markup only when UI is enabled for the current turn.** Otherwise prior replies are projected to `ui.text`. Live voice, character mode, a weaker model chosen mid-session, or a disabled setting therefore never learn the fence format from history.
6. **Every block has a text projection and a speech projection.** Copy, memory, search, summaries and the transcript use `text`. Audio uses `speech`. Nothing ever reads JSON aloud.
7. **Widgets act only through the user, visibly.**
   - A `choices` button sends exactly the text it displays.
   - A `form` fills the composer, and the user sends it.
   - Widgets never call tools, approve proposals or touch trading.
   - A `ui_action` reference is validated server-side and carries no authority.
8. **Numbers can be traced.** Bound values are marked as sourced. Model-authored numeric data in `stats` and `chart` is marked as model-generated.
9. **Interrupted replies get no UI.** If `delivery_status == "interrupted"`, the message renders its delivered text only.
10. **Size limits are fixed** (§7.3). Over-limit blocks degrade to text with a diagnostic.
11. **Off means unchanged.** With prompting disabled and no fences in replies, prompts, storage and rendering are byte-for-byte unchanged.

---

## 5. Goals and non-goals

### V1 goals
- GFM tables, task lists and GitHub alerts in the Markdown renderer (M0).
- A typed catalog with one source of truth (Pydantic), mirrored in zod and checked by shared golden fixtures.
- One compile helper used by both save paths. It produces segments, normalized blocks, `text`, `speech` and diagnostics.
- Projection wired into every consumer, frontend and backend, including the turn-aware `MODEL` rule (invariant 5).
- Components: `stats`, `chart`, `price_chart` (pinned, read-only market data), `sources`, `choices`, and `form` (composer prefill).
- Catalog prompting gated by a setting and per-model capability. Every model starts at `none` and is enabled by evaluation only.
- Per-provider/model quality measurement with multiple samples per prompt.

### Non-goals
- Executing model-written code anywhere (HTML apps are deferred, §9).
- Rendering blocks while a reply streams.
- Widgets that call tools, approve proposals, send unseen text, or touch trading authority.
- Re-implementing in JSON what Markdown already expresses (`table`, `checklist`, `callout`, `steps`, `keyvalue`).
- Arbitrary external images or fonts.
- Rich UI in live voice output, character mode, agent mode, deep research or memory commands.

---

## 6. Architecture

### 6.1 Data flow

    provider reply (raw text, possibly with ```omnix-ui fences)
            |
            v
    finalize_reply_ui(content, scope)          <- one helper, called by BOTH save paths,
            | parse fences (tolerant JSON)        BEFORE _commit_chat_reply (no lock held)
            | validate against catalog
            | normalize (ids, tokens, limits)
            | resolve bindings / validate queries (I/O allowed here)
            | build segments, text, speech, diagnostics
            v
    _commit_chat_reply(content, metadata + {"ui": payload})
            |   job path:    attached alongside existing before_commit metadata
            |   stream path: attached before the commit call in stream_chat_turn
            v
    session -> ChatMessage.metadata.ui
            |
            v
    ChatMessageItem -> ChatUiRenderer
            |  markdown span -> renderMarkdownHtml (escaping, unchanged)
            |  block         -> zod re-validate -> React component (invalid -> text)
            v
    choices click -> send label as user message (+ ui_action ref)
    form submit   -> fill composer; user sends

Compile failures (exceptions) are caught in `finalize_reply_ui`, which records `metadata["ui_error"]`. The reply commits as plain text, and no turn ever fails because of UI.

### 6.2 Wire format (what the model writes)

One block per fence. The info string is exactly `omnix-ui`, and the body is a single JSON object:

    Revenue held steady this quarter.

    ```omnix-ui
    {"type": "stats", "items": [
      {"label": "Revenue", "value": "$6,930", "delta": "+4.1%", "trend": "up"},
      {"label": "Orders", "value": "212"}
    ]}
    ```

Rules:
- `type` is required. `id` is optional; the compiler assigns `b1`, `b2`, … when it's missing or duplicated. `v` defaults to `1`.
- **Tolerant parsing** lives in `generative_ui/parser.py`, not in the strict structured-output parser. It repairs trailing commas, smart quotes and single-quoted keys, and records a `json_repaired` diagnostic when it does.
- Any other info string (` ```json `, ` ```python `) stays a code block.

### 6.3 Stored shape (`metadata.ui`)

    {
      "version": 1,
      "compiler_version": "gui-compiler-1",
      "compiled_at": "2026-10-11T14:03:22Z",   // pins market-data queries (as_of)
      "segments": [
        {"kind": "markdown", "start": 0, "end": 34},   // offsets into content
        {"kind": "block", "id": "b1"},
        {"kind": "text", "text": "…fallback for a dropped block…"}
      ],
      "blocks": {"b1": {"type": "stats", "items": [...], "provenance": "model"}},
      "text":   "Revenue held steady this quarter.\n\nRevenue: $6,930 (+4.1%). Orders: 212.",
      "speech": "Revenue held steady this quarter. Two headline figures: revenue six thousand nine hundred thirty dollars, up four percent; and 212 orders.",
      "diagnostics": [{"block": "b1", "code": "unknown_prop", "path": "items[0].color", "severity": "dropped"}]
    }

- Markdown segments are `[start, end)` offsets into the stored `content`, so prose isn't duplicated. The fence text itself is never inside a Markdown span.
- A dropped block becomes a `text` segment holding its fallback (from the valid part of the spec when possible, otherwise a short notice). A diagnostic records why.
- `compiled_at` is set by the compile, which happens before the assistant message exists. It is the as-of time for `price_chart`.
- The payload is capped at 128 KB. Over the cap, the largest blocks degrade to text first.

### 6.4 Projections

`project_message_content` gains one rule, applied before the existing interrupted-delivery rule, plus a new purpose:

| Purpose | With `metadata.ui` |
|---|---|
| `MODEL_RICH` (new; used when UI is enabled for the current turn) | raw `content` |
| `MODEL` (UI disabled for the current turn) | `ui.text` |
| `MEMORY`, `SUMMARY`, `SEARCH`, `TRANSCRIPT` | `ui.text` |
| `AUDIT`, `EXPORT` | raw `content` |

- `build_prompt_assembly` picks `MODEL_RICH` or `MODEL` from the turn's enablement decision (GUI-3.1).
- On the client, `chatMessageText(message)` returns `ui.text ?? content`, used for copy. `chatMessageSpeech(message)` returns `ui.speech ?? content`, used for play, PCM streaming and streamed voice.
- `data-raw-content` stays raw.

Each component provides both `to_text()` (complete and copyable; a table of stats keeps every value) and `to_speech()` (a short summary: "a chart of AAPL's daily close over six months, ending at 231 dollars").

### 6.5 Module layout

Backend, new package `src/app/platform/chat/generative_ui/`:

| Module | Responsibility |
|---|---|
| `catalog.py` | Pydantic models per block; `CATALOG`; `to_text()` / `to_speech()`; limits |
| `parser.py` | Fence scanner (same grammar as the client renderer); tolerant JSON |
| `compiler.py` | `compile_chat_ui(content, scope)`: pure; ids, normalization, segments, projections, diagnostics |
| `finalize.py` | `finalize_reply_ui(content, scope)`: runs resolvers, calls the compiler, catches failures; used by both save paths |
| `bindings.py` | Binding scope and resolvers (GUI-4) |
| `prompting.py` | Catalog instruction generated from `CATALOG`; `ui_enabled_for_turn` policy |
| `actions.py` | `ui_action` validation (GUI-5) |

Frontend, new folder `web/src/features/assistant/chat/generative-ui/`:
- `schema.ts`;
- `ChatUiRenderer.tsx`, with an error boundary per block;
- `components/*.tsx`;
- `ChatGenerativeUi.css`, the single CSS owner;
- `chatMessageProjection.ts`, holding `chatMessageText` and `chatMessageSpeech`;
- `uiActions.ts`.

Shared golden fixtures live in `resources/chat/generative_ui/fixtures/*.json` and are read by both pytest and Vitest.

---

## 7. What renders where

### 7.1 Markdown (GUI-0.3, no protocol)

| Syntax | Renders as |
|---|---|
| GFM pipe tables with alignment | Table, scrolling horizontally in its own container |
| Task lists `- [ ]` / `- [x]` | Read-only checkboxes (no state to lose) |
| GitHub alerts `> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]` | Toned callouts |
| Ordered lists | Already supported; these cover `steps` |

### 7.2 V1 blocks

| Type | Purpose | Key props | `to_text()` | `to_speech()` |
|---|---|---|---|---|
| `stats` | 1–6 headline numbers | `items[{label, value, delta?, trend?: up\|down\|flat, hint?}]` | `"Label: value (delta)."` per item | Count plus the first two items |
| `chart` | Line, area or bar chart of model-supplied or bound data | `kind: line\|area\|bar`, `x: {type: time\|category, label?}`, `series[{name, points[[x, y]]}]`, `y: {label?, format?}`, `title?` | Title, then min/max/last per series | Title plus the last value of the main series |
| `price_chart` | Pinned, read-only market data (GUI-4.2) | `symbol`, `interval`, `range`, `title?` | `"AAPL daily, 6M to <as_of>"` | Same, spoken |
| `sources` | Citation chips (GUI-4.1) | `refs[{bind}]` | Source titles and URLs | "n sources" |
| `choices` | Suggested next messages (GUI-5.1) | `prompt?`, `options[{label}]` (2–6; the label *is* the message) | `"Options: a; b; c"` | Same |
| `form` | Parameter form that prefills the composer (GUI-5.2) | `fields[{name, kind: select\|slider\|text\|toggle, …}]`, `template` | Field summary | "a form with n fields" |

Charts: time-series `line`/`area` use `lightweight-charts` through a small chat-owned adapter, with no import of trading feature internals. Categorical `bar` uses a small SVG component, so no new dependency is added. Every chart has a "Show data" toggle that renders a table.

Deferred until evaluation shows demand: `tabs`, `timeline`, `comparison`, `image` (bound assets only).

### 7.3 Limits

| Limit | Value | On breach |
|---|---|---|
| Blocks per message | 8 | Extra blocks become text |
| Serialized block | 32 KB | Block becomes text |
| `metadata.ui` total | 128 KB | Largest blocks become text first |
| Chart | 6 series × 2,000 points | Downsampled (LTTB) with diagnostic |
| `choices` label | 160 chars | Option dropped |
| `form` template | 500 chars; values substituted as plain text | Block becomes text |
| Strings | 2,000 chars per field; labels 120 | Truncated |

### 7.4 Styling contract

- Props take tokens (`tone`, `size: sm|md|lg`, `emphasis`), never raw CSS, color or class names.
- Components read `--omnix-*` variables, so every theme preset and light/dark mode works without per-component overrides.
- Layout is single-column at ≤ 480 px, with no page-level horizontal scroll.
- `prefers-reduced-motion` disables entry animations.

---

## 8. Phases and work packages

Each work package lists scope, tasks, tests and acceptance criteria. A package is done when its acceptance criteria pass on local gates and its PROGRESS row is written (§10).

### Phase 0 — Decisions, inventory and Markdown (M0)

#### GUI-0.1 Decision record
- Record decisions D-GUI-1 to D-GUI-7 in [DECISIONS.md](../roadmap/DECISIONS.md):
  - **D-GUI-1:** declarative blocks, with no model code anywhere.
  - **D-GUI-2:** fenced JSON wire format, with a tolerant parser separate from structured outputs.
  - **D-GUI-3:** `metadata.ui` with offsets, and no migration.
  - **D-GUI-4:** projections, including turn-aware `MODEL` / `MODEL_RICH` and a separate `speech`.
  - **D-GUI-5:** compile on every save path whenever a fence is present, outside the commit lock.
  - **D-GUI-6:** widgets act only through visible user text (label equals message; forms prefill).
  - **D-GUI-7:** `rich_replies` is a per-session setting in the session `settings` JSONB, server-side and durable.
- **Acceptance:** decisions recorded, and the open questions in §11 have owners.

#### GUI-0.2 Consumer and writer inventory
- Complete Appendix A. Classify every reader of assistant `content` by purpose, and every writer of assistant replies as "compiles" or "excluded, with reason".
- Confirm the read-only bars endpoint used by the trading chart (GUI-4.2).
- **Acceptance:** Appendix A has no "unknown" rows.

#### GUI-0.3 Markdown: tables, task lists, alerts
- Extend `renderMarkdownHtml` with:
  - GFM tables: header, delimiter with alignment, body, inline Markdown in cells, escaped pipes, ragged rows;
  - task-list items as disabled checkboxes;
  - GitHub alert blockquotes as toned callouts;
  - `isBlockStart` detection for each.
- CSS goes in the existing chat message styles. Each renders correctly in every theme preset at 375 px.
- **Tests (`markdownRenderer.test.ts`):** each construct; a table inside a quote; a non-table line containing pipes; an alert with nested lists; and escaping of HTML in every new construct.
- **Acceptance:** model-emitted tables, task lists and alerts render properly. Existing renderer tests are unchanged. This ships on its own.

### Phase 1 — Contract, compile and projection

#### GUI-1.1 Catalog models
- Add `catalog.py` with the six V1 blocks (§7.2) as Pydantic models (`extra="ignore"` with dropped keys reported, strict literals), each with `to_text()`, `to_speech()` and limits.
- Add `ChatUiPayload`, `ChatUiSegment` and `ChatUiDiagnostic`.
- **Tests:** `src/tests/unit/chat/generative_ui/test_catalog.py` covers a valid example per block, each limit, unknown props, bad literals, and both projections. Every block has golden fixtures.

#### GUI-1.2 Parser
- Add `parser.py`. The fence grammar matches the client renderer (`^\s{0,3}```` + info string). Unclosed fences become text with `unclosed_fence`. Tolerant JSON is implemented here, and `providers/structured/parsing.py` is untouched.
- **Tests:** fences in list items, CRLF input, nested backticks, `omnix-ui` in inline code (not a block), each repair case, and a 100 KB input in linear time.

#### GUI-1.3 Compiler
- Add `compile_chat_ui(content, scope)`: pure, returning `None` when no `omnix-ui` fence is present. It builds offset segments, `text`, `speech`, diagnostics and `compiled_at` (taken from the scope's clock, so tests are deterministic), and enforces the cap.
- **Tests:** golden fixtures shared with Vitest; byte-identical output for identical input and clock; an all-invalid reply (readable `text` and `speech`); an interrupted reply (`None`); offsets reproduce the prose exactly.

#### GUI-1.4 One helper, both save paths
- Add `finalize_reply_ui(content, scope) -> dict | None` in `finalize.py`. It runs any resolvers (none until GUI-4), calls the compiler, and catches exceptions into `ui_error`.
- **Job path:** call it in `_run_chat_generation_job` **before** `_commit_chat_reply`, and merge the result into `metadata`. Don't call it from `before_commit`, which holds `chat_job_commit_lock`.
- **Stream path:** call it in `stream_chat_turn` on `complete` (and on the uncommitted fallback) before `_commit_chat_reply`, after `annotate_reply`. This covers both `/messages/stream` routes.
- Record in Appendix A that the other writers are excluded: character greetings and replies, memory commands, research reports. Reports have their own renderer, revisited under "Later".
- **Tests:**
  - **Integration (`src/tests/chat/`):** job path and stream path each store `metadata.ui` for a fenced reply;
  - a compiler exception still commits the reply as plain text, with `ui_error`;
  - a reply without fences leaves metadata unchanged on both paths;
  - a spy asserts the compile runs while `chat_job_commit_lock` is not held.

#### GUI-1.5 Projections
- Add `MessageContentPurpose.MODEL_RICH` and the rules in §6.4. Route the GUI-0.2 readers through `project_message_content`.
- In `build_prompt_assembly`, use `MODEL` until GUI-3.1 supplies the enablement decision. Until then the model never sees raw block markup in history (invariant 5).
- **Tests:**
  - a purpose matrix with and without `ui`;
  - the interaction with interrupted delivery;
  - prompt assembly with a prior fenced reply contains `ui.text` and not the fence;
  - memory extraction of a block reply sees only prose and `to_text()` output.
- **Acceptance (Phase 1):** fenced replies are compiled on every save path, outside the lock. Every backend consumer sees text, and existing chat tests pass unchanged.

### Phase 2 — Client renderer

#### GUI-2.1 Schema and parsing
- Add `schema.ts`, with zod mirrors and `parseChatUi(metadata, content)`. Markdown spans are sliced from `content` by offset, and a block that fails client validation becomes its text.
- **Tests:** Vitest runs the shared golden fixtures. An offset outside `content` makes the whole message fall back to plain Markdown.

#### GUI-2.2 Message integration
- `ChatMessageItem` renders `ChatUiRenderer` when `parseChatUi` returns a payload. Markdown spans go through `renderMarkdownHtml` with citations. `handleResearchReportAction` stays attached, and `data-raw-content` and `data-omnix-message-content` stay on the wrapper with raw content.
- Each block has an error boundary that falls back to its text.
- **Tests (`ChatbotWorkspace.render.test.tsx`):**
  - a mixed reply;
  - a reply without `ui` gives a DOM identical to today;
  - a component that throws falls back to text;
  - memoization still re-renders only the changed message.

#### GUI-2.3 `stats` and `chart`
- `chart` uses `lightweight-charts` (lazy-loaded, behind a chat-owned adapter) for time series and SVG for categorical bars, with a "Show data" table toggle.
- Model-authored numbers show the "AI-generated values" marker.
- **Tests:** rendering, empty and edge data, downsampled series, keyboard access, theme variables only.

#### GUI-2.4 Projections on the client
- Add `chatMessageText` and `chatMessageSpeech`. Copy uses text. Play, PCM streaming and streamed voice turns use speech.
- **Tests:** copying a block reply gives `ui.text`; audio gets `ui.speech`; a message without `ui` behaves as today.

#### GUI-2.5 Visual QA
- Add a dev-only fixture route that renders every golden fixture in each theme preset, light and dark, at 375 px and 1280 px.
- **Acceptance (Phase 2):** stored block replies render as components everywhere. Copy never contains JSON, and audio never reads JSON or tables.

### Phase 3 — Prompting, enablement and evaluation

#### GUI-3.1 Per-session setting and enablement policy
- **Session setting.** Add `ChatSessionSummary.rich_replies: Literal["off", "on"] | None` (`None` means the default, off).
  - It is stored in the session's `settings` JSONB, serialized in `_settings` and read in `_summary_fields` in `persistence/chat_store.py`, exactly like `research_mode_override`. There is no migration.
  - The decision is server-side and durable across turns, because invariant 5 and GUI-5.4's `ui_action` validation both depend on it.
- **Set-route.** Add `POST /api/chat/sessions/{session_id}/rich-replies`, mirroring `research_mode_routes.py`. Regenerate OpenAPI and the web contracts in this package.
- **Model capability.** Add `rich_ui: none | basic | full` in the provider model catalog. **Every model starts at `none`.** GUI-3.3 sets values from evaluation results.
- **Policy.** Add `ui_enabled_for_turn(session, request, provider, model)`. It checks, in order:
  - `session.rich_replies == "on"`;
  - the model's capability is not `none`;
  - the turn is not one of the excluded modes: live voice turns on the stream routes, `interaction_mode == "character"`, agent mode, deep research, memory commands.
- `build_prompt_assembly` uses this decision to choose `MODEL_RICH` or `MODEL` for history (invariant 5).
- **UI.** The toggle sits in the assistant settings panel but writes to the current session. A per-browser default for new sessions is a later nice-to-have, not V1.
- **Tests:**
  - setting round-trip through the PostgreSQL store, and an unset value reading as `None`;
  - the route sets and clears the value, and rejects an unknown session;
  - a policy matrix (session flag × capability × mode);
  - with the policy false, prompts are byte-identical to today, including when history contains fenced replies.

#### GUI-3.2 Catalog instructions
- `prompting.py` generates a compact instruction (target ≤ 450 tokens) from `CATALOG`, covering:
  - **Prefer Markdown** for tables, lists, task lists and alerts.
  - **Use blocks only** for headline numbers, charts, market data, sources and suggested next steps.
  - The fence format and each block's shape in one line.
  - One example.
- `basic` gets `stats` and `chart` only.
- Append it to `system_instructions` only when enabled, and account for it in the context budget.
- **Tests:** a snapshot of the generated text, the budget accounting, and absence when disabled.

#### GUI-3.3 Evaluation harness
- **Prompt set:** about 40 prompts across data, comparison, how-to, chit-chat and trading-research styles, labelled "should use a block", "should use Markdown only" or "plain".
- **Samples:** 5 per prompt per model, so about 200 samples per model and about 125 in the "should use a block" class.
- **Metrics per model:**
  - valid-block rate, with a 95% Wilson interval;
  - diagnostics by code;
  - precision and recall for block usage;
  - leakage (fences on prompts labelled plain);
  - added tokens and latency.
- **Gate for `full`:**
  - the Wilson lower bound of the valid-block rate is ≥ 93%;
  - precision is ≥ 80%;
  - leakage is ≤ 5%.
- **Gate for `basic`:** the same, measured on the `basic` subset.
- The harness lives in `src/tests/` behind an explicit marker, excluded from default runs. Results go to `docs/roadmap/` as a dated report, and capability values are set only from such a report.

#### GUI-3.4 Telemetry
- Record block counts and diagnostic codes per reply in `provider_metrics.py`. `ChatResponseMetricsRow` shows "n blocks · m dropped" when diagnostics exist.
- **Acceptance (Phase 3):** rich replies are on only for models that passed the gate. All others are unchanged, including what they see in history.

### Phase 4 — Data: sources and pinned market data

#### GUI-4.1 Binding scope and `sources`
- The binding scope is built per turn from data the turn already has:
  - `source:<n>`: research citations;
  - `context:<id>`: `context_items` / `context_sources`.
- There are no `tool:` bindings. The ledger holds only `result_summary` text, and approved executions can land in a later turn. Revisit if tools gain structured results.
- `{"bind": "source:2.title"}` resolves at compile time and freezes the value with `provenance: "bound"`. An unresolvable binding drops the field (or the block, if the field was required) with `unresolved_binding`.
- `sources` renders citation chips using the existing link rules (http, https, mailto; `rel="noopener noreferrer"`).
- **Tests:** each resolver, a missing reference, type mismatch, and a reference outside the turn's scope.

#### GUI-4.2 `price_chart`
- `{"type": "price_chart", "symbol": "AAPL", "interval": "1d", "range": "6M"}` is a query.
- `finalize_reply_ui` validates the symbol and interval against the market-data catalog **before** the commit, with no lock held. `as_of` is `ui.compiled_at`.
- The client fetches bars through the existing read-only bars endpoint (GUI-0.2) with `end = as_of`, so the chart shows what was true when the answer was written. "Open in chart" navigates to the trading chart.
- **Read-only by construction:** `generative-ui/` imports only the read-only market-data client. A test fails if it imports any order, alert, watchlist or strategy write path.
- **Tests:** an unknown symbol degrades to text; `as_of` pinning; a symbol-validation timeout degrades to text without delaying the commit beyond the routing deadline; the import-boundary test.

#### GUI-4.3 Provenance display
- Bound values show a "sourced" affordance whose popover names the source. Model-authored numeric data shows "AI-generated values".
- **Acceptance (Phase 4):** sourced facts and prices come from data and are visibly marked. The market-data component cannot reach any trading write path.

### Phase 5 — Interactivity, visible and user-sent

#### GUI-5.1 `choices`
- Each option's `label` is the exact text sent. There is no separate message field, and the server rejects specs that try to add one.
- Clicking sends the label through the normal send path, with a `ui_action` reference.
- Only the latest assistant message's choices are active. Older ones render disabled, with the chosen option highlighted.
- **Tests:** what is shown equals what is sent; disabling; keyboard and screen-reader labels.

#### GUI-5.2 `form` (composer prefill)
- Field kinds:
  - `select` (≤ 20 options);
  - `slider` (min/max/step/unit);
  - `text` (≤ 200 chars);
  - `toggle`.
- Submitting fills `template` with the field values (plain-text substitution) and puts the result **in the composer**. The user reviews it and presses Send. The resulting message carries `ui_action` with the values.
- **Tests:** template filling with braces in values; the composer receives the text without sending; required fields.

#### GUI-5.3 State persistence
- A `choices` or `form` block takes its submitted state from the latest user message whose `ui_action` references it. A reload shows what was chosen, with no new storage.

#### GUI-5.4 Contract and server validation
- Add `ui_action: ChatUiAction | None` to `SendChatMessageRequest`, as `{source_message_id, block_id, action: choose|submit, option_index?, values?}`. Regenerate OpenAPI and the web contracts (`web/src/api/generated`, `web/src/features/assistant/api/generated.ts`).
- All four send routes accept it.
- `actions.py` validates that:
  - the source is an assistant message in the same session;
  - the block exists and supports the action;
  - for `choose`, the message content equals the option label;
  - values match the field spec.
- An invalid action strips `ui_action` and the text proceeds as an ordinary message. An action never does anything beyond a normal chat turn.
- **Tests:** a forged block id, a cross-session source, a label/content mismatch, out-of-range values, and each of the four routes.
- **Acceptance (Phase 5):** interactive replies work end to end and survive reload. The user always sees and sends the exact text.
- **Security review** (`/security-review`) before this phase is marked done.

### Phase 6 — Polish
- **GUI-6.1 Motion:** block fade-in and chart draw, disabled under reduced motion.
- **GUI-6.2 Accessibility pass:** keyboard-only use, screen-reader labels, chart data tables, focus order, contrast in every theme preset.
- **GUI-6.3 Fullscreen live-chat shell:** layout check. Text shown there uses the projections.

---

## 9. Later (not scheduled; no work-package detail until there's a reason)

- **HTML apps (AppBlock).** Deferred until a concrete Omnix use case exists. If revived:
  - Keep the source in `content`, and have the serve route re-extract it by block id with the same deterministic parser, so nothing new is stored. `metadata.ui` holds `{type, title, sha256, height_hint}`.
  - Give the shared header helper an **explicit policy argument**, so loosening the workspace-preview CSP (which includes `'unsafe-eval'`) can never silently apply to chat apps. Test the chat-app headers on their own.
  - Use `sandbox="allow-scripts"` and never `allow-same-origin`.
  - Treat CSP as **not** a complete network barrier: WebRTC is not reliably blocked by CSP, so an app that embeds conversation content has a low-bandwidth way out. Don't put sensitive context into app generation.
- **Repair pass.** One bounded retry for dropped blocks within the routing deadline.
- **Recompile tool.** Recompile stored replies under a new `compiler_version`.
- **Deep-research reports with blocks.** Reports have their own renderer and save path (`research/jobs.py`).
- **Character-mode rich replies.** A per-character opt-in.
- **Block supersession.** "Update that chart" replaces a prior block instead of regenerating.
- **Streaming skeletons.** Render a placeholder for an open fence while text streams, if the typed chat ever streams.
- **Persistent widget state** beyond submissions.
- **Structured tool-result bindings,** if assistant tools start returning structured results.
- **Export** with rendered blocks.

---

## 10. Testing strategy and gates

Per work package (local gates; CI is not watched during roadmap work):

- `python -m pytest src/tests/unit/chat/generative_ui -q --tb=short`
- `python -m pytest src/tests/unit/chat src/tests/chat -q --tb=short` (regression)
- PostgreSQL-touching tests run on the scratch test database (`omnix_tvp_test` in the 16432 container), never the live database.
- `ruff check src/app/platform/chat/generative_ui` and the existing mypy configuration.
- `npm --prefix web run test -- generative-ui markdownRenderer ChatbotWorkspace`
- `npm --prefix web run build` and the web typecheck and lint.
- Golden fixtures run in both pytest and Vitest.

Contract changes regenerate OpenAPI and the web contracts in the same change. This applies to GUI-3.1 (`rich_replies` and its route), GUI-5.4 (`ui_action`), and any new route.

Progress is tracked as `GUI-x.y` rows in [PROGRESS.md](../roadmap/PROGRESS.md), and deviations are recorded in [DECISIONS.md](../roadmap/DECISIONS.md).

---

## 11. Milestones, risks and open questions

### Milestones

| Milestone | Packages | User-visible result |
|---|---|---|
| M0 | GUI-0.x | Tables, task lists and alerts render properly in chat |
| M1 | GUI-1.x, GUI-2.x | Fenced replies render as components on every save path (not yet prompted) |
| M2 | GUI-3.x | Rich replies on for models that passed evaluation |
| M3 | GUI-4.x | Sourced citations, provenance marks, pinned read-only price charts |
| M4 | GUI-5.x | Choice buttons and composer-prefill forms that survive reload |
| M5 | GUI-6.x | Motion, accessibility, live-shell check |

GUI-0.3 ships immediately. Phases 1 and 2 must both land before Phase 3 enables prompting, so that no model emits blocks before every consumer and both save paths handle them. Phases 4 and 5 are independent of each other after Phase 3.

### Risks

| Risk / question | Mitigation / decision |
|---|---|
| Weak models emit broken JSON or overuse blocks | All start at `none`; multi-sample gate; `basic` subset; Markdown preferred; text fallback |
| Fence format leaks into turns where UI is off (voice, character, weak model) | Invariant 5: history projected to `ui.text` unless enabled; leakage measured in GUI-3.3 |
| Model invents numbers that look authoritative | Provenance marks; bindings and `price_chart` preferred; "Show data" toggle |
| Injected content steers a widget into sending a harmful instruction | Label equals message; forms prefill; server checks label/content match |
| Server and client validators drift | Shared golden fixtures run by both suites |
| A resolver stalls the commit | Resolvers run before the commit, outside the lock, bounded by the routing deadline; on failure the block degrades |
| Where `rich_replies` lives | **Decided:** per session, in the session `settings` JSONB like `research_mode_override`, with no migration (GUI-3.1). There's no server-side assistant settings document, and a client-only flag would make what the model sees in history depend on the browser |
| Character-mode rich replies | Off in V1; "Later" |

---

## Appendix A — Content readers and reply writers

Known on the base commit. GUI-0.2 completes and confirms the table.

### Readers of assistant `content`

| Reader | Location | Purpose / projection |
|---|---|---|
| Prompt history | `prompt_assembly.py` | `MODEL` / `MODEL_RICH` (turn-aware) |
| Session summaries | `compaction.py` | `SUMMARY` |
| History search | `history_search.py` | `SEARCH` |
| Memory turn reaction | `assistant_memory/turn_reactions.py` | `MEMORY` (to confirm) |
| Session export/import | `json_import.py` | `EXPORT` (raw + `metadata.ui`) |
| Delivery sync | `delivery_sync.py` | to classify |
| Job output ref | `_commit_chat_reply` `output_refs[].content` | raw (audit) |
| Copy | `useChatMessageActions.ts:51` | `chatMessageText` |
| PCM stream | `useChatMessageActions.ts:62` | `chatMessageSpeech` |
| Play | `ChatMessageItem.tsx` | `chatMessageSpeech` |
| Streamed voice | `useStreamedVoiceTurns.ts:85` | `chatMessageSpeech` |
| Research report download | `researchProgressController.ts:187` (`data-raw-content`) | raw, must stay raw |

### Writers of assistant replies

| Writer | Location | Compiles? |
|---|---|---|
| Job path | `generation_jobs._run_chat_generation_job` → `_commit_chat_reply` | Yes (GUI-1.4) |
| Stream path (both `/messages/stream` routes) | `admission.stream_chat_turn` → `_commit_chat_reply` | Yes (GUI-1.4) |
| Character greetings/replies | `character_store.py:266`, `:327` | Excluded: character mode is off in V1 |
| Memory commands | `prompt_store.py:651` | Excluded: deterministic text |
| Research reports | `research/jobs.py:258` | Excluded: own renderer ("Later") |
