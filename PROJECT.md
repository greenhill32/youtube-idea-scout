# YouTube Idea Scout

**Project ID:** youtube-idea-scout
**Aliases:** idea-scout
**Type:** Tool
**Status:** IDEA
**Created:** 2026-08-21
**Last Reviewed:** 2026-08-21

## Purpose

Automate the overnight legwork of scanning YouTube for video ideas, so Lee wakes up to a ready-made report instead of manually searching.

## Problem it solves

Manually trawling YouTube for content ideas is slow and easy to skip. This runs unattended overnight against a maintained keyword/niche list and hands back a report in the morning.

## Users

Lee (personal YouTube content pipeline).

## Success criteria

A usable idea list waiting each morning — a handful of ideas genuinely worth considering, not just a raw data dump.

## Current status

IDEA stage. Interview complete; scope, data source, and build details are pending a build plan from Lee.

## Architecture

TBD — no implementation yet.

## Main workflow

1. Lee maintains a list of keywords/niches to watch (mechanism TBD).
2. Overnight, the tool searches YouTube against that list (data source TBD — YouTube Data API vs. alternative).
3. Results are written to a local report (format TBD).
4. Lee reads the report in the morning.

## Important files

None yet — pre-implementation.

## Data / storage

- **Input:** Keyword/niche list maintained by Lee (format/location TBD).
- **Output:** Local report file (format TBD — likely Markdown or similar).
- **Persistence:** Local to this NUC, per repo root convention.

## External dependencies

TBD — likely the YouTube Data API (needs an API key), pending Lee's decision. No other services confirmed.

## Security / access / network exposure

Expected local-only, outbound-only (calls YouTube's API/search, no inbound network exposure). Confirm once implementation starts.

## Decisions made and why

1. **Keyword/niche list, not general trending scan**: Lee wants control over which niches get watched rather than a generic trending feed.
2. **Local report, not email/notification**: Report lands as a local file on the NUC; no external delivery service in scope for now.
3. **Overnight/scheduled run**: The point is to have the report ready in the morning without manual triggering — implies this needs a scheduled job (cron or similar) once built.

## Known problems / gotchas

None yet — pre-implementation.

## Out-of-scope items

TBD — Lee will provide a build plan that defines scope boundaries and abandon criteria in more detail.

## Recovery notes

N/A — pre-implementation.

## Next 3 things

1. Lee to provide a build plan covering scope, data source, and report format.
2. Decide data source (YouTube Data API vs. alternative) and report contents.
3. Decide how the keyword/niche list is maintained (flat file, config, etc.) and how the overnight run gets scheduled.

## AI handoff instructions

Before making changes:
1. Read this file + `git status`.
2. Don't restructure or delete without flagging it first.
3. Prefer small, testable changes.
4. Update Status, Known Problems, and Next 3 Things after significant work.

This project is pre-implementation — the interview is done but the build plan is still coming from Lee. Don't invent architecture, data source, or scope ahead of that plan; treat everything marked TBD as genuinely undecided.

## Recent important history

**2026-08-21 — Project initialised**
Interview held with Lee to scope an overnight YouTube idea-scouting tool: searches a maintained keyword/niche list overnight, produces a local morning report. Success = a usable idea list each morning, not a raw data dump. Data source, report format, and out-of-scope boundaries deferred — Lee will follow up with a build plan.
