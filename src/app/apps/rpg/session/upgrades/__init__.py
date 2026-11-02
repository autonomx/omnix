"""A campaign document's upgrade: what an older version's document is given once, when it is first opened, as a system
turn with a pinned backup (``session/campaign_state.py``'s upcasters; operator-notes.md "Upgrades"). Nothing here runs
on a current document: a load reads it as stored, and a turn changes it only through the reducer."""
