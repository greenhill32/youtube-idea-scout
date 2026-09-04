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
REPORTS_ARCHIVE_DIR = DATA_DIR / "reports"  # one copy per run, keyed by run_id — report.html
                                              # itself is overwritten each run, this isn't
TEMPLATE_DIR = PROJECT_ROOT / "templates"
PROGRESS_FILE = PROJECT_ROOT / "progress.txt"        # engineering memory, not a run log
RUN_HISTORY_FILE = PROJECT_ROOT / "run_history.jsonl"  # one line per completed run

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
COMPETITION_FIELD_VPD_CAP = 2000     # views/day at which the whole field counts as "saturated"

# Weighted, topical channel-fit terms (v0.2 relevance rework, 2026-08-22).
# "why" is deliberately ABSENT: in the 2026-08-21 production run it matched
# 45.9% of all Stage 1 output on its own (it's query-structure framing, not
# topic), and paired with "humans" (8.7%) it maxed out channel_fit for any
# "why are humans..." query regardless of actual subject matter — that's
# why 28/30 report cards came back as one phrase. Specific topical terms
# (psychology, evolution, behaviour...) now carry more weight than broad
# ones (human, humans, body), so two generic hits can no longer outscore
# one genuinely on-topic term.
CHANNEL_FIT_KEYWORDS = {
    "psychology": 1.0,
    "evolution": 1.0,
    "evolutionary": 1.0,
    "behaviour": 0.9,
    "behavior": 0.9,
    "brain": 0.8,
    "society": 0.7,
    "societal": 0.7,
    "history": 0.6,
    "historical": 0.6,
    "human": 0.5,
    "humans": 0.5,
    "body": 0.4,
    "money": 0.4,
    "work": 0.3,
}
CHANNEL_FIT_TARGET = 1.2  # weighted sum needed for a full 1.0 channel_fit score

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
# MAX_REPORT_IDEAS is a CAP, not a target (v0.2). Every distinct opportunity
# must independently clear MIN_SCORE_THRESHOLD; the report shows however
# many qualify, up to this cap. The threshold is never lowered to fill slots.
MAX_REPORT_IDEAS = 20
MIN_SCORE_THRESHOLD = 0.4            # Normalised 0-1; below this = reject
NEAR_DUPLICATE_OVERLAP_THRESHOLD = 0.4  # competing-video overlap fraction that
                                         # merges two ideas into one opportunity
FALLBACK_CANDIDATE_COUNT = 3         # shown, clearly labelled, when zero ideas
                                      # clear MIN_SCORE_THRESHOLD

# --- Captions ---
MAX_CAPTION_VIDEOS_PER_IDEA = 3     # Pull captions from top N competitors per idea
CAPTION_TIMEOUT_SECONDS = 30         # per-video yt-dlp subtitle timeout
CAPTION_LANGUAGES = ["en", "en-GB"]  # Preferred subtitle languages, in order

# --- Gap Analysis / Editorial Judgement ---
# Primary: Claude Code CLI (subscription-based, no API billing)
ANALYSIS_PROVIDER = "claude"         # "claude" or "codex"
CLAUDE_MODEL = os.getenv("SCOUT_MODEL", "haiku")  # configurable via env var
# Fallback (not wired in V1 — placeholder for later):
# CODEX_MODEL = "gpt-5"

# What Stage 6 judges "fit" against — kept as one string so the prompt's
# territory definition can't drift from what a human would recognise as
# on-channel. Not the same mechanism as channel_fit_score() (that's a
# cheap keyword proxy used pre-search in Stage 1/3); this is the LLM's
# actual editorial judgement call in Stage 6.
CHANNEL_DESCRIPTION = (
    "a channel about human psychology, evolution, history, and "
    "\"why do humans do this?\" explainer content"
)

