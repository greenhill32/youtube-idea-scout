# YouTube Idea Scout

**Project ID:** youtube-idea-scout
**Aliases:** idea-scout
**Type:** Tool
**Status:** BUILDING
**Created:** 2026-08-21
**Last Reviewed:** 2026-08-21

## Purpose

Automate the overnight legwork of scanning YouTube for video ideas, so Lee wakes up to a ready-made report instead of manually searching.

## Problem it solves

Manually trawling YouTube for content ideas is slow and easy to skip. This runs unattended overnight against a maintained keyword/niche list and hands back a report in the morning.

## Users

Lee (personal YouTube content pipeline).

## Success criteria

The first report contains at least 5 ideas Lee would genuinely consider making a video about, with evidence he wouldn't have found manually. If not, the architecture is wrong — not too simple.

## Current status

Building per `docs/build-plan.md`, stage-gated (BUILD → RUN → VERIFY → AMEND → PASS, stop for confirmation between stages). Scaffolding done: `config.py`, `seeds.txt`, `preflight.py` all written and passing. Stage 1 (autocomplete expansion) up next.

## Architecture

A Python CLI pipeline, 7 sequential stages, each reading/writing a JSON file so any stage can be re-run independently:

1. **Autocomplete expansion** — seed phrases × a-z suffixes → YouTube autocomplete → `data/autocomplete.json`
2. **YouTube search** — each autocomplete query → yt-dlp search → `data/search_results.json`
3. **Enrichment/scoring** — dedup videos, compute demand/competition/breakout/channel-fit/freshness signals → `data/enriched.json` (pure Python, no network)
4. **Filtering** — hard score/demand/saturation rules narrow to ~30 survivors → `data/survivors.json`
5. **Captions** — pull top-competitor captions per survivor via yt-dlp → `data/captions/<id>.txt`
6. **Gap analysis** — one `claude -p` call per survivor, competitor transcripts in, gap + suggested angle out → `data/analyses/<n>.json`
7. **Report** — assemble a single self-contained `data/report.html`, no JS framework, no server

No database, no dashboard, no autonomous publishing — the pipeline ends at `report.html`; a human reads it and decides. Full stage code and rationale: `docs/build-plan.md`.

## Main workflow

1. Lee maintains `seeds.txt` — one seed phrase per line (question/hook patterns), grouped by comments.
2. `python scout.py` runs preflight then all 7 stages in order (or `--from N` to resume after a fix).
3. Output lands at `data/report.html` — scored ideas, competitor stats, and a Claude-generated content-gap angle per idea.
4. Lee reads the report in the morning and decides what to make. Nothing auto-publishes.

## Important files

- `config.py` — every tuneable constant (thresholds, weights, paths, model name)
- `seeds.txt` — seed phrases driving Stage 1
- `preflight.py` — checks yt-dlp, YouTube autocomplete, and the `claude` CLI actually work before any stage runs
- `scout.py` — main entry point, runs all 7 stages, supports `--from N` resume
- `stage1_autocomplete.py` … `stage7_report.py` — one file per pipeline stage
- `data/` — all runtime output (gitignored; regenerable, not source)
- `docs/build-plan.md` — the full build plan this project is being built from, including the stage-gate build rule

## Data / storage

- **Input:** `seeds.txt` (committed), YouTube (live, via yt-dlp + autocomplete endpoint)
- **Intermediate:** JSON files per stage under `data/` (`autocomplete.json`, `search_results.json`, `enriched.json`, `survivors.json`), plus `data/captions/*.txt` and `data/analyses/*.json`
- **Output:** `data/report.html` — the morning deliverable
- **Persistence:** all local to this NUC; `data/` is a working directory, not permanent storage — each run can overwrite it

## External dependencies

- `yt-dlp` (system package, installed via `apt-get install -t trixie-backports yt-dlp` — the stock Debian version was too old to survive YouTube's current extraction changes)
- YouTube's public autocomplete endpoint (unofficial, no key)
- `claude` CLI (Stage 6 gap analysis, uses Lee's existing Claude Code subscription — no separate API billing)
- Optionally Ollama (only if `USE_LOCAL_LLM_FILTER` is turned on in `config.py`; off by default)

## Security / access / network exposure

Local-only tool, outbound-only network calls (YouTube autocomplete + yt-dlp + local `claude` CLI). No inbound exposure, no server, no credentials stored beyond whatever `claude`/`yt-dlp` already manage.

## Decisions made and why

1. **Keyword/niche list (`seeds.txt`), not general trending scan**: Lee wants control over which niches get watched rather than a generic trending feed.
2. **Local HTML report, not email/notification**: report lands as a local file on the NUC; no external delivery service in scope for now.
3. **No YouTube Data API key** — uses yt-dlp search + the public autocomplete endpoint instead, avoiding API quota/key management.
4. **Claude Code CLI (`-p` flag) for gap analysis, not the API** — rides Lee's existing subscription, no separate billing; Codex CLI fallback documented as a V2 idea, not built.
5. **JSON-file-per-stage architecture, no database** — every stage is independently re-runnable (`scout.py --from N`) and inspectable by hand; deliberately avoids infra weight for a personal overnight tool.
6. **Stage-gated build process**: each of the 7 stages must BUILD → RUN → VERIFY → PASS with real inspected output before the next stage is written. No building ahead, no debugging the whole pipeline at the end. See `docs/build-plan.md`.
7. **apt package over pip for yt-dlp**: kept as a system package via backports rather than a venv/pip install, per Lee's preference when offered the choice (2026-08-21 preflight fix).

## Known problems / gotchas

- yt-dlp needs to stay current — YouTube's extraction changes break older versions (hit this immediately: stock Debian trixie yt-dlp 2025.04.30 failed with a SABR-streaming error; fixed by installing 2026.03.17 from `trixie-backports`). If searches start failing with extractor errors again, check for a newer yt-dlp first.
- `--flat-playlist` in Stage 2 is fast but may return `None`/`0` for `view_count`/`channel_follower_count` on some results — noted in the build plan as a thing to watch when verifying Stage 2 output.
- Score weights in Stage 3 (`config.py`) are a starting point, expected to need tuning after reading the first few real reports.

## Out-of-scope items

No database, no dashboard/web server, no autonomous publishing or cross-posting to other systems, no YouTube Data API key, no agent-to-agent communication. V2 ideas explicitly deferred (see `docs/build-plan.md`): Codex fallback, Google Trends signal, TikTok trending data, autocomplete diffing, cron scheduling, "promote to Factory" pipeline handoff, stale-niche detection, multi-competitor transcript comparison.

Abandon criteria: not yet stated by Lee beyond the implicit one in the build plan's success bar — if the first real report doesn't surface 5 ideas worth making, the architecture (not just the tuning) is considered wrong.

## Recovery notes

If a stage fails mid-run: `scout.py` prints which stage failed and the exact resume command (`python scout.py --from <stage>`); prior stages' JSON outputs on disk are untouched. Preflight (`python preflight.py`) catches systemic breakage (yt-dlp, autocomplete endpoint, `claude` CLI) before anything else runs — run it first when debugging.

## Next 3 things

1. Build and verify Stage 1 (`stage1_autocomplete.py`) — run against real `seeds.txt`, confirm `data/autocomplete.json` has hundreds of unique suggestions.
2. Build and verify Stage 2 (`stage2_search.py`) against Stage 1's real output.
3. Continue stage-by-stage per the build plan through Stage 7, stopping for confirmation after each PASS.

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
