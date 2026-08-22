# YouTube Idea Scout — Code & Output Analysis

**Reviewer:** Claude (Opus 5)
**Date:** 2026-08-22
**Scope:** Full source review (1,611 lines across 10 modules) plus empirical analysis of the completed production run of 2026-08-21 (20:23–23:42 UTC, 6,779 queries, 30,077 videos).
**Status:** Report only — no code was changed.

---

## 1. Verdict

The engineering is sound. The pipeline is cleanly staged, well-commented, resumable, and it ran for three hours unattended and completed without intervention. That is a real achievement and most of the plumbing deserves to survive.

**The scoring model, however, does not work.** It is not a matter of tuning — three of the five signals carry almost no information, the composite has a hard ceiling that 64 ideas hit simultaneously, and the final 30 that reached your report were selected from those 64 by *thread completion order*. The report you read this morning is, functionally, an alphabetical slice of a tie.

That explains the symptom you already noticed: 28 of 30 cards begin with the words "why are humans".

Separately, a caption-handoff mismatch meant **37% of the transcript slots in the Stage 6 prompts were empty** — the pipeline downloaded the captions, then asked Claude to analyse videos it had not been given the transcripts for.

Below: what's good, then findings ranked by impact, then recommendations.

---

## 2. What's genuinely good

Worth stating plainly, because these are the parts worth building on:

- **Stage separation is clean.** Each stage has one input file, one output file, a `run_*()` entry point, and a `__main__` block for isolated testing. `scout.py --from N` works. This is the right shape.
- **Deterministic scoring is kept separate from LLM judgement.** Stages 3–4 are pure Python; the LLM only runs on 30 survivors. That is the correct architecture and it keeps cost and variance down.
- **Preflight checks (`preflight.py`) are excellent practice** — verifying that `yt-dlp` can actually *reach YouTube*, not merely that the binary exists, is the difference between failing in 10 seconds and failing in 3 hours.
- **HTML escaping is done correctly.** `esc()` in `stage7_report.py:18` is applied to every interpolated field. Many hand-rolled report generators get this wrong.
- **Caption caching** (`stage5_captions.py:138`) avoids re-downloading across runs.
- **The comments explaining past bugs are outstanding.** `stage3_enrich.py:91-93` (the "body" inside "nobody" false positive), `stage2_search.py:38-41` (why `--flat-playlist` was rejected), `stage5_captions.py:70-73` (the VTT header). This is institutional memory written down at the point of use, and it is rarer than it should be.

---

## 3. Critical findings

### F1 — The composite score has a ceiling of 0.95, and 64 ideas hit it exactly

**Severity: critical.** `stage3_enrich.py:100-124`

The weighted composite is:

```
demand*0.30 + competition*0.20 + breakout*0.15 + channel_fit*0.25 + freshness*0.10
```

`competition = max(1 - video_count/20, 0)`. But `MAX_SEARCH_RESULTS_PER_QUERY = 5`, so `video_count` is 5 for essentially every query. Measured across the run:

| `raw_video_count` | ideas |
|---|---|
| 5 | 6,004 (99.6%) |
| 1–4 | 24 |

So `competition` is **0.75 for 99.6% of ideas** — a constant. It contributes a fixed +0.15 to every score and discriminates nothing. The maximum achievable composite is therefore `0.30 + 0.15 + 0.15 + 0.25 + 0.10 = 0.95`, and no idea can ever score higher.

**64 ideas scored exactly 0.95.** Stage 4 takes the first 30.

### F2 — The tiebreak among those 64 is non-deterministic

**Severity: critical.** `stage2_search.py:99` → `stage3_enrich.py:166` → `stage4_filter.py:127`

Stage 3 sorts by score with Python's stable sort, so ties preserve input order. Input order is `search_results.json` key order, which is written in `as_completed()` order — i.e. **whichever of the 4 worker threads happened to finish first**.

Measured: the key order has 632 out-of-alphabetical adjacent pairs out of 6,027 (10.5%). It *approximates* the sorted input order because tasks take similar time, which is why the report looks alphabetical — but it is incidental scheduling, not a guarantee.

The practical consequence: **34 ideas that scored identically to the ones you read were discarded for no reason**, and a re-run on the same data could return a different 30. Among the discarded:

```
why can't humans grow new teeth
why can't humans imagine a new color
why can't humans live past 100
why can't humans drink dirty water like animals
```

Several of these are, arguably, better video ideas than what made the cut.

### F3 — `channel_fit` is a "why"+"humans" detector, not a channel model

**Severity: critical.** `config.py:41-46`, `stage3_enrich.py:94-103`

`channel_fit = min(matches/2, 1.0)` — two keyword hits earn full marks. Keyword firing rates across all 6,028 scored ideas:

