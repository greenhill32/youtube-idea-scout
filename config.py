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
    "human", "humans", "history", "why",
    "behaviour", "brain", "society",
    "money", "work", "body",
]
# "humans" (plural) added alongside "human": word-boundary matching means
# "human" alone does not match inside "humans", which would have zeroed
# channel_fit on seeds like "why can't humans" / "why are humans" — exactly
# the explanatory seeds this project wants to score well.

# --- Stage 1 pre-search junk filter ---
# Seeds that are short/generic enough to produce YouTube autocomplete
# collisions with existing song/movie/game titles rather than genuine
# video-idea phrasing (this is what happened with the old bare "don't"
# seed — removed from seeds.txt entirely, 2026-08-21 relevance fix).
# Suggestions originating ONLY from these seeds get extra scrutiny in
# Stage 1, before the expensive search/caption/analysis stages run.
WEAK_SEEDS = {
    "never do",
    "stop doing",
    "you cannot",
}
JUNK_FILTER_MAX_WORDS = 4  # "very short" query threshold for the junk filter

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
