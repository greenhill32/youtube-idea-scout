"""
Stage 3: Enrich and score search results.

Input:  data/search_results.json
Output: data/enriched.json — list of enriched idea objects, each containing:
        - query (the autocomplete phrase)
        - videos (list of competing videos with computed scores)
        - idea_score (composite 0-1 score for this idea)
        - signals (dict of individual signal values)

All scoring is deterministic Python. No LLM, no network calls.
"""

import json
from datetime import datetime, timezone
from collections import defaultdict
from config import (
    DATA_DIR,
    MIN_VIEWS_PER_DAY,
    MAX_SATURATION_COUNT,
    BREAKOUT_VIEWS_PER_DAY,
    BREAKOUT_MAX_AGE_DAYS,
    COMPETITION_FIELD_VPD_CAP,
)
from common import channel_fit_score, current_run_id


def parse_upload_date(date_str: str) -> datetime | None:
    """Parse YYYYMMDD date string to datetime."""
    if not date_str or len(date_str) != 8:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def days_since_upload(date_str: str) -> float | None:
    """Days between upload date and now."""
    upload = parse_upload_date(date_str)
    if not upload:
        return None
    delta = datetime.now(timezone.utc) - upload
    return max(delta.days, 1)  # Floor at 1 to avoid division by zero


def compute_video_scores(video: dict) -> dict:
    """Add computed fields to a single video dict."""
    video = dict(video)  # Don't mutate the original

    age_days = days_since_upload(video.get("upload_date", ""))
    views = video.get("view_count", 0) or 0
    subs = video.get("channel_follower_count", 0) or 0

    video["age_days"] = age_days
    video["views_per_day"] = round(views / age_days, 1) if age_days else 0
    video["views_per_sub"] = round(views / subs, 2) if subs > 0 else 0
    video["is_breakout"] = (
        video["views_per_day"] >= BREAKOUT_VIEWS_PER_DAY
        and age_days is not None
        and age_days <= BREAKOUT_MAX_AGE_DAYS
    )

    return video


def compute_idea_score(query: str, videos: list[dict]) -> tuple[float, dict]:
    """
    Score an idea (query) based on its competing videos.
    Returns (normalised_score, signals_dict).

    Signals:
    - demand: are people watching videos on this topic? (views/day of best video)
    - competition: how strong is the whole competing field, not just one video?
    - breakout: any recent breakout videos? (suggests rising interest)
    - channel_fit: does the query match your channel's territory?
    - freshness: is the best-performing video old? (old = stale = opportunity)
    """
    if not videos:
        return 0.0, {}

    best_vpd = max(v.get("views_per_day", 0) for v in videos)
    video_count = len(videos)
    has_breakout = any(v.get("is_breakout", False) for v in videos)
    oldest_top_video_days = max(
        ((v.get("age_days", 0) or 0) for v in videos
         if (v.get("view_count", 0) or 0) > 0),
        default=0,
    )

    channel_fit = channel_fit_score(query)

    # Normalise each signal to 0-1 range
    demand = min(best_vpd / 2000, 1.0)            # 2000 vpd = max demand signal
    # Competition (v0.2 rework): the old signal was 1 - video_count/20, but
    # MAX_SEARCH_RESULTS_PER_QUERY caps every search at 5 results, so
    # video_count was ~5 for 99.6% of ideas — a near-constant that
    # contributed a fixed +0.15 to every score and discriminated nothing
    # (64 ideas tied at the resulting 0.95 ceiling in the 2026-08-21 run).
    # Instead, measure how strong the whole field is performing (average
    # views/day across all returned videos, not just the best one): a
    # field where every video does well is genuinely saturated; a field
    # with one breakout and four weak videos still has room.
    avg_field_vpd = sum(v.get("views_per_day", 0) or 0 for v in videos) / video_count
    competition = round(max(1 - min(avg_field_vpd / COMPETITION_FIELD_VPD_CAP, 1.0), 0), 3)
    breakout = 1.0 if has_breakout else 0.0
    freshness = min(oldest_top_video_days / 365, 1.0)  # Older top videos = more opportunity

    signals = {
        "demand": round(demand, 3),
        "competition": round(competition, 3),
        "breakout": round(breakout, 3),
        "channel_fit": round(channel_fit, 3),
        "freshness": round(freshness, 3),
        "raw_best_vpd": round(best_vpd, 1),
        "raw_video_count": video_count,
        "raw_oldest_days": oldest_top_video_days,
    }

    # Weighted composite
    score = (
        demand * 0.30
        + competition * 0.20
        + breakout * 0.15
        + channel_fit * 0.25
        + freshness * 0.10
    )

    return round(score, 4), signals


def run_enrichment() -> list[dict]:
    """
    Enrich and score all search results.
    Deduplicates videos by video ID across queries.
    Writes data/enriched.json.
    """
    print(f"Run ID: {current_run_id(DATA_DIR)}")

    with open(DATA_DIR / "search_results.json") as f:
        search_results = json.load(f)

    print(f"Stage 3: Enriching {len(search_results)} queries...")

    # Deduplicate videos by ID across all queries
    seen_video_ids: set[str] = set()
    enriched_ideas = []

    for query, videos in search_results.items():
        unique_videos = []
        for v in videos:
            vid = v.get("id", "")
            if vid and vid not in seen_video_ids:
                seen_video_ids.add(vid)
                unique_videos.append(compute_video_scores(v))
            elif vid in seen_video_ids:
                # Video already seen from another query — still score it
                # for this idea but don't double-count in global stats
                unique_videos.append(compute_video_scores(v))

        score, signals = compute_idea_score(query, unique_videos)

        enriched_ideas.append({
            "query": query,
            "idea_score": score,
            "signals": signals,
            "videos": unique_videos,
        })

    # Sort by score descending, tie-broken alphabetically by query (v0.2).
    # The old sort-by-score-only left ties in whatever order they arrived
    # in enriched_ideas, which traces back to search_results.json's key
    # order — itself an artefact of which of Stage 2's worker threads
    # happened to finish first. Same input now always yields the same
    # ranking, regardless of thread completion order.
    enriched_ideas.sort(key=lambda x: (-x["idea_score"], x["query"]))

    print(f"Stage 3 complete: {len(enriched_ideas)} ideas scored.")

    out_path = DATA_DIR / "enriched.json"
    with open(out_path, "w") as f:
        json.dump(enriched_ideas, f, indent=2)

    print(f"Wrote {out_path} ({len(enriched_ideas)} ideas)")

    scores = [x["idea_score"] for x in enriched_ideas]
    zero_scores = sum(1 for s in scores if s == 0)
    print(f"Score range: min={min(scores) if scores else 'N/A'}, "
          f"max={max(scores) if scores else 'N/A'}, "
          f"zero-score ideas: {zero_scores}/{len(scores)}")

    print("Top 3 by score:")
    for idea in enriched_ideas[:3]:
        print(f"  - \"{idea['query']}\" score={idea['idea_score']} signals={idea['signals']}")

    return enriched_ideas


if __name__ == "__main__":
    run_enrichment()