| keyword | fires on | | keyword | fires on |
|---|---|---|---|---|
| `why` | 2,764 (45.9%) | | `work` | 15 (0.2%) |
| `humans` | 527 (8.7%) | | `brain` | 6 (0.1%) |
| `body` | 99 (1.6%) | | `history` | 1 |
| `human` | 85 (1.4%) | | `society` | 1 |
| `money` | 63 (1.0%) | | **`psychology`** | **0** |
| | | | **`evolution`** | **0** |
| | | | **`behaviour`** | **0** |

The three keywords that most specifically describe your channel's territory **never fire once**. `why` is effectively a stopword in a seed list where nearly every seed starts with "why".

Because two hits are needed for a 1.0, and the only common co-occurrence is `why` + `humans`, the signal reduces to a test for that exact phrase pair. Stage 4 then applies a **hard gate** on `channel_fit > 0` (`stage4_filter.py:36-42`), making this weak proxy the single most decisive filter in the pipeline.

That is the direct cause of the 28/30 "why are humans" report. The relevance fix of 2026-08-21 solved the pop-culture-collision problem by over-correcting into a near-monoculture.

### F4 — 37% of transcripts were silently missing from the LLM prompts

**Severity: critical.** `stage5_captions.py:124-128` vs `stage6_analysis.py:137`

Stage 5 selects which videos to fetch captions for by **view count descending**:

```python
videos = sorted(idea.get("videos", []),
                key=lambda v: v.get("view_count", 0) or 0,
                reverse=True)[:MAX_CAPTION_VIDEOS_PER_IDEA]
```

Stage 6 selects which captions to *read* by **original search-result order**:

```python
for video in idea.get("videos", [])[:MAX_CAPTION_VIDEOS_PER_IDEA]:
```

These are different sets. Measured on the run:

- **27 of 30 survivors** had a mismatch between the two sets.
- **33 of 90 caption lookups (37%)** found no file and passed the literal string `"(no captions available)"` into the prompt.

So the pipeline spent time downloading 88 transcripts, then discarded a third of them and asked Claude to perform gap analysis on competitor videos whose content it could not see — while still presenting the resulting analysis in the report with a green "high confidence" badge. This degrades the one output that carries real value.

### F5 — ~93 minutes of the run were provably wasted

**Severity: high.**

`channel_fit` is computed **purely from the query string**. It needs no network call, no video metadata, nothing from Stage 2. Yet the gate that rejects `channel_fit == 0` runs in Stage 4, *after* every query has been searched.

Of the 6,779 queries handed to Stage 2, **3,438 (50.7%) had `channel_fit == 0`** and were therefore guaranteed to be rejected before a single video was fetched for them.

Stage 2 took ~183 minutes. Roughly **93 minutes searched queries that could not possibly survive.**

### F6 — Overall funnel yield is 0.44%

**Severity: high (design).**

```
6,779 queries searched
  → 6,028 returned videos      (751 empty, 11%)
  → 2,396 passed hard rules
  →    64 tied at the 0.95 ceiling
  →    30 reported             ← 225:1
```

Three hours of network I/O and 57 MB of intermediate JSON to produce 30 cards, of which (see F7) perhaps 12–15 are distinct ideas.

### F7 — The 30 cards are not 30 ideas

**Severity: high (output quality).**

The survivor list contains obvious near-duplicates:

```
why are humans apex predators
why are humans considered apex predators
why are humans not apex predators
why are humans top of the food chain
why are humans at the top of the food chain
```

That is five cards for what is one video. Likewise `why are humans right handed` / `why are humans right hand dominant` / `why are humans mostly right handed`, and `why are humans different colors` / `why are humans different skin colors`.

Corroborating this: **12 of 73 distinct videos appear in more than one survivor's top-3**, meaning the pipeline paid for overlapping caption downloads and overlapping LLM analyses of the same source material.

There is no near-duplicate collapse anywhere in the pipeline.

---

## 4. Correctness & robustness

### F8 — Stage 2 has no checkpointing; a crash at 99% loses three hours

`stage2_search.py:93-120`. All results accumulate in an in-memory dict and are written **once**, at the end. A crash, OOM, or `Ctrl-C` at query 6,700 of 6,779 discards everything. `scout.py --from N` resumes at *stage* granularity only, so recovery means re-running the full three hours.

### F9 — The deduplication in Stage 3 is a no-op

`stage3_enrich.py:141-154`. The `if` and `elif` branches perform *identical* work:

```python
if vid and vid not in seen_video_ids:
    seen_video_ids.add(vid)
    unique_videos.append(compute_video_scores(v))
elif vid in seen_video_ids:
    unique_videos.append(compute_video_scores(v))   # same thing
```

