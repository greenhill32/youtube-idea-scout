"""
Scout V2 Stage 5: lightweight format-evidence collection.

Input:
  data/opportunity_survivors.json

Outputs:
  data/opportunity_format_evidence.json
  data/opportunity_stage5_stats.json
  data/opportunity_captions/<video_id>.txt

Stage 5 does not decide whether an opportunity is good and does not classify
asset type. It packages observable evidence for Stage 6: channel title patterns,
video-length profile, candidate metadata, and (where available) one cached
candidate transcript per surviving channel.
"""

from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import (
    DATA_DIR,
    CAPTION_LANGUAGES,
    OPPORTUNITY_FORMAT_CAPTIONS_DIR,
    OPPORTUNITY_FORMAT_TRANSCRIPTS_PER_CHANNEL,
    OPPORTUNITY_FORMAT_CAPTION_TIMEOUT_SECONDS,
    OPPORTUNITY_FORMAT_TRANSCRIPT_CHAR_LIMIT,
)

INPUT_FILE = DATA_DIR / "opportunity_survivors.json"
OUTPUT_FILE = DATA_DIR / "opportunity_format_evidence.json"
STATS_FILE = DATA_DIR / "opportunity_stage5_stats.json"


def _median(values: list[int]) -> int | None:
    vals = [int(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0]
    return int(round(statistics.median(vals))) if vals else None


def _duration_band(seconds: int | None) -> str:
    if seconds is None:
        return "UNKNOWN"
    if seconds <= 180:
        return "SHORT"
    if seconds <= 900:
        return "MID"
    if seconds <= 2400:
        return "LONG"
    return "VERY_LONG"


def _title_shape(title: str) -> list[str]:
    t = (title or "").strip()
    lower = t.lower()
    flags = []
    if re.search(r"\b\d+\b", t):
        flags.append("numbered")
    if lower.startswith("why ") or " why " in lower:
        flags.append("why-question")
    if lower.startswith("how ") or " how " in lower:
        flags.append("how-explainer")
    if lower.startswith("what ") or " what " in lower:
        flags.append("what-question")
    if ":" in t:
        flags.append("colon-title")
    if "|" in t:
        flags.append("series-separator")
    if re.search(r"\bs\d+\s*e\d+\b", lower):
        flags.append("episode-label")
    if "full episode" in lower:
        flags.append("full-episode-label")
    if "documentary" in lower:
        flags.append("documentary-label")
    if "ambience" in lower or "ambient" in lower:
        flags.append("ambience-label")
    if "explained" in lower or "explainer" in lower:
        flags.append("explainer-label")
    return flags


def _common_title_shapes(videos: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for v in videos:
        for flag in _title_shape(v.get("title") or ""):
            counts[flag] = counts.get(flag, 0) + 1
    return [
        {"pattern": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _clean_vtt(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT"):
            continue
        if line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line or line.isdigit():
            continue
        clean = re.sub(r"<[^>]+>", "", line)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean and clean not in lines[-1:]:
            lines.append(clean)
    return " ".join(lines)


def _fetch_caption(video_id: str) -> tuple[str | None, str]:
    """
    Returns (caption_text, status) where status is CACHED/FETCHED/UNAVAILABLE.
    Caption failures are non-fatal: Stage 5 still retains title/duration evidence.
    """
    OPPORTUNITY_FORMAT_CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    cached = OPPORTUNITY_FORMAT_CAPTIONS_DIR / f"{video_id}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace"), "CACHED"

    if not shutil.which("yt-dlp"):
        return None, "UNAVAILABLE"

    stem = OPPORTUNITY_FORMAT_CAPTIONS_DIR / video_id
    lang_args = []
    for lang in CAPTION_LANGUAGES:
        lang_args.extend(["--sub-lang", lang])

    try:
        subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--write-sub",
                "--skip-download",
                "--sub-format", "vtt",
                *lang_args,
                "-o", str(stem),
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            text=True,
            timeout=OPPORTUNITY_FORMAT_CAPTION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, "UNAVAILABLE"

    vtts = sorted(OPPORTUNITY_FORMAT_CAPTIONS_DIR.glob(f"{video_id}*.vtt"))
    if not vtts:
        return None, "UNAVAILABLE"

    text = _clean_vtt(vtts[0].read_text(encoding="utf-8", errors="replace"))
    for path in vtts:
        try:
            path.unlink()
        except OSError:
            pass

    if not text:
        return None, "UNAVAILABLE"

    cached.write_text(text, encoding="utf-8")
    return text, "FETCHED"


def _best_candidates(channel: dict) -> list[dict]:
    candidates = [dict(v) for v in channel.get("candidate_videos") or []]
    candidates.sort(
        key=lambda v: (
            -(v.get("effective_outlier_multiple") or 0),
            -(v.get("view_count") or 0),
            str(v.get("title") or "").lower(),
        )
    )
    return candidates[:max(OPPORTUNITY_FORMAT_TRANSCRIPTS_PER_CHANNEL, 0)]


def _channel_evidence(channel: dict) -> tuple[dict, dict]:
    recent = [dict(v) for v in channel.get("videos") or []]
    durations = [int(v.get("duration_seconds") or 0) for v in recent if int(v.get("duration_seconds") or 0) > 0]
    typical = _median(durations)
    shorts = sum(1 for v in recent if v.get("is_short") is True)
    longform = sum(1 for v in recent if v.get("is_short") is False)

    transcript_records = []
    stats = {"attempted": 0, "fetched": 0, "cached": 0, "unavailable": 0}

    for candidate in _best_candidates(channel):
        vid = candidate.get("video_id") or ""
        if not vid:
            continue
        stats["attempted"] += 1
        text, status = _fetch_caption(vid)
        if status == "FETCHED":
            stats["fetched"] += 1
        elif status == "CACHED":
            stats["cached"] += 1
        else:
            stats["unavailable"] += 1
        transcript_records.append({
            "video_id": vid,
            "title": candidate.get("title"),
            "caption_status": status,
            "transcript_chars": len(text) if text else 0,
            "transcript_excerpt": (text[:OPPORTUNITY_FORMAT_TRANSCRIPT_CHAR_LIMIT] if text else None),
        })

    return {
        **channel,
        "format_evidence": {
            "recent_upload_sample_count": len(recent),
            "typical_duration_seconds": typical,
            "typical_duration_band": _duration_band(typical),
            "short_upload_count": shorts,
            "longform_upload_count": longform,
            "short_share": round(shorts / len(recent), 2) if recent else None,
            "recent_titles": [
                {
                    "video_id": v.get("video_id"),
                    "title": v.get("title"),
                    "duration_seconds": v.get("duration_seconds"),
                    "view_count": v.get("view_count"),
                    "is_candidate": bool(v.get("is_candidate")),
                }
                for v in recent
            ],
            "title_pattern_evidence": _common_title_shapes(recent),
            "candidate_transcripts": transcript_records,
            "stage4_decision": (channel.get("stage4") or {}).get("decision"),
            "stage4_review_reasons": (channel.get("stage4") or {}).get("review_reasons") or [],
        },
    }, stats


def run_opportunity_format_evidence() -> dict:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing {INPUT_FILE}. Run V2 Stage 4 first.")

    payload = json.loads(INPUT_FILE.read_text())
    channels = payload.get("channels")
    if not isinstance(channels, list):
        raise ValueError("opportunity_survivors.json: channels must be a list")

    enriched = []
    transcript_stats = {"attempted": 0, "fetched": 0, "cached": 0, "unavailable": 0}
    for channel in channels:
        record, local = _channel_evidence(channel)
        enriched.append(record)
        for key in transcript_stats:
            transcript_stats[key] += local[key]

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out = {
        "schema_version": 1,
        "run_id": payload.get("run_id"),
        "generated_at": generated_at,
        "source_mode": payload.get("source_mode"),
        "channels": enriched,
    }
    OUTPUT_FILE.write_text(json.dumps(out, indent=2))

    duration_counts = {}
    stage4_counts = {}
    channels_with_caption = 0
    channels_without_caption = 0
    for c in enriched:
        evidence = c["format_evidence"]
        band = evidence["typical_duration_band"]
        duration_counts[band] = duration_counts.get(band, 0) + 1
        decision = evidence.get("stage4_decision") or "UNKNOWN"
        stage4_counts[decision] = stage4_counts.get(decision, 0) + 1
        has_caption = any(t.get("caption_status") in {"FETCHED", "CACHED"} for t in evidence["candidate_transcripts"])
        if has_caption:
            channels_with_caption += 1
        else:
            channels_without_caption += 1

    stats = {
        "run_id": payload.get("run_id"),
        "channels_examined": len(enriched),
        "duration_band_distribution": duration_counts,
        "stage4_survivor_distribution": stage4_counts,
        "caption_attempts": transcript_stats["attempted"],
        "captions_fetched": transcript_stats["fetched"],
        "captions_cached": transcript_stats["cached"],
        "captions_unavailable": transcript_stats["unavailable"],
        "channels_with_candidate_caption": channels_with_caption,
        "channels_without_candidate_caption": channels_without_caption,
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2))

    print(f"Stage 5 format evidence: {len(enriched)} channels")
    print(f"  duration bands: {duration_counts}")
    print(f"  Stage 4 survivor states: {stage4_counts}")
    print(
        "  captions: "
        f"{transcript_stats['fetched']} fetched, "
        f"{transcript_stats['cached']} cached, "
        f"{transcript_stats['unavailable']} unavailable "
        f"of {transcript_stats['attempted']} attempted"
    )
    print(f"  channels with candidate caption: {channels_with_caption}")
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Wrote {STATS_FILE}")
    return out


if __name__ == "__main__":
    run_opportunity_format_evidence()
