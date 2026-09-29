# Archived RPG test tooling

`manual_llm_transcript_old.py.txt` preserves the retired monolithic manual
transcript runner for historical reference. It had 91 undefined-name findings
and was only executable through the `manual_llm_transcript_old.py` shim, which
has been removed. The maintained entry point is
`src/tests/rpg/manual_llm_transcript.py`; current behavior is implemented in
`src/tests/rpg/manual/` and covered by the RPG manual tests.
