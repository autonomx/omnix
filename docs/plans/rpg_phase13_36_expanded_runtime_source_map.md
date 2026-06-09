# Phase 13.36 — expanded runtime source map

## Context

The stream-capture artifact now reliably records late failed turns from the console log. It confirms turns 59 through 100 fail with the same runtime error, but the live stack is still not available. The current source map only shows a narrow window around the runtime-result probe.

## Change

This slice expands the generated source map artifact so the next operator run can identify the surrounding generated code without needing a live Python traceback.

The source map now includes:

- wider local context around matching lines
- bounded enclosing function context
- function start and end line numbers
- matches for the runtime-result probe
- matches for the runtime exception capture helper
- matches for likely turn failure console emission lines

## Verification target

The next operator run should produce an expanded `autoplay-runtime-probe-source-map.json` that includes the full bounded function context around the failed runtime-result probe and any turn-failure emission lines present in the combined generated source.

This is evidence capture only; it does not claim the runtime issue is fixed.
