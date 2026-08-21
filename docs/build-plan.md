# youtube-idea-scout — Complete Build Plan


## Build Execution Rule — Stage-Gated Development

Build this project one stage at a time.

For each stage, use this loop:

**BUILD → RUN → VERIFY → AMEND → RE-RUN → PASS**

Do not implement, scaffold, prepare, or modify any later stage until the current stage has passed verification.

For every stage:

1. **Build only the current stage**
   - Implement only the files and functionality required for that stage.
   - Do not anticipate later stages unless a shared file such as `config.py` is strictly required.

2. **Run it**
   - Execute the stage using a deliberately small smoke-test input first.
   - Do not treat successful execution alone as success.

3. **Verify the actual output**
   - Confirm the expected output file exists.
   - Inspect its contents.
   - Check structure, data types, useful values, counts, and obvious anomalies.
   - Where relevant, print a small sample to the console so the result can be visually inspected.

4. **Compare against the stage contract**
   - State what the stage was expected to return.
   - State what it actually returned.
   - Identify missing fields, empty data, incorrect values, duplicates, malformed output, warnings, or silent failures.

5. **Amend if necessary**
   - Fix only what is required to make the current stage reliable.
   - Re-run the smoke test after every amendment.
   - Do not compensate for bad output by changing a later stage.

6. **Declare PASS or FAIL**
   - Mark the stage PASS only when its output is demonstrably suitable as input for the next stage.
   - If it fails, remain on that stage and continue the build/run/verify/amend loop.

7. **STOP after PASS**
   - Show:
     - command run;
     - output produced;
     - representative sample;
     - checks performed;
     - any limitations discovered;
     - final `STAGE N: PASS`.
   - Then stop and wait for explicit instruction before beginning Stage N+1.

**Important:**
A stage that "runs without errors" has not necessarily passed. Bad, empty, incomplete, misleading, or unexpected data must be caught at the stage where it originates. The objective is that when Stage N+1 begins, the output from Stage N is already known-good and manually verified. Never build the entire pipeline and debug it afterwards.


---


## What This Is

A Python CLI tool that runs overnight (or on demand), discovers YouTube video ideas using autocomplete expansion, scores them against competitors, pulls competitor captions, and uses Claude Code to find content gaps. It produces a single `report.html` you read in the morning and decide what to make.

**It does not decide for you. It does not publish anything. It does not connect to any other system.**


## What Success Looks Like

The first report contains at least 5 ideas you'd genuinely consider making a video about, with evidence you wouldn't have found manually. If it doesn't, the architecture is wrong — not too simple.


## Principles

- No database. JSON files for intermediate data.
- No dashboard. One static HTML report.
- No agent-to-agent communication. One script, sequential stages.
- No autonomous publishing. The pipeline ends at report.html.
- No external dependencies beyond yt-dlp, Python standard library, and one LLM CLI call.
- Human judgment is the final step. Always.


---


## Project Structure

```
youtube-idea-scout/
├── config.py              # All configuration in one place
├── seeds.txt              # One seed phrase per line
├── preflight.py           # Dependency/connectivity checks
├── stage1_autocomplete.py # Seed → autocomplete expansion
├── stage2_search.py       # Expanded queries → YouTube metadata
├── stage3_enrich.py       # Raw metadata → computed scores + dedup
├── stage4_filter.py       # Score-based filtering (Python rules, optional local LLM)
├── stage5_captions.py     # Fetch competitor captions for survivors
├── stage6_analysis.py     # LLM gap analysis via Claude Code -p
├── stage7_report.py       # Assemble report.html
├── scout.py               # Main entry point — runs all stages in order
├── data/                  # Created at runtime
│   ├── autocomplete.json
│   ├── search_results.json
│   ├── enriched.json
│   ├── survivors.json
│   ├── captions/          # One .txt per video ID
│   ├── analyses/          # One .json per surviving idea
│   └── report.html        # Final output
└── templates/
    └── report_template.html  # Jinja2 or string.Template for report
```


---


## Configuration — config.py

All tuneable values live here. No magic numbers buried in stage files.