`seen_video_ids` is populated but never affects output. The docstring claims "Deduplicates videos by video ID across queries" — nothing is deduplicated. Either the dedup is wanted (and missing) or it isn't (and this is misleading dead code). Given F7, some form of cross-idea dedup probably *is* wanted.

### F10 — Latent crash in the freshness calculation

`stage3_enrich.py:85-88`:

```python
oldest_top_video_days = max(
    (v.get("age_days", 0) or 0) for v in videos
    if (v.get("view_count", 0) or 0) > 0
) if videos else 0
```

The `if videos` guard protects against an empty *video list*, but not against every video having zero views — which makes the generator empty and raises `ValueError: max() arg is an empty sequence`. This kills the entire run via `scout.py:73-76`.

Zero occurrences in this dataset, so it is latent rather than active — but it would surface roughly three hours into a run, at Stage 3, on a day when a query returns only brand-new zero-view videos.

### F11 — `MAX_SATURATION_COUNT` gate can never fire

`stage4_filter.py:34-35` rejects ideas where `raw_video_count >= 20`. Since Stage 2 caps at 5 results, this condition is unreachable. Dead rule.

### F12 — Search failures are indistinguishable from genuine no-results

`stage2_search.py:73-78` returns `[]` for timeout, non-zero exit, and legitimate empty results alike. 751 queries (11%) "returned zero videos" — there is no way to tell how many were real vs transient network failures. There is no retry on any of them.

### F13 — Hard rules are evaluated twice over the full list

`stage4_filter.py:111` and `:146` each run `passes_hard_rules` across all 6,028 ideas. Cheap here, but it is the kind of duplication that gets expensive when the predicate later grows.

### F14 — `USE_LOCAL_LLM_FILTER` is untested code

`stage4_filter.py:46-97` has never executed (`config.py:69` is `False`). It shells out to `curl` rather than using `urllib` as the rest of the codebase does, and on failure returns *all* borderline ideas. It is a plausible source of surprise the day it is switched on.

---

## 5. Output quality & LLM usage

### F15 — LLM `confidence` is not discriminating

Across the 30 analyses: **25 "high", 5 "medium", 0 "low"**. The model is asked to self-assess whether a real content gap exists, on evidence that (per F4) was frequently missing. It says "high" 83% of the time. The report then colour-codes this as if it carried information — green badges throughout `stage7_report.py:92-98`.

Uncalibrated self-assessment presented as a confidence signal is worse than no signal, because it invites trust.

### F16 — Prompt-injection surface via YouTube transcripts

`stage6_analysis.py:36-45`. Auto-generated captions — text written by third parties — are interpolated directly into a Claude prompt whose output is parsed as JSON and rendered into HTML.

Severity is genuinely **low**: output is escaped at render (`esc()`), and the analysis is advisory. But a video whose transcript contains instruction-shaped text could steer the analysis for that card. Worth knowing about; not worth alarm.

### F17 — Stage 6 output parsing is fragile

`stage6_analysis.py:91` uses `re.search(r"\{[\s\S]*\}", raw_output)` — greedy, spanning first `{` to last `}`. It works, but the Claude CLI supports `--output-format json`, which would remove the guesswork entirely.

### F18 — Stage 6 runs 30 sequential subprocesses

`stage6_analysis.py:132-146`. Roughly 9 minutes of the run, serially, when Stage 2 already demonstrates the `ThreadPoolExecutor` pattern that would cut it to ~2.

### F19 — Stage 1 spends most of its time asleep

`stage1_autocomplete.py:134`. 675 requests × 0.3s = 3.4 minutes of `time.sleep` out of a ~5 minute stage, fully serialised.

---

## 6. Operational

### F20 — 57 MB of intermediate JSON rewritten every night

`enriched.json` (31 MB) and `search_results.json` (26 MB) carry full video metadata — including 500-character descriptions — for all 6,028 ideas, when 30 matter. Both are pretty-printed with `indent=2`. On an overnight cadence this is meaningful disk churn for data that is discarded the next day.

### F21 — No cross-run memory

Nothing records what was reported yesterday. Run this tonight and it will return the same alphabetical slice of the same "why are humans" tie. There is no dismissal mechanism, no suppression of already-seen ideas, and no record of which suggestions you actually acted on.

For a tool meant to run nightly, this is the difference between a habit and a novelty.

### F22 — No tests

Zero test files. Stages 3 and 4 are pure, deterministic functions over plain dicts — the easiest possible thing to unit-test. A single test asserting that `competition` varies across inputs would have caught F1 on day one.

### F23 — Measured stage timings

Derived from output-file mtimes (the log records only start/end):

