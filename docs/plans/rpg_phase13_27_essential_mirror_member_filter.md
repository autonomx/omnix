# Phase 13.27 — essential mirror member filter

## Context

The latest operator rerun showed the report materialization guard is working and preserving evidence. The remaining post-run delay is the essential unzipped artifact mirror, which reported copying a small set of files while skipping 17,740 files.

## Change

This slice installs a narrow ZIP member filter for `autoplay-campaign-results.zip` enumeration. It removes `review-artifacts/` members from `namelist()` and `infolist()` results so essential mirror/review code does not spend time iterating thousands of large review split members that are not part of the essential mirror.

The filter is opt-out via `RPG_AUTOPLAY_FAST_ESSENTIAL_MIRROR=0` and does not affect other ZIP files.

## Verification target

The next operator rerun should show the final mirror line with a much smaller skipped count and a shorter gap between `write_results_zip.end` and `Wrote essential unzipped autoplay result artifact mirror`.

This does not claim the RecursionError is fixed.