```python
"""
youtube-idea-scout configuration.
Edit values here — not in the stage files.
"""

import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
SEEDS_FILE = PROJECT_ROOT / "seeds.txt"
DATA_DIR = PROJECT_ROOT / "data"
CAPTIONS_DIR = DATA_DIR / "captions"
ANALYSES_DIR = DATA_DIR / "analyses"
REPORT_FILE = DATA_DIR / "report.html"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

# --- Autocomplete ---
AUTOCOMPLETE_SUFFIXES = list("abcdefghijklmnopqrstuvwxyz") + [""]
# Each seed phrase is expanded by appending each suffix.
# "" = bare seed with no suffix appended.
AUTOCOMPLETE_URL = "https://suggestqueries-clients6.youtube.com/complete/search"
AUTOCOMPLETE_PARAMS = {
    "client": "youtube",
    "hl": "en",
    "gl": "GB",
    # "ds": "yt",  # Uncomment if needed for YouTube-specific results
}
AUTOCOMPLETE_DELAY_SECONDS = 0.3  # Polite delay between requests

# --- Search ---
MAX_SEARCH_RESULTS_PER_QUERY = 5     # yt-dlp: how many videos per search query
MAX_CONCURRENT_SEARCHES = 4          # concurrent yt-dlp search processes
SEARCH_TIMEOUT_SECONDS = 30          # per-search timeout

# --- Enrichment / Scoring ---
MIN_VIEWS_PER_DAY = 50               # Below this = too dead to bother
MAX_SATURATION_COUNT = 20            # More than this many competing videos = saturated
BREAKOUT_VIEWS_PER_DAY = 500         # Above this = recent breakout signal
BREAKOUT_MAX_AGE_DAYS = 90           # Only count breakout if video is this young
CHANNEL_FIT_KEYWORDS = [             # Your channel's territory — ideas matching
    "psychology", "evolution",        # these score higher on channel-fit
    "human", "history", "why",
    "behaviour", "brain", "society",
    "money", "work", "body",
]

# --- Filtering ---
SURVIVOR_TARGET = 30                 # Aim for roughly this many survivors
MIN_SCORE_THRESHOLD = 0.4           # Normalised 0-1; below this = reject
USE_LOCAL_LLM_FILTER = False         # Set True to enable local LLM as tiebreaker
LOCAL_LLM_MODEL = "llama3"           # Ollama model name if local LLM is enabled
LOCAL_LLM_URL = "http://localhost:11434/api/generate"

# --- Captions ---
MAX_CAPTION_VIDEOS_PER_IDEA = 3     # Pull captions from top N competitors per idea
CAPTION_TIMEOUT_SECONDS = 30         # per-video yt-dlp subtitle timeout
CAPTION_LANGUAGES = ["en", "en-GB"]  # Preferred subtitle languages, in order

# --- Gap Analysis ---
# Primary: Claude Code CLI (subscription-based, no API billing)
ANALYSIS_PROVIDER = "claude"         # "claude" or "codex"
CLAUDE_MODEL = os.getenv("SCOUT_MODEL", "haiku")  # configurable via env var
# Fallback (not wired in V1 — placeholder for later):
# CODEX_MODEL = "gpt-5"

# --- Report ---
MAX_IDEAS_IN_REPORT = 30             # Cap the final report length
```


---


## seeds.txt

One seed phrase per line. Blank lines and lines starting with `#` are ignored.

```text
# Question seeds — high search-intent
why does
why can't
why is
how much does
what happens if
is it worth
how can I
don't

# Clickbait / hook seeds — high click-intent
you won't believe
you cannot
never do
stop doing
the real reason
nobody tells you
what they don't teach
```


---


## Preflight — preflight.py

Runs before anything else. Confirms that required tools actually work right now, not just that they're installed. If anything fails, print a clear message and exit — don't let the pipeline run and produce a silent empty report.

```python
"""
Preflight checks. Run before any pipeline stage.
Exit with a clear error if anything required is broken.
"""

import subprocess
import sys
import shutil
from urllib.request import urlopen
from config import AUTOCOMPLETE_URL


def check_yt_dlp() -> bool:
    """Verify yt-dlp is installed AND can reach YouTube."""
    if not shutil.which("yt-dlp"):
        print("PREFLIGHT FAIL: yt-dlp is not installed or not on PATH.")
        print("  Fix: pip install yt-dlp")
        return False
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "ytsearch1:test"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print("PREFLIGHT FAIL: yt-dlp is installed but YouTube search failed.")
            print(f"  stderr: {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print("PREFLIGHT FAIL: yt-dlp YouTube search timed out (30s).")
        return False
    return True


def check_autocomplete() -> bool:
    """Verify YouTube autocomplete endpoint is reachable."""
    try:
        url = f"{AUTOCOMPLETE_URL}?client=youtube&q=test"
        response = urlopen(url, timeout=10)
        if response.status != 200:
            print(f"PREFLIGHT FAIL: Autocomplete returned status {response.status}")
            return False
    except Exception as e:
        print(f"PREFLIGHT FAIL: Cannot reach YouTube autocomplete: {e}")
        return False
    return True


def check_claude_code() -> bool:
    """Verify Claude Code CLI is available."""
    if not shutil.which("claude"):
        print("PREFLIGHT FAIL: 'claude' CLI is not installed or not on PATH.")
        print("  Fix: install Claude Code — see https://docs.anthropic.com")
        return False
    # Don't run an actual prompt — just confirm the binary exists and responds.
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print("PREFLIGHT FAIL: 'claude --version' failed.")
            return False
    except subprocess.TimeoutExpired:
        print("PREFLIGHT FAIL: 'claude --version' timed out.")
        return False
    return True


def run_preflight() -> bool:
    """Run all checks. Returns True if all pass."""
    print("Running preflight checks...")
    checks = [
        ("yt-dlp", check_yt_dlp),
        ("YouTube autocomplete", check_autocomplete),
        ("Claude Code CLI", check_claude_code),
    ]
    all_ok = True
    for name, check_fn in checks:
        ok = check_fn()
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False
    if not all_ok:
        print("\nPreflight failed. Fix the above before running the scout.")
    return all_ok


if __name__ == "__main__":
    if not run_preflight():
        sys.exit(1)
    print("\nAll preflight checks passed.")
```


---


## Stage 1: Autocomplete Expansion — stage1_autocomplete.py

**Input:** `seeds.txt`
**Output:** `data/autocomplete.json`

Takes each seed phrase, appends each letter a-z (plus bare seed), hits the YouTube autocomplete endpoint, collects all suggestions. Deduplicates across seeds.

