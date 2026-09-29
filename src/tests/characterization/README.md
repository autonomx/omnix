# Characterization tests

These scenarios freeze externally observable behavior immediately before a
refactor. They capture values at a public route or pipeline boundary, normalize
only nondeterministic identifiers and time data, and compare the result with a
reviewed JSON golden.

Run the characterization suite with:

```text
python -m pytest src/tests/characterization -q --tb=short
```

To introduce a scenario, add its test and golden in the same PR **before**
changing the behavior it records. Set `OMNIX_UPDATE_GOLDEN=1` only for that
scenario-introduction run, review the generated JSON, then unset it. State in
the PR description that the golden captures the pre-refactor behavior. Once a
scenario is merged, a golden change requires a separate behavior-change PR and
written justification.

The shared fakes in `fakes.py` do not start providers or connect to live
services. `FakeLLMProvider` selects scripted responses using a SHA-256 digest
of canonical prompt messages; `FakeTTS` returns fixed bytes; `FakeMarketData`
returns an explicitly supplied bar series. Add deterministic inputs alongside
each new golden.

`harness.capture(name, fn)` requires a dictionary result and a checked-in golden.
The harness replaces timestamps, durations, and UUIDs in first-seen order,
rounds floats to six decimals, preserves ordered sequences, and sorts sets.
