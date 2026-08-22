"""
Stage 2: Search YouTube for each autocomplete suggestion.

Input:  data/autocomplete.json (list of query strings)
Output: data/search_results.json — dict mapping query → list of video metadata

Uses yt-dlp with --dump-json to get structured metadata without downloading.
Runs concurrent searches with a configurable worker pool.
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from config import (
    DATA_DIR,
    MAX_SEARCH_RESULTS_PER_QUERY,
    MAX_CONCURRENT_SEARCHES,
    SEARCH_TIMEOUT_SECONDS,
)
from common import current_run_id


def search_youtube(query: str) -> list[dict]:
    """
    Search YouTube for a query via yt-dlp.
    Returns list of dicts with keys:
      id, title, view_count, upload_date, channel, channel_follower_count,
      duration, url, description
    """
    search_term = f"ytsearch{MAX_SEARCH_RESULTS_PER_QUERY}:{query}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",
                "--no-download",
                "--no-warnings",
                # NOT using --flat-playlist: smoke-tested it and upload_date /
                # channel_follower_count came back empty on 60/60 videos, which
                # silently zeroes out Stage 3's demand/freshness/breakout scoring.
                # Full resolution is slower (~7s/query vs near-instant) but complete.
                search_term,
            ],
            capture_output=True,
            text=True,
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return []

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "view_count": data.get("view_count", 0),
                    "upload_date": data.get("upload_date", ""),  # YYYYMMDD
                    "channel": data.get("channel", data.get("uploader", "")),
                    "channel_follower_count": data.get("channel_follower_count", 0),
                    "duration": data.get("duration", 0),
                    "url": data.get("webpage_url", f"https://youtube.com/watch?v={data.get('id', '')}"),
                    "description": (data.get("description", "") or "")[:500],
                    "query": query,  # Track which query found this
                })
            except json.JSONDecodeError:
                continue
        return videos

    except subprocess.TimeoutExpired:
        print(f"  Warning: search timed out for '{query}'")
        return []
    except Exception as e:
        print(f"  Warning: search failed for '{query}': {e}")
        return []


def run_search() -> dict[str, list[dict]]:
    """
    Search YouTube for all autocomplete suggestions.
    Returns dict mapping query → list of video metadata.
    Writes results to data/search_results.json.
    """
    run_id = current_run_id(DATA_DIR)
    print(f"Run ID: {run_id}")

    with open(DATA_DIR / "autocomplete.json") as f:
        queries = json.load(f)

    print(f"Stage 2: Searching YouTube for {len(queries)} queries "
          f"({MAX_CONCURRENT_SEARCHES} concurrent workers)...")

    results: dict[str, list[dict]] = {}
    done = 0
    zero_result_queries = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SEARCHES) as pool:
        future_to_query = {pool.submit(search_youtube, q): q for q in queries}
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                videos = future.result()
                if videos:
                    results[query] = videos
                else:
                    zero_result_queries += 1
            except Exception as e:
                print(f"  Warning: worker exception for '{query}': {e}")
                zero_result_queries += 1
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(queries)} searches done")

    total_videos = sum(len(v) for v in results.values())
    print(f"Stage 2 complete: {total_videos} videos from {len(results)} queries "
          f"({zero_result_queries} queries returned zero videos).")

    out_path = DATA_DIR / "search_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {out_path} ({len(results)} queries, {total_videos} videos)")

    stats_path = DATA_DIR / "stage2_stats.json"
    with open(stats_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "queries_searched": len(queries),
            "videos_found": total_videos,
            "zero_result_queries": zero_result_queries,
        }, f, indent=2)

    sample_queries = list(results.keys())[:3]
    print("Sample:")
    for q in sample_queries:
        v = results[q][0] if results[q] else {}
        print(f"  - \"{q}\" -> {len(results[q])} videos, e.g. "
              f"\"{v.get('title', '?')}\" ({v.get('view_count', '?')} views, "
              f"channel={v.get('channel', '?')})")

    return results


if __name__ == "__main__":
    run_search()
