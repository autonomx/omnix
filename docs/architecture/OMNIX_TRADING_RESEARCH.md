# Omnix Trading Read-Only Market Research

OTT-14 adds optional AI-assisted research without creating a second provider system and without granting the model any mutation capability.

## Provider boundary

The runtime resolves the currently configured provider through `app.shared.get_provider()`. That path uses Omnix provider settings, caching, and the existing provider registry. Trading does not import LM Studio, OpenRouter, Cerebras, OpenAI, or any provider SDK directly.

The request may include a model override, but it cannot contain API keys, base URLs, credentials, or arbitrary provider configuration.

## Bounded normalized context

The research service accepts at most:

- 200 finalized normalized bars
- 20 selected price levels
- an 800-character research question
- a 24,000-character serialized context

Only the latest 40 finalized bars are included individually in the prompt. The remaining requested history contributes to deterministic indicators and source evidence.

Context includes:

- canonical instrument metadata
- interval
- latest OHLCV and one-bar change
- SMA 20, EMA 20, and RSI 14 from `omnix-indicators-v2`
- selected levels
- provider, requested/resolved binding, freshness, cache, completeness, and as-of metadata
- the normalized dataset fingerprint

No news, fundamentals, account state, alerts, backtests, orders, fills, or positions are added unless they are explicitly introduced by a later reviewed roadmap phase.

## Output contract

The registered model must return one JSON object with exactly:

- `summary`
- `observations`
- `risks`
- `confidence`

Pydantic rejects malformed JSON, extra execution-shaped fields, missing sections, unbounded lists, and invalid confidence values. The server attaches provider/model identity and immutable source evidence after validation; the model cannot choose or alter that metadata.

Every successful response contains:

- `read_only: true`
- the exact instrument, interval, binding, provider, dataset fingerprint, formula version, bar count, freshness, and as-of timestamp
- `Research only. Not financial advice. No order was created or executed.`

## Failure behavior

- Request/context validation failures return `422`.
- Invalid provider JSON or schema output returns `502`.
- Missing configured providers return `503`.
- Calls exceeding 90 seconds return `504`.

Failures do not create a fallback narrative and do not mutate Trading state.

## Mutation isolation

The frontend has one endpoint: `POST /api/trading/research`. The service has no dependency on alert creation, backtest execution, paper observation processing, or order placement. It cannot autonomously execute trades.
