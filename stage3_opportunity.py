"""
Scout V2 Stage 3: deterministic opportunity enrichment.

Input:
  data/imported_channels.json

Output:
  data/opportunity_enriched.json
  data/opportunity_stage3_stats.json

This stage describes what the data says. It does not make editorial
MAKE/WATCH/REJECT decisions and does not judge factory fit or rights risk.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from typing import Any

from config import (
    DATA_DIR,
    OPPORTUNITY_IMPORTED_FILE,
    OPPORTUNITY_UPLOAD_WINDOW_DAYS,
    OPPORTUNITY_MIN_VIEWS,
    OPPORTUNITY_MIN_TRUSTED_BASELINE_VIEWS,
    OPPORTUNITY_MAX_EFFECTIVE_OUTLIER,
    OPPORTUNITY_SPAM_HASHTAG_THRESHOLD,
)
from common import current_run_id

OUTPUT_FILE = DATA_DIR / "opportunity_enriched.json"
STATS_FILE = DATA_DIR / "opportunity_stage3_stats.json"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _days_old(value: str | None, now: datetime) -> int | None:
    dt = _parse_iso(value)
    if not dt:
        return None
    return max((now - dt).days, 0)


def _median(values: list[int]) -> int | None:
    vals = [int(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0]
    return int(round(statistics.median(vals))) if vals else None


def _hashtag_count(title: str) -> int:
    return len(re.findall(r"(?<!\w)#\w+", title or ""))


def _looks_spammy(title: str) -> list[str]:
    flags = []
    hashtags = _hashtag_count(title)
    if hashtags >= OPPORTUNITY_SPAM_HASHTAG_THRESHOLD:
        flags.append(f"many_hashtags:{hashtags}")
    words = [w for w in re.split(r"\s+", title or "") if w]
    if len(words) >= 5:
        alpha = [c for c in title if c.isalpha()]
        if alpha:
            upper_ratio = sum(c.isupper() for c in alpha) / len(alpha)
            if upper_ratio >= 0.75:
                flags.append("mostly_uppercase")
    return flags


def _candidate_videos(channel: dict, now: datetime) -> list[dict]:
    """
    Prefer Stage 0's explicit candidate marker. For imported feeds that do not
    have it, infer candidates conservatively from recency + minimum views.
    """
    videos = [dict(v) for v in channel.get("videos", [])]
    explicit = [v for v in videos if v.get("is_candidate") is True]
    if explicit:
        return explicit

    inferred = []
    for v in videos:
        age = _days_old(v.get("published_at"), now)
        if age is None or age > OPPORTUNITY_UPLOAD_WINDOW_DAYS:
            continue
        if int(v.get("view_count") or 0) < OPPORTUNITY_MIN_VIEWS:
            continue
        v["is_candidate"] = True
        v["candidate_inferred"] = True
        inferred.append(v)
    return inferred


def _baseline_for(video: dict, all_videos: list[dict]) -> int | None:
    existing = video.get("baseline_views")
    if isinstance(existing, (int, float)) and not isinstance(existing, bool) and existing > 0:
        return int(existing)

    vals = [
        int(v.get("view_count") or 0)
        for v in all_videos
        if v.get("video_id") != video.get("video_id")
        and int(v.get("view_count") or 0) > 0
        and not v.get("is_candidate")
    ]
    return _median(vals)


def _enrich_candidate(video: dict, all_videos: list[dict], subs: int, now: datetime) -> dict:
    v = dict(video)
    views = int(v.get("view_count") or 0)
    baseline = _baseline_for(v, all_videos)

    raw_outlier = v.get("outlier_multiple")
    if not isinstance(raw_outlier, (int, float)) or isinstance(raw_outlier, bool):
        raw_outlier = round(views / baseline, 2) if baseline else None
    elif raw_outlier is not None:
        raw_outlier = float(raw_outlier)

    baseline_trusted = bool(baseline is not None and baseline >= OPPORTUNITY_MIN_TRUSTED_BASELINE_VIEWS)
    effective_outlier = None
    if raw_outlier is not None and baseline_trusted:
        effective_outlier = round(min(raw_outlier, OPPORTUNITY_MAX_EFFECTIVE_OUTLIER), 2)

    return {
        **v,
        "age_days": _days_old(v.get("published_at"), now),
        "baseline_views": baseline,
        "baseline_trusted": baseline_trusted,
        "raw_outlier_multiple": raw_outlier,
        "effective_outlier_multiple": effective_outlier,
        "views_per_subscriber": round(views / subs, 2) if subs > 0 else None,
        "spam_flags": _looks_spammy(v.get("title") or ""),
    }


def _data_quality(candidates: list[dict], all_videos: list[dict]) -> tuple[str, list[str]]:
    reasons = []
    if not candidates:
        return "BAD", ["no_candidate_videos"]
    if len(all_videos) < 3:
        reasons.append("thin_recent_upload_sample")
    trusted = [v for v in candidates if v.get("baseline_trusted")]
    if not trusted:
        reasons.append("no_trusted_candidate_baseline")
    spammy = sum(bool(v.get("spam_flags")) for v in candidates)
    if spammy:
        reasons.append(f"spam_flagged_candidates:{spammy}")
    if len(all_videos) < 3:
        return "BAD", reasons
    if not trusted or spammy == len(candidates):
        return "QUESTIONABLE", reasons
    return "GOOD", reasons


def _emergence(candidates: list[dict]) -> tuple[str, list[str]]:
    if not candidates:
        return "INSUFFICIENT", ["no_candidate_videos"]

    trusted = [v for v in candidates if v.get("effective_outlier_multiple") is not None]
    max_effective = max((v["effective_outlier_multiple"] for v in trusted), default=None)
    max_vps = max((v.get("views_per_subscriber") or 0 for v in candidates), default=0)
    candidate_count = len(candidates)

    reasons = []
    if max_effective is not None:
        reasons.append(f"max_trusted_outlier:{max_effective}x")
    else:
        raw = max((v.get("raw_outlier_multiple") or 0 for v in candidates), default=0)
        if raw:
            reasons.append(f"raw_outlier_untrusted:{raw}x")
    reasons.append(f"candidate_videos:{candidate_count}")
    if max_vps:
        reasons.append(f"max_views_per_subscriber:{round(max_vps, 2)}")

    # Strong requires either repeated breakout behaviour or one very clear,
    # trustworthy outlier on a small channel. Moderate is a credible single
    # breakout. Weak preserves low-baseline signals without allowing them to
    # dominate downstream ranking.
    if (candidate_count >= 2 and max_effective is not None and max_effective >= 3) or (
        max_effective is not None and max_effective >= 10
    ):
        return "STRONG", reasons
    if max_effective is not None and max_effective >= 3:
        return "MODERATE", reasons
    if max_effective is not None and max_effective >= 1.5:
        return "WEAK", reasons
    if max_vps >= 2:
        return "WEAK", reasons
    return "INSUFFICIENT", reasons


def _traction(candidates: list[dict], recent_median: int | None, subs: int) -> str:
    if subs <= 0:
        return "UNKNOWN"
    max_candidate = max((int(v.get("view_count") or 0) for v in candidates), default=0)
    median_ratio = (recent_median / subs) if recent_median is not None else 0
    candidate_ratio = max_candidate / subs if subs else 0
    if candidate_ratio >= 2 or median_ratio >= 0.5:
        return "HIGH"
    if candidate_ratio >= 1 or median_ratio >= 0.2:
        return "MEDIUM"
    return "LOW"


def enrich_channel(channel: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    all_videos = [dict(v) for v in channel.get("videos", [])]
    candidates_raw = _candidate_videos(channel, now)
    candidate_ids = {v.get("video_id") for v in candidates_raw}

    # Mark inferred candidates in the full set as well so baseline computation
    # excludes them where appropriate.
    for v in all_videos:
        if v.get("video_id") in candidate_ids:
            v["is_candidate"] = True

    subs = int(channel.get("subscriber_count") or 0)
    candidates = [_enrich_candidate(v, all_videos, subs, now) for v in candidates_raw]

    non_candidate_views = [
        int(v.get("view_count") or 0)
        for v in all_videos
        if v.get("video_id") not in candidate_ids and int(v.get("view_count") or 0) > 0
    ]
    recent_median = _median(non_candidate_views)

    quality_band, quality_reasons = _data_quality(candidates, all_videos)
    emergence_band, emergence_reasons = _emergence(candidates)

    trustworthy = [v for v in candidates if v.get("effective_outlier_multiple") is not None]
    raw_outliers = [v.get("raw_outlier_multiple") for v in candidates if v.get("raw_outlier_multiple") is not None]

    return {
        **channel,
        "candidate_videos": candidates,
        "evidence": {
            "candidate_count": len(candidates),
            "recent_upload_sample_count": len(all_videos),
            "recent_non_candidate_median_views": recent_median,
            "trusted_baseline_candidate_count": len(trustworthy),
            "raw_max_outlier_multiple": round(max(raw_outliers), 2) if raw_outliers else None,
            "effective_max_outlier_multiple": round(
                max(v["effective_outlier_multiple"] for v in trustworthy), 2
            ) if trustworthy else None,
            "max_candidate_views_per_subscriber": round(
                max((v.get("views_per_subscriber") or 0 for v in candidates), default=0), 2
            ) if subs > 0 else None,
            "discovery_query_count": len(channel.get("discovered_by_queries") or []),
        },
        "bands": {
            "data_quality": quality_band,
            "emergence_evidence": emergence_band,
            "channel_traction": _traction(candidates, recent_median, subs),
        },
        "flags": sorted(set(
            quality_reasons
            + [flag for v in candidates for flag in v.get("spam_flags", [])]
        )),
        "evidence_reasons": {
            "data_quality": quality_reasons,
            "emergence_evidence": emergence_reasons,
        },
    }


def run_opportunity_enrichment() -> dict:
    if not OPPORTUNITY_IMPORTED_FILE.exists():
        raise FileNotFoundError(
            f"Missing {OPPORTUNITY_IMPORTED_FILE}. Run Stage 0 opportunity radar first."
        )

    payload = json.loads(OPPORTUNITY_IMPORTED_FILE.read_text())
    channels = payload.get("channels")
    if not isinstance(channels, list):
        raise ValueError("imported_channels.json: channels must be a list")

    run_id = payload.get("run_id") or current_run_id(DATA_DIR)
    now = datetime.now(timezone.utc)
    enriched = [enrich_channel(c, now) for c in channels]

    # Deterministic ordering: evidence strength first, then trustworthy outlier,
    # then candidate views, then channel title. This is not a final verdict.
    emergence_rank = {"STRONG": 0, "MODERATE": 1, "WEAK": 2, "INSUFFICIENT": 3}
    quality_rank = {"GOOD": 0, "QUESTIONABLE": 1, "BAD": 2}

    def sort_key(c: dict):
        max_views = max((int(v.get("view_count") or 0) for v in c.get("candidate_videos", [])), default=0)
        return (
            emergence_rank.get(c["bands"]["emergence_evidence"], 9),
            quality_rank.get(c["bands"]["data_quality"], 9),
            -(c["evidence"].get("effective_max_outlier_multiple") or 0),
            -max_views,
            str(c.get("title") or "").lower(),
        )

    enriched.sort(key=sort_key)

    out = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "source_mode": payload.get("source_mode"),
        "channels": enriched,
    }
    OUTPUT_FILE.write_text(json.dumps(out, indent=2))

    stats = {
        "run_id": run_id,
        "channels_examined": len(enriched),
        "candidate_videos_landed": sum(c["evidence"]["candidate_count"] for c in enriched),
        "data_quality": {},
        "emergence_evidence": {},
        "channel_traction": {},
        "low_baseline_candidates": sum(
            1 for c in enriched for v in c.get("candidate_videos", [])
            if v.get("baseline_views") is not None and not v.get("baseline_trusted")
        ),
        "spam_flagged_candidates": sum(
            1 for c in enriched for v in c.get("candidate_videos", [])
            if v.get("spam_flags")
        ),
    }
    for dimension in ("data_quality", "emergence_evidence", "channel_traction"):
        counts = {}
        for c in enriched:
            band = c["bands"][dimension]
            counts[band] = counts.get(band, 0) + 1
        stats[dimension] = counts

    STATS_FILE.write_text(json.dumps(stats, indent=2))

    print(f"Stage 3 opportunity enrichment: {len(enriched)} channels")
    print(f"  candidate videos landed: {stats['candidate_videos_landed']}")
    print(f"  data quality: {stats['data_quality']}")
    print(f"  emergence: {stats['emergence_evidence']}")
    print(f"  traction: {stats['channel_traction']}")
    print(f"  low-baseline candidates: {stats['low_baseline_candidates']}")
    print(f"  spam-flagged candidates: {stats['spam_flagged_candidates']}")
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Wrote {STATS_FILE}")

    return out


if __name__ == "__main__":
    run_opportunity_enrichment()
