"""
Stage 1: Expand seed phrases via YouTube autocomplete.

Input:  seeds.txt (one phrase per line)
Output: data/autocomplete.json — list of unique autocomplete suggestions

Each seed is queried with suffixes a-z plus the bare seed itself.
YouTube autocomplete returns JSONP; we strip the wrapper and parse.
"""

import json
import time
import re
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from pathlib import Path
from config import (
    SEEDS_FILE, DATA_DIR,
    AUTOCOMPLETE_URL, AUTOCOMPLETE_PARAMS,
    AUTOCOMPLETE_SUFFIXES, AUTOCOMPLETE_DELAY_SECONDS,
    CHANNEL_FIT_KEYWORDS, WEAK_SEEDS, JUNK_FILTER_MAX_WORDS,
)
from common import channel_fit_score, start_run


def load_seeds(path: Path) -> list[str]:
    """Load seed phrases from file. Skip blanks and comments."""
    seeds = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                seeds.append(line)
    return seeds


def fetch_autocomplete(seed: str, suffix: str) -> list[str]:
    """
    Query YouTube autocomplete for a seed+suffix.
    Returns a list of suggestion strings.

    YouTube returns JSONP like:
      window.google.ac.h(["query",[["suggestion1"],["suggestion2"],...]])
    We extract the JSON array inside the parentheses.
    """
    query = f"{seed} {suffix}".strip()
    params = {**AUTOCOMPLETE_PARAMS, "q": query}
    url = f"{AUTOCOMPLETE_URL}?{urlencode(params)}"

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        response = urlopen(req, timeout=10)
        raw = response.read().decode("utf-8")

        # Extract JSON from JSONP wrapper
        # Format: window.google.ac.h( <JSON> )
        match = re.search(r"\((.+)\)\s*$", raw)
        if not match:
            return []

        data = json.loads(match.group(1))
        # data[1] is the list of suggestion arrays
        if len(data) > 1 and isinstance(data[1], list):
            return [item[0] for item in data[1] if isinstance(item, list) and item]
        return []

    except Exception as e:
        print(f"  Warning: autocomplete failed for '{query}': {e}")
        return []


def is_probable_junk(suggestion: str, origin_seeds: set[str]) -> bool:
    """
    Conservative pre-search junk filter (Stage 1, before the expensive
    search/caption/analysis stages run).

    Flags a suggestion as junk only if ALL of:
      - it's short (<= JUNK_FILTER_MAX_WORDS words) — genuine explanatory
        ideas tend to run longer than song/movie/game titles that
        autocomplete surfaces for generic seeds;
      - it contains none of CHANNEL_FIT_KEYWORDS — no topical anchor;
      - every seed that produced it is in WEAK_SEEDS — i.e. it never
        arose from an explanatory/specific seed, only a generic hook one.

    Deliberately conservative: this is not a classifier, just a filter
    for the specific failure mode seen in the 2026-08-21 500-query run
    (bare "don't" + suffix -> pop-culture title collisions).
    """
    word_count = len(suggestion.split())
    if word_count > JUNK_FILTER_MAX_WORDS:
        return False

    has_fit_keyword = any(
        re.search(rf"\b{re.escape(kw)}\b", suggestion.lower())
        for kw in CHANNEL_FIT_KEYWORDS
    )
    if has_fit_keyword:
        return False

    from_weak_seed_only = origin_seeds and origin_seeds.issubset(WEAK_SEEDS)
    if not from_weak_seed_only:
        return False

    return True


def run_autocomplete() -> list[str]:
    """
    Expand all seeds through autocomplete.
    Applies a conservative junk filter (see is_probable_junk) before
    writing output, so obvious title-collision noise from weak seeds
    doesn't reach the expensive downstream stages.
    Writes results to data/autocomplete.json (flat list of strings —
    seed provenance is tracked in-memory for filtering only, not
    persisted, so Stage 2's input contract is unchanged).
    """
    run_id = start_run(DATA_DIR)
    print(f"Run ID: {run_id}")

    seeds = load_seeds(SEEDS_FILE)
    print(f"Stage 1: Expanding {len(seeds)} seeds x {len(AUTOCOMPLETE_SUFFIXES)} suffixes...")

    origins: dict[str, set[str]] = {}  # suggestion -> set of seeds that produced it
    total_queries = len(seeds) * len(AUTOCOMPLETE_SUFFIXES)
    done = 0
    warnings = 0

    for seed in seeds:
        for suffix in AUTOCOMPLETE_SUFFIXES:
            suggestions = fetch_autocomplete(seed, suffix)
            if not suggestions:
                warnings += 1
            for s in suggestions:
                origins.setdefault(s, set()).add(seed)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{total_queries} queries done, {len(origins)} unique suggestions so far")
            time.sleep(AUTOCOMPLETE_DELAY_SECONDS)

    all_suggestions = sorted(origins.keys())
    junk = [s for s in all_suggestions if is_probable_junk(s, origins[s])]
    after_junk_filter = [s for s in all_suggestions if s not in set(junk)]

    print(f"Stage 1 raw: {len(all_suggestions)} unique suggestions from {total_queries} queries "
          f"({warnings} queries returned zero suggestions).")
    print(f"Junk filter: {len(junk)} removed, {len(after_junk_filter)} kept.")
    if junk:
        print("Sample of filtered junk:")
        for s in junk[:5]:
            print(f"  - {s}  (from: {sorted(origins[s])})")

    # Query-only eligibility gate (v0.2): channel_fit is computable from the
    # query text alone, with no video/network data. Reject zero-fit queries
    # here, before Stage 2 spends a search on them — in the 2026-08-21 run,
    # 50.7% of Stage 1 output had zero channel_fit and was guaranteed to be
    # rejected at Stage 4 anyway, after ~93 minutes of wasted searching.
    zero_fit = [s for s in after_junk_filter if channel_fit_score(s) <= 0]
    results = [s for s in after_junk_filter if channel_fit_score(s) > 0]
    print(f"Query-only channel-fit gate: {len(zero_fit)} rejected (zero topical fit), "
          f"{len(results)} eligible for search.")
    if zero_fit:
        print("Sample rejected (zero channel-fit):")
        for s in zero_fit[:5]:
            print(f"  - {s}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "autocomplete.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {out_path} ({len(results)} items)")

    stats_path = DATA_DIR / "stage1_stats.json"
    with open(stats_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "raw_suggestions": len(all_suggestions),
            "after_junk_filter": len(after_junk_filter),
            "zero_fit_rejected": len(zero_fit),
            "queries_generated": len(results),
        }, f, indent=2)
    sample = results[:5] if len(results) >= 5 else results
    print("Sample:")
    for s in sample:
        print(f"  - {s}")

    return results


if __name__ == "__main__":
    run_autocomplete()