```python
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

    for seed in seeds:
        for suffix in AUTOCOMPLETE_SUFFIXES:
            suggestions = fetch_autocomplete(seed, suffix)
            all_suggestions.update(suggestions)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{total_queries} queries done, {len(all_suggestions)} unique suggestions so far")
            time.sleep(AUTOCOMPLETE_DELAY_SECONDS)

    results = sorted(all_suggestions)
    print(f"Stage 1 complete: {len(results)} unique suggestions from {total_queries} queries.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "autocomplete.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    run_autocomplete()
```

**Expected volume:** ~15 seeds x 27 suffixes = ~405 queries. At 0.3s delay = ~2 minutes. Expect 500-2000 unique suggestions after dedup.


---


## Stage 2: YouTube Search — stage2_search.py

**Input:** `data/autocomplete.json`
**Output:** `data/search_results.json`

For each autocomplete suggestion, search YouTube via yt-dlp and collect metadata for the top N results. Run searches concurrently (configurable pool size) with timeouts.

```python
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
                "--flat-playlist",    # Don't resolve every video fully
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
    with open(DATA_DIR / "autocomplete.json") as f:
        queries = json.load(f)

    print(f"Stage 2: Searching YouTube for {len(queries)} queries "
          f"({MAX_CONCURRENT_SEARCHES} concurrent workers)...")

    results: dict[str, list[dict]] = {}
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SEARCHES) as pool:
        future_to_query = {pool.submit(search_youtube, q): q for q in queries}
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                videos = future.result()
                if videos:
                    results[query] = videos
            except Exception as e:
                print(f"  Warning: worker exception for '{query}': {e}")
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(queries)} searches done")

    total_videos = sum(len(v) for v in results.values())
    print(f"Stage 2 complete: {total_videos} videos from {len(results)} queries.")

    with open(DATA_DIR / "search_results.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    run_search()
```

**Notes:**
- `--flat-playlist` makes this much faster but may return less metadata for some fields. If `view_count` or `channel_follower_count` comes back as `None`/`0` too often, switch to full resolution (slower but complete).
- yt-dlp respects YouTube rate limits. If you get 429 errors, reduce `MAX_CONCURRENT_SEARCHES` or add a delay between batches.


---


## Stage 3: Enrichment + Scoring — stage3_enrich.py

**Input:** `data/search_results.json`
**Output:** `data/enriched.json`

Deduplicate videos across queries, compute derived scores, attach them. This is pure Python — no network calls, no LLM.

```python
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
    CHANNEL_FIT_KEYWORDS,
)


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
    - competition: how many videos already exist? (lower is better)
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
        (v.get("age_days", 0) or 0) for v in videos
        if (v.get("view_count", 0) or 0) > 0
    ) if videos else 0

    query_lower = query.lower()
    fit_matches = sum(1 for kw in CHANNEL_FIT_KEYWORDS if kw in query_lower)

    # Normalise each signal to 0-1 range
    demand = min(best_vpd / 2000, 1.0)            # 2000 vpd = max demand signal
    competition = max(1 - (video_count / MAX_SATURATION_COUNT), 0)
    breakout = 1.0 if has_breakout else 0.0
    channel_fit = min(fit_matches / 2, 1.0)        # 2+ keyword matches = full fit
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

    # Sort by score descending
    enriched_ideas.sort(key=lambda x: x["idea_score"], reverse=True)

    print(f"Stage 3 complete: {len(enriched_ideas)} ideas scored. "
          f"Top score: {enriched_ideas[0]['idea_score'] if enriched_ideas else 'N/A'}")

    with open(DATA_DIR / "enriched.json", "w") as f:
        json.dump(enriched_ideas, f, indent=2)

    return enriched_ideas


if __name__ == "__main__":
    run_enrichment()
```

**Score weighting rationale:**
- `channel_fit` (0.25) — high weight because an idea outside your channel's territory is useless regardless of demand.
- `demand` (0.30) — highest weight because no views = no audience.
- `competition` (0.20) — lower competition = better opportunity.
- `breakout` (0.15) — bonus signal, not primary.
- `freshness` (0.10) — tiebreaker: stale top videos = opportunity for a fresh take.

**These weights are a starting point. Adjust after reading the first few reports.**


---


## Stage 4: Filtering — stage4_filter.py

**Input:** `data/enriched.json`
**Output:** `data/survivors.json`

Python rules first. Local LLM only as an optional tiebreaker for borderline cases — off by default.

