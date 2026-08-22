"""
Stage 6: LLM editorial gap analysis + MAKE/REJECT verdict, via Claude Code CLI.

Input:  data/survivors.json + data/captions/*.txt
Output: data/analyses/<index>.json — one analysis per idea (always written,
        even on failure — see PARSE_FAILURE_VERDICT below)
        data/stage6_stats.json — investigated/make/reject/failure counts

Uses 'claude --model <model> -p <prompt>' for each idea, sequentially (order
matches survivors.json, so verdict/ordering never depends on subprocess
completion timing). This uses your existing Claude subscription — no API
billing.

Fail-closed (v0.21): if the model's output can't be parsed, is malformed,
or lacks a valid verdict, the idea gets verdict=REJECT with a fatal_issue
recorded — never a silent drop, never a default to MAKE, never inferred
from prose. No automatic retry.

Fallback to Codex CLI is a placeholder for V2 (not wired in V1).
"""

import json
import re
import subprocess
from pathlib import Path
from config import (
    DATA_DIR, ANALYSES_DIR, CLAUDE_MODEL, MAX_CAPTION_VIDEOS_PER_IDEA,
    CHANNEL_DESCRIPTION,
)
from common import select_competitor_videos, current_run_id

VALID_VERDICTS = {"MAKE", "REJECT"}
PARSE_FAILURE_VERDICT = "REJECT"
PARSE_FAILURE_ISSUE = "editorial verdict parse failure"


def build_analysis_prompt(idea: dict, captions: list[str]) -> str:
    """
    Build the prompt for gap analysis.
    Includes: the query, competitor video metadata, and their caption text.
    Asks for: what competitors cover, what they miss, and a suggested angle.
    """
    query = idea["query"]
    # Shared selection (common.select_competitor_videos) — must match
    # Stage 5's fetch selection exactly, or captions Stage 5 downloaded
    # go silently unused here (2026-08-21 bug: 37% of slots came back
    # "(no captions available)" despite the caption existing on disk).
    videos = select_competitor_videos(idea, MAX_CAPTION_VIDEOS_PER_IDEA)

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

This analysis is for {CHANNEL_DESCRIPTION}.

EDITORIAL RULES (apply before anything else):

Gap strength and channel/scout fit are independent veto criteria.

A candidate MUST be REJECT if there is no meaningful content gap, regardless
of demand, hook or makeability.

A candidate MUST be REJECT if it does not belong to the intended
scout/content territory described above, regardless of demand, hook or
makeability.

Strong metrics do not rescue a fundamentally unsuitable idea. For example:
huge demand + easy video + no meaningful gap = REJECT. Huge demand + strong
hook + off-territory subject (e.g. franchise/movie lore that only nominally
mentions "humans") = REJECT.

Only after both GAP and FIT clear the required bar should demand, hook and
makeability be considered together when deciding MAKE versus REJECT.

