# Live Agent conversation classification matrix

This suite validates the real SemanticTask v2 classification path with
**GPT-5.6 Luna at high reasoning effort** and then replays the resulting
SemanticTask through the production typed-chat handoff boundary.

It is intentionally broader than the existing single-turn semantic and coding
matrices. The corpus contains 34 scenarios and more than 160 user turns across:

- coding and local web/Playwright work;
- smart-home reads, changes, narrowing, verification, and target corrections;
- current public-web research, software releases, outages, and source-quality refinements;
- read-only trading research, quotes, catalysts, filings, and multi-step comparisons.

The coding corpus alone covers conversation lengths 1 through 10. Multi-turn
cases include discussion before implementation, read-only diagnosis followed by
a fix, repeated coding refinements, implementation corrections, test-only
follow-ups, and an explicit semantic resume.

## What each turn validates

For every user turn, the live model must produce a SemanticTask whose compiled
result has the expected lane, profile, action intents, evidence requirements,
prohibitions, and—where important—objective relation.

For Agent turns, the exact live SemanticTask is replayed through
route_typed_chat_turn with a recording execution service. The suite verifies
that Omnix sends exactly the intended user-authored request to execution:

- a new run receives an exact RunSpec task/objective;
- an active run receives an exact steering message;
- a semantic resume receives the prior canonical objective rather than stale
  assistant prose;
- prior transcript/reference context never leaks into task authority;
- the RunSpec profile and local/external capabilities equal the deterministic
  least-privilege authority compilation;
- Chat-created Agent RunSpecs use chatgpt_codex / gpt-5.6-luna / high.

The test does not execute real workspace, smart-home, web-search, or market
tools. Current-data Chat evidence execution is stubbed after its evidence policy
has been compiled and asserted. This keeps the suite focused on classification,
authority compilation, and the execution request boundary.

## Run it

PowerShell:

    $env:OMNIX_RUN_LIVE_AGENT_CONVERSATION_TESTS="1"
    python -m pytest src/tests/agent_runtime/test_live_agent_conversation_matrix.py -q --tb=short

The Codex CLI must already be installed and authenticated with ChatGPT.

The model and reasoning effort are fixed by the test contract. They are not
environment-overridable. The only Codex/runtime knobs are:

    $env:OMNIX_LIVE_CODEX_PATH="codex"
    $env:OMNIX_LIVE_AGENT_FAST_MODE="0"

The full matrix deliberately performs many live LLM classifications. For a
focused run, filter by domain:

    $env:OMNIX_LIVE_AGENT_CONVERSATION_DOMAIN="coding"

Valid domains are coding, smarthome, web, and trading. Multiple domains can be
comma-separated.

Or filter by scenario id substring:

    $env:OMNIX_LIVE_AGENT_CONVERSATION_SCENARIO="coding_05"

Unset the filters to run the complete matrix.

## Regression guard

A non-live test in the same module runs in the normal Agent Runtime suite and
prevents accidental shrinkage. It requires:

- at least 34 scenarios;
- at least 115 user turns;
- coverage of every conversation length from 1 through 10;
- at least eight scenarios and 30 turns in each requested domain;
- multiple coding refinements in the five-turn coding case;
- at least one semantic resume;
- current-evidence coverage for home, web, and trading;
- coding command/test execution coverage.

The existing single-turn live semantic and coding matrices remain useful. This
conversation matrix complements them by testing continuity and the exact
authority request sent after the classifier has interpreted conversational
context.