# --- V2 Opportunity Mode (additive; V1 above remains unchanged) ---
OPPORTUNITY_IMPORT_DIR = DATA_DIR / "import"
OPPORTUNITY_IMPORTED_FILE = DATA_DIR / "imported_channels.json"
OPPORTUNITY_WATCHLIST_DB = DATA_DIR / "watchlist.db"

# Stage 0 radar source. Override with SCOUT_OPPORTUNITY_SOURCE=self|import.
OPPORTUNITY_SOURCE_MODE = os.getenv("SCOUT_OPPORTUNITY_SOURCE", "self")

# Broad discovery territories, not V1 hook/query seeds. These are deliberately
# production-compatible areas, not a hard editorial remit; V2 is allowed to
# discover adjacent formats.
OPPORTUNITY_QUERIES = [
    "history documentary",
    "daily life history",
    "forgotten history",
    "science documentary",
    "science what if",
    "space documentary",
    "engineering explained",
    "infrastructure documentary",
    "technology documentary",
    "business documentary",
    "geography documentary",
    "historical ambience",
    "sleep ambience",
]

OPPORTUNITY_UPLOAD_WINDOW_DAYS = int(os.getenv("SCOUT_OPPORTUNITY_WINDOW_DAYS", "7"))
OPPORTUNITY_SEARCH_RESULTS_PER_QUERY = int(os.getenv("SCOUT_OPPORTUNITY_RESULTS_PER_QUERY", "20"))
OPPORTUNITY_MIN_VIEWS = int(os.getenv("SCOUT_OPPORTUNITY_MIN_VIEWS", "10000"))
OPPORTUNITY_MAX_SUBSCRIBERS = int(os.getenv("SCOUT_OPPORTUNITY_MAX_SUBSCRIBERS", "100000"))
OPPORTUNITY_RECENT_UPLOADS_FOR_BASELINE = int(os.getenv("SCOUT_OPPORTUNITY_BASELINE_UPLOADS", "10"))
OPPORTUNITY_SEARCH_TIMEOUT_SECONDS = int(os.getenv("SCOUT_OPPORTUNITY_TIMEOUT", "60"))
OPPORTUNITY_MIN_TRUSTED_BASELINE_VIEWS = int(os.getenv("SCOUT_OPPORTUNITY_BASELINE_FLOOR", "500"))
OPPORTUNITY_MAX_EFFECTIVE_OUTLIER = float(os.getenv("SCOUT_OPPORTUNITY_OUTLIER_CAP", "50"))
OPPORTUNITY_SPAM_HASHTAG_THRESHOLD = int(os.getenv("SCOUT_OPPORTUNITY_SPAM_HASHTAGS", "4"))


# External-feed age bands. 22-45 day feeds are discovery-only: later V2
# stages must refresh their metrics before scoring.
OPPORTUNITY_FRESH_DAYS = 7
OPPORTUNITY_ACCEPTABLE_DAYS = 21
OPPORTUNITY_DISCOVERY_ONLY_DAYS = 45
OPPORTUNITY_WATCH_DAYS = 90

# Production ceiling used by later V2 scoring. "Technically possible" is not
# enough: factory-fit is about a credible repeatable test at current capability.
OPPORTUNITY_PRODUCTION_PROFILE = """
Current strengths:
- AI still imagery; pans, zooms, parallax and light motion
- narration/TTS, maps, diagrams, screenshots and charts
- ambience/sound design and occasional short AI video clips
- 8-30 minute narrated explainers and long-form ambience

Current weak areas:
- recurring character animation and lip-sync dialogue
- heavy 3D, presenter-led formats, or real-world filming
- formats whose core asset is copyrighted third-party footage
- high-frequency news/celebrity/sports production

Factory-fit anchors:
A = credible first test now, <= 1 day
B = one small production addition, <= 2-3 days
C = new workflow/tooling, roughly 1-2 weeks
D = fundamentally outside current capability
"""

# --- Report ---
# (report length is governed by MAX_REPORT_IDEAS above — Stage 4 already
# caps survivors.json, so Stage 7 doesn't need its own separate limit)
