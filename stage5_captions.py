"""
Stage 5: Fetch competitor captions for surviving ideas.

Input:  data/survivors.json
Output: data/captions/<video_id>.txt — one plaintext caption file per video

Uses yt-dlp to download subtitles (auto-generated or manual).
Skips videos where captions are unavailable.
"""

import json
import re
import subprocess
from pathlib import Path
from config import (
    DATA_DIR, CAPTIONS_DIR,
    MAX_CAPTION_VIDEOS_PER_IDEA,
    CAPTION_TIMEOUT_SECONDS,
    CAPTION_LANGUAGES,
)
from common import select_competitor_videos, current_run_id


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
            if line.startswith("Kind:") or line.startswith("Language:"):
                # VTT metadata header lines — not caption content. Missed by
                # the original filter (they're neither timestamps nor digits),
                # so every caption file opened with this junk prefixed. Caught
                # during Stage 5 smoke-test verification.
                continue
            if "-->" in line:  # Timestamp line
                continue
            if line.isdigit():  # Sequence number
                continue
            # Remove HTML-style tags like <c> </c>
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
    """
    print(f"Run ID: {current_run_id(DATA_DIR)}")

    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Stage 5: Fetching captions for {len(survivors)} ideas...")

    idea_captions: dict[str, list[str]] = {}
    total_fetched = 0
    total_skipped = 0
    total_cached = 0

    for idea in survivors:
        query = idea["query"]
        # Shared selection (common.select_competitor_videos) — Stage 6 must
        # pick the exact same videos, or downloaded captions go unused.
        videos = select_competitor_videos(idea, MAX_CAPTION_VIDEOS_PER_IDEA)

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
                total_cached += 1
                continue

            caption = fetch_captions(vid, url)
            if caption:
                captions_for_idea.append(caption)
                total_fetched += 1
            else:
                total_skipped += 1

        idea_captions[query] = captions_for_idea

    total_txt_files = len(list(CAPTIONS_DIR.glob("*.txt")))
    print(f"Stage 5 complete: {total_fetched} captions fetched, {total_cached} from cache, "
          f"{total_skipped} unavailable/skipped.")
    print(f"Wrote {total_txt_files} caption files to {CAPTIONS_DIR}")

    sample_files = sorted(CAPTIONS_DIR.glob("*.txt"))[:3]
    print("Sample:")
    for f in sample_files:
        text = f.read_text(encoding="utf-8")
        print(f"  - {f.name} ({len(text)} chars): {text[:120]!r}...")

    ideas_with_zero_captions = sum(1 for v in idea_captions.values() if not any(v))
    if ideas_with_zero_captions:
        print(f"  WARNING: {ideas_with_zero_captions}/{len(survivors)} ideas got zero usable captions.")

    return idea_captions


if __name__ == "__main__":
    run_captions()
