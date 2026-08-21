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
)


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


def run_autocomplete() -> list[str]:
    """
    Expand all seeds through autocomplete.
    Returns deduplicated list of suggestions.
    Writes results to data/autocomplete.json.
    """
    seeds = load_seeds(SEEDS_FILE)
    print(f"Stage 1: Expanding {len(seeds)} seeds x {len(AUTOCOMPLETE_SUFFIXES)} suffixes...")

    all_suggestions: set[str] = set()
    total_queries = len(seeds) * len(AUTOCOMPLETE_SUFFIXES)
    done = 0
    warnings = 0

    for seed in seeds:
        for suffix in AUTOCOMPLETE_SUFFIXES:
            suggestions = fetch_autocomplete(seed, suffix)
            if not suggestions:
                warnings += 1
            all_suggestions.update(suggestions)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{total_queries} queries done, {len(all_suggestions)} unique suggestions so far")
            time.sleep(AUTOCOMPLETE_DELAY_SECONDS)

    results = sorted(all_suggestions)
    print(f"Stage 1 complete: {len(results)} unique suggestions from {total_queries} queries "
          f"({warnings} queries returned zero suggestions).")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "autocomplete.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {out_path} ({len(results)} items)")
    sample = results[:5] if len(results) >= 5 else results
    print("Sample:")
    for s in sample:
        print(f"  - {s}")

    return results


if __name__ == "__main__":
    run_autocomplete()