```python
"""
Stage 4: Filter enriched ideas down to survivors.

Input:  data/enriched.json
Output: data/survivors.json — the top ideas worth analysing further

Filtering strategy:
1. Hard Python rules (score threshold, minimum demand, saturation cap)
2. If too many remain, take top N by score
3. Optional: local LLM tiebreaker for borderline cases (off by default)
"""

import json
import subprocess
from config import (
    DATA_DIR,
    SURVIVOR_TARGET,
    MIN_SCORE_THRESHOLD,
    MIN_VIEWS_PER_DAY,
    MAX_SATURATION_COUNT,
    USE_LOCAL_LLM_FILTER,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_URL,
)


def passes_hard_rules(idea: dict) -> bool:
    """Apply deterministic rejection rules."""
    if idea["idea_score"] < MIN_SCORE_THRESHOLD:
        return False
    signals = idea.get("signals", {})
    if signals.get("raw_best_vpd", 0) < MIN_VIEWS_PER_DAY:
        return False  # Topic is too dead
    if signals.get("raw_video_count", 0) >= MAX_SATURATION_COUNT:
        return False  # Too saturated
    return True


def local_llm_filter(borderline_ideas: list[dict]) -> list[dict]:
    """
    Optional: ask a local LLM (via Ollama) to pick the best from borderline ideas.
    Only called when USE_LOCAL_LLM_FILTER is True and there are too many survivors.

    The LLM receives a numbered list of idea queries with their scores
    and returns the indices of the ones worth keeping.
    """
    if not borderline_ideas:
        return []

    # Build a concise prompt — just queries and scores, no video details
    idea_list = "\n".join(
        f"{i+1}. \"{idea['query']}\" (score: {idea['idea_score']}, "
        f"demand: {idea['signals'].get('demand', '?')}, "
        f"competition: {idea['signals'].get('competition', '?')})"
        for i, idea in enumerate(borderline_ideas)
    )

    prompt = f"""You are filtering YouTube video ideas. Below is a numbered list of
candidate ideas with their scores. Pick the ones most likely to attract viewers
for a channel about human psychology, evolution, history, and "why do humans do this?"

Return ONLY a JSON array of the numbers you want to keep. Example: [1, 3, 7]

{idea_list}"""

    try:
        result = subprocess.run(
            ["curl", "-s", LOCAL_LLM_URL,
             "-d", json.dumps({
                 "model": LOCAL_LLM_MODEL,
                 "prompt": prompt,
                 "stream": False
             })],
            capture_output=True, text=True, timeout=60
        )
        response = json.loads(result.stdout)
        answer = response.get("response", "")

        # Extract JSON array from response
        import re
        match = re.search(r"\[[\d\s,]+\]", answer)
        if match:
            keep_indices = json.loads(match.group())
            return [borderline_ideas[i - 1] for i in keep_indices
                    if 1 <= i <= len(borderline_ideas)]
    except Exception as e:
        print(f"  Warning: local LLM filter failed: {e}")
        print("  Falling back to score-based cutoff.")

    return borderline_ideas  # On failure, keep all borderline ideas


def run_filter() -> list[dict]:
    """
    Filter enriched ideas to survivors.
    Writes data/survivors.json.
    """
    with open(DATA_DIR / "enriched.json") as f:
        enriched = json.load(f)

    print(f"Stage 4: Filtering {len(enriched)} ideas...")

    # Step 1: hard rules
    passed = [idea for idea in enriched if passes_hard_rules(idea)]
    rejected = len(enriched) - len(passed)
    print(f"  Hard rules: {len(passed)} passed, {rejected} rejected")

    # Step 2: if still too many, split into safe keepers and borderline
    if len(passed) <= SURVIVOR_TARGET:
        survivors = passed
    elif USE_LOCAL_LLM_FILTER:
        # Top half are safe keepers; bottom half go to LLM for tiebreaking
        safe = passed[:SURVIVOR_TARGET // 2]
        borderline = passed[SURVIVOR_TARGET // 2:]
        llm_picks = local_llm_filter(borderline)
        survivors = safe + llm_picks[:SURVIVOR_TARGET - len(safe)]
        print(f"  Local LLM kept {len(llm_picks)} from {len(borderline)} borderline ideas")
    else:
        # Just take top N by score
        survivors = passed[:SURVIVOR_TARGET]

    print(f"Stage 4 complete: {len(survivors)} survivors.")

    with open(DATA_DIR / "survivors.json", "w") as f:
        json.dump(survivors, f, indent=2)

    return survivors


if __name__ == "__main__":
    run_filter()
```


---


## Stage 5: Caption Fetch — stage5_captions.py

**Input:** `data/survivors.json`
**Output:** `data/captions/<video_id>.txt` (one file per video)

For each surviving idea, pull captions/subtitles from the top N competing videos using yt-dlp.

