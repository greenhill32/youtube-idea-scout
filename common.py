"""
Shared helpers used across multiple pipeline stages.

Keeping these in one place means Stage 1's query-only gate and Stage 3's
channel_fit scoring signal can never drift apart (same logic, same
weights), and Stage 5's caption downloads and Stage 6's caption reads
always refer to the exact same competitor videos.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from config import CHANNEL_FIT_KEYWORDS, CHANNEL_FIT_TARGET


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def start_run(data_dir: Path) -> str:
    """
    Called once, by Stage 1, at the start of a fresh pipeline run. Generates
    a run_id and persists it to data/run_id.txt so every later stage --
    whether run in-process via scout.py or standalone via `python stageN.py`
    -- picks up the same id without it being threaded through function args.
    """
    run_id = new_run_id()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "run_id.txt").write_text(run_id)
    return run_id


def current_run_id(data_dir: Path) -> str:
    """
    Read the run_id for any stage after Stage 1. Falls back to minting one
    (and persisting it, same as start_run) if none exists yet -- so running
    a stage standalone, with no prior Stage 1 in this data/ directory,
    never crashes for lack of a run_id.
    """
    run_id_file = data_dir / "run_id.txt"
    if run_id_file.exists():
        existing = run_id_file.read_text().strip()
        if existing:
            return existing
    return start_run(data_dir)


def channel_fit_score(query: str) -> float:
    """
    Weighted, deterministic channel-fit score for a query string, 0-1.
    Computed from the query text alone (no video/network data needed),
    so it doubles as a Stage 1 pre-search eligibility gate and as
    Stage 3's channel_fit scoring signal — one definition, used twice.

    Word-boundary matching, not substring (see stage3 changelog note on
    the "body" inside "nobody" false positive). Generic query-structure
    words like "why" carry no weight — CHANNEL_FIT_KEYWORDS deliberately
    excludes them; see config.py for why "why" dominated the old scoring.
    """
    query_lower = query.lower()
    weighted_sum = sum(
        weight for keyword, weight in CHANNEL_FIT_KEYWORDS.items()
        if re.search(rf"\b{re.escape(keyword)}\b", query_lower)
    )
    return round(min(weighted_sum / CHANNEL_FIT_TARGET, 1.0), 3)


def select_competitor_videos(idea: dict, n: int) -> list[dict]:
    """
    The single definition of "top N competitor videos" for an idea.
    Stage 5 downloads captions for exactly this selection; Stage 6 reads
    captions for exactly this same selection. Before this shared helper,
    Stage 5 sorted by view_count while Stage 6 read original search
    order — the mismatch silently dropped 37% of downloaded captions
    from the Stage 6 prompts (2026-08-21 production run).
    """
    videos = idea.get("videos", [])
    return sorted(videos, key=lambda v: v.get("view_count", 0) or 0, reverse=True)[:n]
