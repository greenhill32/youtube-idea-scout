"""
Scout V2 Stage 0: channel-first opportunity radar/import.

V1 never imports or calls this module.
Outputs:
  data/imported_channels.json
  data/opportunity_stage0_stats.json
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    DATA_DIR,
    OPPORTUNITY_IMPORT_DIR,
    OPPORTUNITY_IMPORTED_FILE,
    OPPORTUNITY_SOURCE_MODE,
    OPPORTUNITY_QUERIES,
    OPPORTUNITY_UPLOAD_WINDOW_DAYS,
    OPPORTUNITY_SEARCH_RESULTS_PER_QUERY,
    OPPORTUNITY_MIN_VIEWS,
    OPPORTUNITY_MAX_SUBSCRIBERS,
    OPPORTUNITY_RECENT_UPLOADS_FOR_BASELINE,
    OPPORTUNITY_SEARCH_TIMEOUT_SECONDS,
    OPPORTUNITY_FRESH_DAYS,
    OPPORTUNITY_ACCEPTABLE_DAYS,
    OPPORTUNITY_DISCOVERY_ONLY_DAYS,
    OPPORTUNITY_WATCHLIST_DB,
)
from common import current_run_id

SCHEMA_VERSION = 1


class OpportunityImportError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OpportunityImportError(f"{field}: expected non-empty ISO-8601 UTC string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OpportunityImportError(f"{field}: invalid ISO-8601 timestamp {value!r}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise OpportunityImportError(f"{field}: timestamp must be UTC")
    return dt.astimezone(timezone.utc)


def _age_band(fetched_at: datetime, now: datetime | None = None) -> tuple[str, int]:
    age = max(((now or _now()) - fetched_at).days, 0)
    if age <= OPPORTUNITY_FRESH_DAYS:
        return "FRESH", age
    if age <= OPPORTUNITY_ACCEPTABLE_DAYS:
        return "ACCEPTABLE", age
    if age <= OPPORTUNITY_DISCOVERY_ONLY_DAYS:
        return "DISCOVERY_ONLY", age
    raise OpportunityImportError(
        f"fetched_at: feed is {age} days old; maximum is {OPPORTUNITY_DISCOVERY_ONLY_DAYS} days"
    )


def _need(obj: dict, keys: tuple[str, ...], ctx: str) -> None:
    for key in keys:
        if key not in obj:
            raise OpportunityImportError(f"{ctx}.{key}: missing required field")


def _str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpportunityImportError(f"{field}: expected non-empty string")
    return value


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpportunityImportError(f"{field}: expected non-negative integer")
    return value


def _video(v: Any, ctx: str) -> dict:
    if not isinstance(v, dict):
        raise OpportunityImportError(f"{ctx}: expected object")
    _need(v, ("video_id", "title", "published_at", "view_count", "duration_seconds", "is_short"), ctx)
    _parse_utc(v["published_at"], f"{ctx}.published_at")
    if not isinstance(v["is_short"], bool):
        raise OpportunityImportError(f"{ctx}.is_short: expected boolean")
    return {
        "video_id": _str(v["video_id"], f"{ctx}.video_id"),
        "title": _str(v["title"], f"{ctx}.title"),
        "published_at": v["published_at"],
        "view_count": _int(v["view_count"], f"{ctx}.view_count"),
        "duration_seconds": _int(v["duration_seconds"], f"{ctx}.duration_seconds"),
        "is_short": v["is_short"],
        "baseline_views": None,
        "outlier_multiple": None,
    }


def _channel(c: Any, ctx: str) -> dict:
    if not isinstance(c, dict):
        raise OpportunityImportError(f"{ctx}: expected object")
    _need(c, ("channel_id", "title", "subscriber_count", "video_count", "created_at", "country", "videos"), ctx)
    channel_id = _str(c["channel_id"], f"{ctx}.channel_id")
    if not channel_id.startswith("UC"):
        raise OpportunityImportError(f"{ctx}.channel_id: expected canonical UC... channel id")
    if c["created_at"] is not None:
        _parse_utc(c["created_at"], f"{ctx}.created_at")
    country = c["country"]
    if country is not None:
        country = _str(country, f"{ctx}.country").upper()
        if len(country) != 2 or not country.isalpha():
            raise OpportunityImportError(f"{ctx}.country: expected ISO-2 code or null")
    if not isinstance(c["videos"], list):
        raise OpportunityImportError(f"{ctx}.videos: expected array")
    return {
        "channel_id": channel_id,
        "title": _str(c["title"], f"{ctx}.title"),
        "subscriber_count": _int(c["subscriber_count"], f"{ctx}.subscriber_count"),
        "video_count": _int(c["video_count"], f"{ctx}.video_count"),
        "created_at": c["created_at"],
        "country": country,
        "videos": [_video(v, f"{ctx}.videos[{i}]") for i, v in enumerate(c["videos"])],
    }


def validate_external_feed(payload: Any, filename: str, *, now: datetime | None = None) -> dict:
    if not isinstance(payload, dict):
        raise OpportunityImportError(f"{filename}: root must be an object")
    _need(payload, ("source", "fetched_at", "schema_version", "channels"), filename)
    if payload["schema_version"] != SCHEMA_VERSION:
        raise OpportunityImportError(
            f"{filename}.schema_version: expected {SCHEMA_VERSION}, got {payload['schema_version']!r}"
        )
    source = _str(payload["source"], f"{filename}.source")
    fetched = _parse_utc(payload["fetched_at"], f"{filename}.fetched_at")
    band, days = _age_band(fetched, now)
    if not isinstance(payload["channels"], list):
        raise OpportunityImportError(f"{filename}.channels: expected array")
    channels = []
    for i, raw in enumerate(payload["channels"]):
        c = _channel(raw, f"{filename}.channels[{i}]")
        c.update({
            "source": source,
            "sources": [source],
            "fetched_at": _iso(fetched),
            "data_age_band": band,
            "data_age_days": days,
            "discovered_by_queries": [],
        })
        channels.append(c)
    return {"source": source, "fetched_at": _iso(fetched), "data_age_band": band, "data_age_days": days, "channels": channels}


def _watch_ids() -> set[str]:
    if not OPPORTUNITY_WATCHLIST_DB.exists():
        return set()
    try:
        with sqlite3.connect(OPPORTUNITY_WATCHLIST_DB) as conn:
            return {row[0] for row in conn.execute("SELECT channel_id FROM channels")}
    except sqlite3.Error as exc:
        raise RuntimeError(f"Could not read watchlist DB: {exc}") from exc


def import_external_feeds(import_dir: Path | None = None) -> tuple[list[dict], dict]:
    import_dir = import_dir or OPPORTUNITY_IMPORT_DIR
    files = sorted(import_dir.glob("*.json")) if import_dir.exists() else []
    if not files:
        raise FileNotFoundError(f"No external opportunity feeds found in {import_dir}")
    by_id: dict[str, dict] = {}
    file_stats = []
    duplicates = 0
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise OpportunityImportError(f"{path.name}: invalid JSON line {exc.lineno}, col {exc.colno}") from exc
        feed = validate_external_feed(payload, path.name)
        file_stats.append({
            "file": path.name, "source": feed["source"], "fetched_at": feed["fetched_at"],
            "data_age_band": feed["data_age_band"], "channels": len(feed["channels"]),
        })
        for c in feed["channels"]:
            cid = c["channel_id"]
            if cid in by_id:
                duplicates += 1
                # Newer feed wins channel stats; videos are unioned by id.
                old = by_id[cid]
                newest = c if _parse_utc(c["fetched_at"], "incoming") >= _parse_utc(old["fetched_at"], "existing") else old
                other = old if newest is c else c
                vids = {v["video_id"]: v for v in other["videos"]}
                vids.update({v["video_id"]: v for v in newest["videos"]})
                newest = dict(newest)
                newest["videos"] = list(vids.values())
                newest["sources"] = sorted(set(old.get("sources", [])) | set(c.get("sources", [])))
                by_id[cid] = newest
            else:
                by_id[cid] = c
    watched = _watch_ids()
    channels = list(by_id.values())
    for c in channels:
        c["is_watched"] = c["channel_id"] in watched
    return channels, {
        "source_mode": "import",
        "files": file_stats,
        "input_files": len(files),
        "unique_channels": len(channels),
        "duplicate_channel_records_merged": duplicates,
        "already_watched": sum(c["is_watched"] for c in channels),
    }


def _yt_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) != 8:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _yt(args: list[str], timeout: int) -> list[dict]:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is required for opportunity source=self")
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-download", "--no-warnings", "--dump-json", *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"yt-dlp timed out for {args[-1]!r}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {args[-1]!r}: {result.stderr[:300]}")
    rows = []
    for line in result.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _recent_channel_videos(channel_id: str) -> tuple[list[dict], int | None]:
    rows = _yt(
        ["--playlist-end", str(OPPORTUNITY_RECENT_UPLOADS_FOR_BASELINE),
         f"https://www.youtube.com/channel/{channel_id}/videos"],
        max(OPPORTUNITY_SEARCH_TIMEOUT_SECONDS, 120),
    )
    count = next((r.get("playlist_count") for r in rows if isinstance(r.get("playlist_count"), int)), None)
    videos = []
    for row in rows:
        published = _yt_date(row.get("upload_date"))
        duration = int(row.get("duration") or 0)
        videos.append({
            "video_id": row.get("id") or "",
            "title": row.get("title") or "",
            "published_at": _iso(published) if published else None,
            "view_count": int(row.get("view_count") or 0),
            "duration_seconds": duration,
            "is_short": duration <= 180,
        })
    return videos, count


def _outlier(candidate_id: str, views: int, recent: list[dict]) -> tuple[int | None, float | None]:
    vals = [int(v["view_count"]) for v in recent if v["video_id"] != candidate_id and int(v.get("view_count") or 0) > 0]
    if not vals:
        return None, None
    baseline = int(round(statistics.median(vals)))
    return baseline, round(views / baseline, 2) if baseline else None


def collect_self_radar() -> tuple[list[dict], dict]:
    now = _now()
    cutoff = now.timestamp() - OPPORTUNITY_UPLOAD_WINDOW_DAYS * 86400
    candidate_rows: dict[str, dict] = {}
    found_by: dict[str, set[str]] = defaultdict(set)

    for query in OPPORTUNITY_QUERIES:
        for row in _yt([f"ytsearchdate{OPPORTUNITY_SEARCH_RESULTS_PER_QUERY}:{query}"], OPPORTUNITY_SEARCH_TIMEOUT_SECONDS):
            vid, cid = row.get("id") or "", row.get("channel_id") or ""
            published = _yt_date(row.get("upload_date"))
            views = int(row.get("view_count") or 0)
            subs = int(row.get("channel_follower_count") or 0)
            if not vid or not cid or not published or published.timestamp() < cutoff:
                continue
            if views < OPPORTUNITY_MIN_VIEWS or subs > OPPORTUNITY_MAX_SUBSCRIBERS:
                continue
            candidate_rows.setdefault(vid, row)
            found_by[cid].add(query)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in candidate_rows.values():
        grouped[row["channel_id"]].append(row)

    watched = _watch_ids()
    channels = []
    lookups = 0
    for cid in sorted(grouped):
        recent, video_count = _recent_channel_videos(cid)
        lookups += 1
        candidate_ids = {r["id"] for r in grouped[cid]}
        for v in recent:
            v["is_candidate"] = v["video_id"] in candidate_ids
            if v["is_candidate"]:
                v["baseline_views"], v["outlier_multiple"] = _outlier(v["video_id"], v["view_count"], recent)
            else:
                v["baseline_views"] = None
                v["outlier_multiple"] = None
        first = grouped[cid][0]
        channels.append({
            "channel_id": cid,
            "title": first.get("channel") or first.get("uploader") or cid,
            "subscriber_count": max(int(r.get("channel_follower_count") or 0) for r in grouped[cid]),
            "video_count": video_count,
            "created_at": None,
            "country": None,
            "videos": recent,
            "source": "self-collected",
            "sources": ["self-collected"],
            "fetched_at": _iso(now),
            "data_age_band": "FRESH",
            "data_age_days": 0,
            "discovered_by_queries": sorted(found_by[cid]),
            "is_watched": cid in watched,
        })
    return channels, {
        "source_mode": "self",
        "queries_searched": len(OPPORTUNITY_QUERIES),
        "candidate_videos": len(candidate_rows),
        "unique_channels": len(channels),
        "channel_lookups": lookups,
        "upload_window_days": OPPORTUNITY_UPLOAD_WINDOW_DAYS,
    }


def run_opportunity_radar(source: str | None = None) -> dict:
    source = (source or OPPORTUNITY_SOURCE_MODE).lower()
    if source not in {"self", "import"}:
        raise ValueError("Opportunity source must be 'self' or 'import'")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OPPORTUNITY_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = current_run_id(DATA_DIR)
    print(f"Stage 0: Opportunity radar (source={source}, run_id={run_id})")
    channels, stats = collect_self_radar() if source == "self" else import_external_feeds()
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _iso(_now()),
        "source_mode": source,
        "channels": channels,
    }
    OPPORTUNITY_IMPORTED_FILE.write_text(json.dumps(envelope, indent=2))
    (DATA_DIR / "opportunity_stage0_stats.json").write_text(json.dumps({"run_id": run_id, **stats}, indent=2))
    print(f"Stage 0 complete: {len(channels)} channels -> {OPPORTUNITY_IMPORTED_FILE}")
    return envelope


if __name__ == "__main__":
    run_opportunity_radar()