```python
"""
Stage 5: Fetch competitor captions for surviving ideas.

Input:  data/survivors.json
Output: data/captions/<video_id>.txt — one plaintext caption file per video

Uses yt-dlp to download subtitles (auto-generated or manual).
Skips videos where captions are unavailable.
"""

import json
import subprocess
from pathlib import Path
from config import (
    DATA_DIR, CAPTIONS_DIR,
    MAX_CAPTION_VIDEOS_PER_IDEA,
    CAPTION_TIMEOUT_SECONDS,
    CAPTION_LANGUAGES,
)


def fetch_captions(video_id: str, url: str) -> str | None:
    """
    Download captions for a single video.
    Returns caption text, or None if unavailable.
    Saves to data/captions/<video_id>.txt.
    """
    output_path = CAPTIONS_DIR / f"{video_id}"
    # yt-dlp writes <output_path>.<lang>.vtt — we'll read whatever it creates

    lang_args = []
    for lang in CAPTION_LANGUAGES:
        lang_args.extend(["--sub-lang", lang])

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",       # Fall back to auto-generated
                "--write-sub",            # Prefer manual subs
                "--skip-download",        # Don't download the video
                "--sub-format", "vtt",
                *lang_args,
                "-o", str(output_path),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=CAPTION_TIMEOUT_SECONDS,
        )

        # yt-dlp creates files like: <video_id>.en.vtt
        # Find whatever .vtt file was created
        vtt_files = list(CAPTIONS_DIR.glob(f"{video_id}*.vtt"))
        if not vtt_files:
            return None

        # Read the first matching VTT file, strip VTT formatting
        raw = vtt_files[0].read_text(encoding="utf-8", errors="replace")
        # Basic VTT cleanup: remove timestamps and formatting
        lines = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("WEBVTT"):
                continue
            if "-->" in line:  # Timestamp line
                continue
            if line.isdigit():  # Sequence number
                continue
            # Remove HTML-style tags like <c> </c>
            import re
            clean = re.sub(r"<[^>]+>", "", line)
            if clean and clean not in lines[-1:]:  # Basic dedup of repeated lines
                lines.append(clean)

        caption_text = " ".join(lines)

        # Save cleaned text
        txt_path = CAPTIONS_DIR / f"{video_id}.txt"
        txt_path.write_text(caption_text, encoding="utf-8")

        # Clean up VTT files
        for vtt in vtt_files:
            vtt.unlink()

        return caption_text

    except subprocess.TimeoutExpired:
        print(f"  Warning: caption fetch timed out for {video_id}")
        return None
    except Exception as e:
        print(f"  Warning: caption fetch failed for {video_id}: {e}")
        return None


def run_captions() -> dict[str, list[str]]:
    """
    Fetch captions for top competitors of each surviving idea.
    Returns dict mapping query → list of caption texts.
    Updates survivors.json with caption availability.
    """
    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Stage 5: Fetching captions for {len(survivors)} ideas...")

    idea_captions: dict[str, list[str]] = {}
    total_fetched = 0
    total_skipped = 0

    for idea in survivors:
        query = idea["query"]
        # Sort videos by views descending, take top N
        videos = sorted(
            idea.get("videos", []),
            key=lambda v: v.get("view_count", 0) or 0,
            reverse=True,
        )[:MAX_CAPTION_VIDEOS_PER_IDEA]

        captions_for_idea = []
        for video in videos:
            vid = video.get("id", "")
            url = video.get("url", "")
            if not vid or not url:
                continue

            # Check if we already have this caption cached
            cached = CAPTIONS_DIR / f"{vid}.txt"
            if cached.exists():
                captions_for_idea.append(cached.read_text(encoding="utf-8"))
                total_fetched += 1
                continue

            caption = fetch_captions(vid, url)
            if caption:
                captions_for_idea.append(caption)
                total_fetched += 1
            else:
                total_skipped += 1

        idea_captions[query] = captions_for_idea

    print(f"Stage 5 complete: {total_fetched} captions fetched, {total_skipped} unavailable.")

    return idea_captions


if __name__ == "__main__":
    run_captions()
```


---


## Stage 6: Gap Analysis — stage6_analysis.py

**Input:** `data/survivors.json` + `data/captions/*.txt`
**Output:** `data/analyses/<idea_index>.json` (one analysis per surviving idea)

Calls Claude Code CLI with `-p` flag for non-interactive one-shot prompts. Each surviving idea gets its own analysis call. Model is configurable via `SCOUT_MODEL` environment variable.

