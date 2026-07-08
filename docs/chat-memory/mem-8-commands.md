# MEM-8 — Explicit memory commands

Status: implementation complete pending exact-head required checks.

Recognized commands are parsed deterministically and handled without sending the command to the language model. Supported operations include explicit save with scope/category, list, unambiguous forget, snapshot refresh, per-Chat disable, and exact-ID update. Ambiguous forget and unavailable update operations remain non-mutating.