Respond with ONLY a JSON object (no markdown, no backticks, no explanation) with these exact keys:
{{
  "query": "{query}",
  "what_competitors_cover": "2-3 sentence summary of what these videos cover",
  "what_competitors_miss": "2-3 sentence summary of gaps, angles, or questions none of them address",
  "suggested_angle": "One specific angle for a new video that would fill the gap",
  "gap_assessment": "adequate" or "inadequate" — is there a real, meaningful content gap?
  "fit_assessment": "adequate" or "inadequate" — does this genuinely belong to the channel's territory?
  "verdict": "MAKE" or "REJECT" — REJECT if either assessment above is "inadequate", regardless of other factors
  "confidence": "high/medium/low — how confident are you in this verdict",
  "reasoning": "1-2 sentences on why this verdict follows from the gap/fit assessments"
}}"""


def _fail_closed(query: str, index: int, reason: str) -> dict:
    """
    Build the fail-closed analysis dict for a parse/validation failure.
    Always REJECT, always a fatal_issue explaining why — never a silent
    drop, never a default to MAKE, never an inferred verdict. Still saved
    to disk like any other analysis, so the idea remains visible in the
    report's rejected list rather than vanishing without a trace.
    """
    analysis = {
        "query": query,
        "what_competitors_cover": None,
        "what_competitors_miss": None,
        "suggested_angle": None,
        "gap_assessment": None,
        "fit_assessment": None,
        "verdict": PARSE_FAILURE_VERDICT,
        "confidence": "n/a",
        "reasoning": None,
        "fatal_issue": f"{PARSE_FAILURE_ISSUE}: {reason}",
    }
    analysis_path = ANALYSES_DIR / f"{index:04d}.json"
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)
    return analysis


def analyse_idea(index: int, idea: dict, captions: list[str]) -> dict:
    """
    Run editorial gap analysis + MAKE/REJECT verdict for one idea via
    Claude Code CLI. Always returns a dict with a valid verdict — on any
    parse or validation failure, returns the fail-closed REJECT dict
    (see _fail_closed) rather than None. No retry.
    """
    query = idea["query"]
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
            return _fail_closed(query, index, f"claude CLI exited {result.returncode}")

        raw_output = result.stdout.strip()

        # Try to parse JSON from the output
        # Claude might wrap in markdown code fences despite instructions
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        if not json_match:
            print(f"  Warning: Could not parse JSON from Claude output for idea {index}")
            print(f"  Raw output (first 300 chars): {raw_output[:300]}")
            return _fail_closed(query, index, "no JSON object found in output")

        try:
            analysis = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  Warning: JSON parse error for idea {index}: {e}")
            return _fail_closed(query, index, f"JSON parse error: {e}")

        # Schema validation: verdict must be present and one of MAKE/REJECT.
        # A missing or invalid verdict is treated exactly like a parse
        # failure — fail closed, not inferred from prose elsewhere in
        # the response.
        verdict = str(analysis.get("verdict", "")).strip().upper()
        if verdict not in VALID_VERDICTS:
            print(f"  Warning: missing/invalid verdict for idea {index}: {analysis.get('verdict')!r}")
            return _fail_closed(query, index, f"missing or invalid verdict: {analysis.get('verdict')!r}")
        analysis["verdict"] = verdict

        # Save to file
        analysis_path = ANALYSES_DIR / f"{index:04d}.json"
        with open(analysis_path, "w") as f:
            json.dump(analysis, f, indent=2)

        return analysis

    except subprocess.TimeoutExpired:
        print(f"  Warning: Claude analysis timed out for idea {index}")
        return _fail_closed(query, index, "claude CLI timed out")
    except Exception as e:
        print(f"  Warning: Unexpected error for idea {index}: {e}")
        return _fail_closed(query, index, f"unexpected error: {e}")


def run_analysis() -> list[dict]:
    """
    Run editorial gap analysis + MAKE/REJECT verdict for all surviving
    ideas, sequentially (order = survivors.json order, so verdict/ordering
    never depends on subprocess completion timing — see stage4_filter.py's
    deterministic sort, preserved all the way through).
    Returns list of analysis dicts — always one per survivor, never None
    (see analyse_idea's fail-closed behaviour).
    """
    run_id = current_run_id(DATA_DIR)
    print(f"Run ID: {run_id}")

    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

    captions_dir = DATA_DIR / "captions"

    print(f"Stage 6: Running editorial analysis on {len(survivors)} ideas via Claude Code...")

    analyses = []
    for i, idea in enumerate(survivors):
        print(f"  Analysing {i+1}/{len(survivors)}: \"{idea['query'][:60]}\"")

        # Gather captions for this idea's top videos — same selection Stage 5 used
        captions = []
        for video in select_competitor_videos(idea, MAX_CAPTION_VIDEOS_PER_IDEA):
            vid = video.get("id", "")
            caption_file = captions_dir / f"{vid}.txt"
            if caption_file.exists():
                captions.append(caption_file.read_text(encoding="utf-8"))
            else:
                captions.append("(no captions available)")

        analysis = analyse_idea(i, idea, captions)
        analyses.append(analysis)

    make_count = sum(1 for a in analyses if a.get("verdict") == "MAKE")
    reject_count = sum(1 for a in analyses if a.get("verdict") == "REJECT")
    editorial_failures = sum(1 for a in analyses if a.get("fatal_issue"))

    print(f"Stage 6 complete: {len(analyses)} evaluated -> "
          f"{make_count} MAKE, {reject_count} REJECT.")
    print(f"Editorial evaluation failures: {editorial_failures}")
    print(f"Wrote analyses to {ANALYSES_DIR}")

    for i, a in enumerate(analyses[:2]):
        print(f"Sample analysis {i}: {json.dumps(a, indent=2)[:500]}")

    stats_path = DATA_DIR / "stage6_stats.json"
    with open(stats_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "investigated": len(analyses),
            "make": make_count,
            "reject": reject_count,
            "editorial_failures": editorial_failures,
        }, f, indent=2)
    print(f"Wrote {stats_path}")

    return analyses


if __name__ == "__main__":
    run_analysis()