```python
"""
Stage 6: LLM gap analysis via Claude Code CLI.

Input:  data/survivors.json + data/captions/*.txt
Output: data/analyses/<index>.json — one analysis per idea

Uses 'claude --model <model> -p <prompt>' for each idea.
This uses your existing Claude subscription — no API billing.

Fallback to Codex CLI is a placeholder for V2 (not wired in V1).
"""

import json
import subprocess
from pathlib import Path
from config import DATA_DIR, ANALYSES_DIR, CLAUDE_MODEL, MAX_CAPTION_VIDEOS_PER_IDEA


def build_analysis_prompt(idea: dict, captions: list[str]) -> str:
    """
    Build the prompt for gap analysis.
    Includes: the query, competitor video metadata, and their caption text.
    Asks for: what competitors cover, what they miss, and a suggested angle.
    """
    query = idea["query"]
    videos = idea.get("videos", [])[:MAX_CAPTION_VIDEOS_PER_IDEA]

    competitor_section = ""
    for i, video in enumerate(videos):
        caption_text = captions[i] if i < len(captions) else "(no captions available)"
        # Truncate captions to avoid hitting context limits
        if len(caption_text) > 3000:
            caption_text = caption_text[:3000] + "... [truncated]"

        competitor_section += f"""
--- Competitor {i+1} ---
Title: {video.get('title', 'Unknown')}
Channel: {video.get('channel', 'Unknown')}
Views: {video.get('view_count', 0):,}
Views/day: {video.get('views_per_day', 0)}
URL: {video.get('url', '')}
Transcript:
{caption_text}
"""

    return f"""Analyse the YouTube content landscape for the search query: "{query}"

Below are the top competing videos with their transcripts.

{competitor_section}

Respond with ONLY a JSON object (no markdown, no backticks, no explanation) with these exact keys:
{{
  "query": "{query}",
  "what_competitors_cover": "2-3 sentence summary of what these videos cover",
  "what_competitors_miss": "2-3 sentence summary of gaps, angles, or questions none of them address",
  "suggested_angle": "One specific angle for a new video that would fill the gap",
  "confidence": "high/medium/low — how confident are you there's a real content gap",
  "reasoning": "1-2 sentences on why this angle would work"
}}"""


def analyse_idea(index: int, idea: dict, captions: list[str]) -> dict | None:
    """
    Run gap analysis for one idea via Claude Code CLI.
    Returns parsed analysis dict, or None on failure.
    """
    prompt = build_analysis_prompt(idea, captions)

    try:
        result = subprocess.run(
            [
                "claude",
                "--model", CLAUDE_MODEL,
                "-p", prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout per analysis
        )

        if result.returncode != 0:
            print(f"  Warning: Claude analysis failed for idea {index}: {result.stderr[:200]}")
            return None

        raw_output = result.stdout.strip()

        # Try to parse JSON from the output
        # Claude might wrap in markdown code fences despite instructions
        import re
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        if json_match:
            analysis = json.loads(json_match.group())

            # Save to file
            analysis_path = ANALYSES_DIR / f"{index:04d}.json"
            with open(analysis_path, "w") as f:
                json.dump(analysis, f, indent=2)

            return analysis

        print(f"  Warning: Could not parse JSON from Claude output for idea {index}")
        print(f"  Raw output (first 300 chars): {raw_output[:300]}")
        return None

    except subprocess.TimeoutExpired:
        print(f"  Warning: Claude analysis timed out for idea {index}")
        return None
    except json.JSONDecodeError as e:
        print(f"  Warning: JSON parse error for idea {index}: {e}")
        return None
    except Exception as e:
        print(f"  Warning: Unexpected error for idea {index}: {e}")
        return None


def run_analysis() -> list[dict]:
    """
    Run gap analysis for all surviving ideas.
    Returns list of analysis dicts (may contain None for failures).
    """
    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

    # Load captions
    from stage5_captions import run_captions
    # If captions were already fetched, load from cache
    captions_dir = DATA_DIR / "captions"

    print(f"Stage 6: Running gap analysis on {len(survivors)} ideas via Claude Code...")

    analyses = []
    for i, idea in enumerate(survivors):
        print(f"  Analysing {i+1}/{len(survivors)}: \"{idea['query'][:60]}\"")

        # Gather captions for this idea's top videos
        captions = []
        for video in idea.get("videos", [])[:MAX_CAPTION_VIDEOS_PER_IDEA]:
            vid = video.get("id", "")
            caption_file = captions_dir / f"{vid}.txt"
            if caption_file.exists():
                captions.append(caption_file.read_text(encoding="utf-8"))
            else:
                captions.append("(no captions available)")

        analysis = analyse_idea(i, idea, captions)
        analyses.append(analysis)

    successful = sum(1 for a in analyses if a is not None)
    print(f"Stage 6 complete: {successful}/{len(survivors)} analyses succeeded.")

    return analyses


if __name__ == "__main__":
    run_analysis()
```

**Why sequential, not concurrent for this stage:** Each Claude Code `-p` call uses your subscription quota. Running them in parallel doesn't save quota and risks rate limiting. Sequential is fine — 30 ideas at ~30 seconds each = ~15 minutes.


---


## Stage 7: Report Generation — stage7_report.py

**Input:** `data/survivors.json` + `data/analyses/*.json`
**Output:** `data/report.html`

Assembles a single static HTML file. No JavaScript framework, no build step — just Python string formatting or `string.Template`.

