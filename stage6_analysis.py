"""
Stage 6: LLM gap analysis via Claude Code CLI.

Input:  data/survivors.json + data/captions/*.txt
Output: data/analyses/<index>.json — one analysis per idea

Uses 'claude --model <model> -p <prompt>' for each idea.
This uses your existing Claude subscription — no API billing.

Fallback to Codex CLI is a placeholder for V2 (not wired in V1).
"""

import json
import re
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
    print(f"Wrote analyses to {ANALYSES_DIR}")

    for i, a in enumerate(analyses[:2]):
        if a:
            print(f"Sample analysis {i}: {json.dumps(a, indent=2)[:500]}")

    failed = len(survivors) - successful
    if failed:
        print(f"  WARNING: {failed}/{len(survivors)} ideas have no analysis "
              f"(report will show 'not available' for these).")

    return analyses


if __name__ == "__main__":
    run_analysis()