| Stage | Duration | Share |
|---|---|---|
| 1 — Autocomplete | ~5 min | 2.5% |
| **2 — Search** | **~183 min** | **92%** |
| 3 — Enrich | <2 s | ~0% |
| 4 — Filter | <1 s | ~0% |
| 5 — Captions | ~2 min | 1% |
| 6 — Gap analysis | ~9 min | 4.5% |
| 7 — Report | <1 s | ~0% |
| **Total** | **3 h 19 m** | |

Stage 2 *is* the runtime. Every optimisation that matters lives there.

---

## 7. Recommendations, in priority order

### Tier 1 — Fix before the next run (correctness)

1. **Align Stage 5 and Stage 6 on the same video selection (F4).** One shared helper — `top_videos_for_idea(idea)` — called by both. This is a handful of lines and it recovers a third of the analytical input the pipeline already paid for. Highest value-per-effort item in this report.

2. **Break the scoring ceiling (F1, F2).** Either drop `competition` entirely and redistribute its 0.20 weight, or make it measure something real (see #6). Then add an explicit, deterministic tiebreak — `sort(key=(-score, query))` at minimum — so results stop depending on thread scheduling.

3. **Move the `channel_fit` gate into Stage 1 (F5).** It is a pure function of the query string. Applying it before the network call removes half the Stage 2 workload for zero loss in output. ~90 minutes saved per run, one function moved.

4. **Fix or remove the no-op dedup (F9) and guard the `max()` (F10).**

### Tier 2 — Make the output worth reading (quality)

5. **Replace the `channel_fit` keyword list with something that models the channel (F3).** Options, cheapest first:
   - Remove `why` (a stopword in your seed set) and require matches from a *topical* vocabulary — this alone would break the monoculture.
   - Weight keywords instead of counting them, so `evolution` is worth more than `body`.
   - Best: score fit by similarity against the titles/descriptions of videos *you have actually published*, rather than a hand-written list. It adapts as the channel does.

6. **Make `competition` measure competition.** Counting your own result limit cannot work. Either search deeper (`ytsearch20:`) and count results whose titles genuinely match the query intent, or derive it from view distribution — a topic where the top video has 50× the tenth is wide open; one where ten videos share views evenly is saturated.

7. **Rename `freshness` → `staleness`, and rescale it (F/§3).** 94.4% of ideas score 1.0 because the cap is 365 days and most YouTube topics have something older. Either raise the ceiling to ~3 years or switch to a percentile rank across the run.

8. **Collapse near-duplicate queries before Stage 4 (F7).** Cluster on normalised token sets, keep the highest-scoring member, and list the variants as alternate phrasings on that one card. Thirty genuinely distinct ideas beats thirty cards.

9. **Prefer percentile ranks over hard caps throughout.** `demand` saturates at 1.0 for 42.7% of ideas because of the fixed `/2000` divisor. Ranking each signal *within the run* keeps every signal discriminating regardless of how the absolute numbers drift.

10. **Drop the `confidence` field, or ground it (F15).** As it stands it is decoration. If it stays, the LLM should be told explicitly when a transcript was unavailable, and instructed to lower confidence accordingly.

### Tier 3 — Make it a nightly habit (operations)

11. **Two-phase search (F23).** Use `--flat-playlist` for the breadth pass (fast, gives ids and titles), score a provisional ranking, then pay for full metadata resolution only on the top few hundred. Combined with #3, this plausibly takes Stage 2 from ~3 hours to well under 30 minutes — which changes what the tool can be.

12. **Checkpoint Stage 2 to JSONL (F8).** Append each result as it completes; on restart, skip queries already present. Removes the all-or-nothing failure mode.

13. **Add a `seen.json` (F21).** Suppress or decay ideas reported in the last N days. Log which ideas you actually made videos about — that becomes the training signal for #5.

14. **Parallelise Stage 6 (F18)** with the pool pattern from Stage 2, and use `claude --output-format json` (F17).

15. **Unit-test Stages 3 and 4 (F22).** Pure functions, plain dicts. A dozen assertions covering signal variance, the ceiling, and tie behaviour would have caught F1, F2, F10 and F11.

16. **Emit a run manifest** — per-stage timings, counts, rejection reasons, score histogram — as JSON alongside the report. Right now that has to be reconstructed from file mtimes.

---

## 8. Closing

The pipeline works. What it is missing is a scoring model that discriminates, and that gap is disguised precisely *because* the plumbing is reliable — it produces thirty confident-looking cards every time, so nothing appears wrong until you notice they all start with the same three words.

The single highest-leverage change is #1 (the caption alignment): a few lines, and it recovers a third of the evidence the gap analysis is supposed to be built on. After that, #3 buys back an hour and a half of runtime for almost no work, and #2 and #5 together are what turn the report from an alphabetical slice of a tie into an actual ranking.

None of this requires rearchitecting. The bones are good.