```python
"""
Stage 7: Generate report.html from survivors and analyses.

Input:  data/survivors.json + data/analyses/*.json
Output: data/report.html

One self-contained HTML file. No external dependencies.
Opens in any browser. Designed for morning reading.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from config import DATA_DIR, ANALYSES_DIR, REPORT_FILE, MAX_IDEAS_IN_REPORT


def load_analyses() -> dict[int, dict]:
    """Load all analysis JSON files, keyed by index."""
    analyses = {}
    for f in sorted(ANALYSES_DIR.glob("*.json")):
        try:
            index = int(f.stem)
            analyses[index] = json.loads(f.read_text())
        except (ValueError, json.JSONDecodeError):
            continue
    return analyses


def confidence_colour(confidence: str) -> str:
    """CSS colour for confidence level."""
    return {
        "high": "#22c55e",
        "medium": "#eab308",
        "low": "#ef4444",
    }.get(confidence.lower(), "#888")


def score_bar(score: float) -> str:
    """HTML for a simple visual score bar."""
    pct = int(score * 100)
    colour = "#22c55e" if pct >= 70 else "#eab308" if pct >= 40 else "#ef4444"
    return f'''<div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle">
        <div style="background:{colour};height:100%;width:{pct}%;border-radius:4px"></div>
    </div> <span style="font-size:0.85em;color:#666">{pct}%</span>'''


def generate_report() -> str:
    """Build the full HTML report."""
    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    analyses = load_analyses()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Limit to configured maximum
    survivors = survivors[:MAX_IDEAS_IN_REPORT]

    # Build idea cards
    cards_html = ""
    for i, idea in enumerate(survivors):
        query = idea["query"]
        score = idea["idea_score"]
        signals = idea.get("signals", {})
        analysis = analyses.get(i, {})

        # Competitor video rows
        video_rows = ""
        for v in idea.get("videos", [])[:3]:
            video_rows += f"""<tr>
                <td style="padding:4px 8px"><a href="{v.get('url', '#')}" target="_blank"
                    style="color:#2563eb;text-decoration:none">{v.get('title', 'Unknown')[:80]}</a></td>
                <td style="padding:4px 8px;text-align:right">{v.get('view_count', 0):,}</td>
                <td style="padding:4px 8px;text-align:right">{v.get('views_per_day', 0):,.0f}</td>
                <td style="padding:4px 8px">{v.get('channel', 'Unknown')}</td>
            </tr>"""

        # Analysis section
        analysis_html = ""
        if analysis:
            conf = analysis.get("confidence", "unknown")
            analysis_html = f"""
            <div style="margin-top:12px;padding:12px;background:#f0fdf4;border-radius:6px;border-left:3px solid {confidence_colour(conf)}">
                <div style="font-weight:600;margin-bottom:6px">
                    Gap Analysis
                    <span style="font-size:0.8em;padding:2px 6px;border-radius:3px;
                        background:{confidence_colour(conf)};color:white;margin-left:8px">
                        {conf} confidence
                    </span>
                </div>
                <p style="margin:4px 0"><strong>Competitors cover:</strong> {analysis.get('what_competitors_cover', 'N/A')}</p>
                <p style="margin:4px 0"><strong>Competitors miss:</strong> {analysis.get('what_competitors_miss', 'N/A')}</p>
                <p style="margin:4px 0;padding:8px;background:#dcfce7;border-radius:4px">
                    <strong>Suggested angle:</strong> {analysis.get('suggested_angle', 'N/A')}
                </p>
                <p style="margin:4px 0;font-size:0.9em;color:#666"><em>{analysis.get('reasoning', '')}</em></p>
            </div>"""
        else:
            analysis_html = '<div style="margin-top:12px;padding:8px;background:#fef3c7;border-radius:4px;font-size:0.9em">Gap analysis not available for this idea.</div>'

        cards_html += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px;background:white">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <h3 style="margin:0;font-size:1.1em">#{i+1} — "{query}"</h3>
                <div>{score_bar(score)}</div>
            </div>
            <div style="display:flex;gap:16px;font-size:0.85em;color:#666;margin-bottom:12px">
                <span>Demand: {signals.get('demand', '?')}</span>
                <span>Competition: {signals.get('competition', '?')}</span>
                <span>Breakout: {'Yes' if signals.get('breakout', 0) > 0 else 'No'}</span>
                <span>Channel fit: {signals.get('channel_fit', '?')}</span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:0.9em;margin-bottom:8px">
                <thead>
                    <tr style="border-bottom:1px solid #e5e7eb;text-align:left">
                        <th style="padding:4px 8px">Video</th>
                        <th style="padding:4px 8px;text-align:right">Views</th>
                        <th style="padding:4px 8px;text-align:right">Views/day</th>
                        <th style="padding:4px 8px">Channel</th>
                    </tr>
                </thead>
                <tbody>{video_rows}</tbody>
            </table>
            {analysis_html}
        </div>"""

    # Full HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Idea Scout Report — {now}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f9fafb;
            color: #1f2937;
        }}
        a {{ color: #2563eb; }}
    </style>
</head>
<body>
    <h1 style="margin-bottom:4px">YouTube Idea Scout Report</h1>
    <p style="color:#6b7280;margin-top:0">Generated {now} — {len(survivors)} ideas scored and analysed</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">
    {cards_html}
    <p style="text-align:center;color:#9ca3af;font-size:0.85em;margin-top:32px">
        End of report. Open competitor links in new tabs. Your call what to make.
    </p>
</body>
</html>"""

    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"Stage 7 complete: report written to {REPORT_FILE}")
    return html


if __name__ == "__main__":
    generate_report()
```


---


## Main Entry Point — scout.py

```python
"""
youtube-idea-scout — main entry point.

Runs all stages in order:
  preflight → autocomplete → search → enrich → filter → captions → analysis → report

Usage:
  python scout.py            # Full run
  python scout.py --from 5   # Resume from stage 5 (captions)
  python scout.py --preflight # Preflight checks only
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

from config import DATA_DIR
from preflight import run_preflight
from stage1_autocomplete import run_autocomplete
from stage2_search import run_search
from stage3_enrich import run_enrichment
from stage4_filter import run_filter
from stage5_captions import run_captions
from stage6_analysis import run_analysis
from stage7_report import generate_report


def main():
    parser = argparse.ArgumentParser(description="YouTube Idea Scout")
    parser.add_argument("--from", dest="from_stage", type=int, default=1,
                        help="Resume from stage N (1-7)")
    parser.add_argument("--preflight", action="store_true",
                        help="Run preflight checks only")
    args = parser.parse_args()

    print(f"=== YouTube Idea Scout ===")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    # Always run preflight
    if not run_preflight():
        sys.exit(1)
    print()

    if args.preflight:
        return

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    stages = [
        (1, "Autocomplete expansion", run_autocomplete),
        (2, "YouTube search", run_search),
        (3, "Enrichment + scoring", run_enrichment),
        (4, "Filtering", run_filter),
        (5, "Caption fetch", run_captions),
        (6, "Gap analysis", run_analysis),
        (7, "Report generation", generate_report),
    ]

    for stage_num, name, fn in stages:
        if stage_num < args.from_stage:
            print(f"Stage {stage_num}: {name} — SKIPPED (resuming from {args.from_stage})")
            continue

        print(f"\n{'='*60}")
        print(f"Stage {stage_num}: {name}")
        print(f"{'='*60}")

        try:
            fn()
        except Exception as e:
            print(f"\nFATAL: Stage {stage_num} ({name}) failed: {e}")
            print(f"Fix the error and resume with: python scout.py --from {stage_num}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"DONE — report at: {DATA_DIR / 'report.html'}")
    print(f"Finished: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
```


---


## Dependencies

Minimal. No requirements.txt needed for V1 if these are already installed:

```
Python 3.10+          (for type hint syntax)
yt-dlp                pip install yt-dlp
Claude Code CLI       (already installed via your subscription)
```

**Optional (only if USE_LOCAL_LLM_FILTER is enabled):**
```
Ollama                (running locally with a model pulled)
curl                  (used to call Ollama API — preinstalled on most systems)
```

No other Python packages required. The entire tool uses only the standard library plus yt-dlp as a CLI subprocess.


---


## Expected Runtime

| Stage | What | Approx. time |
|-------|------|-------------|
| 1 | Autocomplete expansion (~405 queries at 0.3s delay) | ~2 min |
| 2 | YouTube search (~500-2000 queries, 4 concurrent) | ~15-30 min |
| 3 | Enrichment + scoring (pure Python, no I/O) | <5 sec |
| 4 | Filtering (pure Python, no I/O) | <1 sec |
| 5 | Caption fetch (~30 ideas x 3 videos = ~90 fetches) | ~5-10 min |
| 6 | Gap analysis (~30 Claude calls at ~30s each) | ~15 min |
| 7 | Report generation (pure Python) | <1 sec |
| **Total** | | **~40-60 min** |

This fits comfortably in an overnight window, even with conservative delays.


---


## Error Handling Strategy

Every stage writes its output to a JSON file before the next stage begins. This means:

1. If stage 3 crashes, you can fix it and run `python scout.py --from 3` — stages 1-2 results are still on disk.
2. If a single yt-dlp call fails within a stage, the stage logs a warning and continues with remaining items — one bad video doesn't kill the whole run.
3. If Claude Code fails for one idea, that idea gets "Gap analysis not available" in the report — it doesn't prevent the other 29 from being analysed.
4. Preflight catches systemic failures (yt-dlp broken, YouTube down, Claude CLI missing) before any work starts.

**No silent failures.** Every warning prints to stdout. The report visually flags ideas where analysis failed. An empty report (0 survivors) prints a clear message rather than an empty HTML file.


---


## V2 Additions (Not In This Build)

These are documented here so they don't sneak into V1. Each is gated behind: "does the first report contain 5 ideas worth making?"

- **Codex CLI as fallback provider** for gap analysis (clean subscription-based fallback when Claude quota runs out)
- **Google Trends cross-check** as an additional scoring signal in Stage 3
- **TikTok Creative Center** trending hashtag data as a demand signal
- **Autocomplete diff** — compare today's autocomplete vs yesterday's to flag newly appearing phrases
- **Scheduled overnight run** via cron/launchd
- **"Promote to Factory"** — a manual command that copies a chosen idea into the YouTube Factory pipeline input format
- **Stale niche detection** — flag niches where the leading videos are surprisingly old
- **Multi-competitor transcript comparison** — find questions none of the top videos answer


---


## Build Sequence for the Builder

If you are an AI agent building this project, follow this exact order:

1. Create the directory structure: `youtube-idea-scout/`, `data/`, `templates/`
2. Write `config.py` — all constants, all paths, all thresholds
3. Write `seeds.txt` — the seed phrases
4. Write `preflight.py` — test it: `python preflight.py`
5. Write `stage1_autocomplete.py` — test it: `python stage1_autocomplete.py`, verify `data/autocomplete.json` has hundreds of entries
6. Write `stage2_search.py` — test it: `python stage2_search.py`, verify `data/search_results.json` has video metadata
7. Write `stage3_enrich.py` — test it: `python stage3_enrich.py`, verify `data/enriched.json` has scores between 0 and 1
8. Write `stage4_filter.py` — test it: `python stage4_filter.py`, verify `data/survivors.json` has ~20-30 ideas
9. Write `stage5_captions.py` — test it: `python stage5_captions.py`, verify `data/captions/` has .txt files
10. Write `stage6_analysis.py` — test it: `python stage6_analysis.py`, verify `data/analyses/` has .json files with gap analysis
11. Write `stage7_report.py` — test it: `python stage7_report.py`, verify `data/report.html` opens in a browser and looks correct
12. Write `scout.py` — test full run: `python scout.py`
13. Test resume: kill mid-run, then `python scout.py --from <stage>` — confirm it picks up from cached JSON

**Test each stage individually before wiring them together.**
**Do not add features not described in this document.**
**Do not add a database, dashboard, web server, or any autonomous publishing.**

**Verification output — required for every stage, to support the stage-gated build rule above:**

Each stage's `__main__` block must print, at minimum:
- the output file path it just wrote;
- a count of records/items produced (suggestions, videos, ideas, survivors, captions, analyses — whichever applies);
- a representative sample of 2-3 entries printed to console (not just "N items done"), so the result can be visually inspected without opening the JSON file separately;
- any warnings or skipped/failed items encountered during the run, with counts.

This is not a separate inspection script — it's the stage's own summary output, and it's what "Run it" and "Verify the actual output" (steps 2-3 of the Build Execution Rule) check against. A stage that only prints "Stage N complete" does not give the builder enough to compare against the stage contract in step 4.
