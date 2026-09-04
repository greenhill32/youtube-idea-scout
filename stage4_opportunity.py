"""
Scout V2 Stage 4: conservative deterministic hard gates.

Input:
  data/opportunity_enriched.json

Outputs:
  data/opportunity_gated.json
  data/opportunity_survivors.json
  data/opportunity_stage4_stats.json

Stage 4 is deliberately conservative. It only hard-rejects when observable
metadata gives clear evidence that the format is outside the current production
ceiling, is core-dependent on risky third-party footage, requires unsustainable
cadence, or the Stage 3 evidence is unusable. Ambiguous cases are REVIEW, not
REJECT. Editorial judgement remains for later stages.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from config import (
    DATA_DIR,
    OPPORTUNITY_GATE_ASSET_REJECT_PHRASES,
    OPPORTUNITY_GATE_ASSET_REVIEW_PHRASES,
    OPPORTUNITY_GATE_PERFORMANCE_REJECT_PHRASES,
    OPPORTUNITY_GATE_PERFORMANCE_REVIEW_PHRASES,
    OPPORTUNITY_GATE_CADENCE_REJECT_PHRASES,
    OPPORTUNITY_GATE_CADENCE_REVIEW_PHRASES,
    OPPORTUNITY_GATE_REJECT_BAD_DATA,
    OPPORTUNITY_GATE_REJECT_ALL_SPAM_CANDIDATES,
)

INPUT_FILE = DATA_DIR / "opportunity_enriched.json"
OUTPUT_FILE = DATA_DIR / "opportunity_gated.json"
SURVIVORS_FILE = DATA_DIR / "opportunity_survivors.json"
STATS_FILE = DATA_DIR / "opportunity_stage4_stats.json"


def _norm(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9#+' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _evidence_text(channel: dict) -> str:
    parts = [
        channel.get("title") or "",
        " ".join(channel.get("discovered_by_queries") or []),
    ]
    for video in channel.get("candidate_videos") or []:
        parts.append(video.get("title") or "")
    return _norm(" | ".join(parts))


def _matched(text: str, phrases: list[str]) -> list[str]:
    hits = []
    for phrase in phrases:
        p = _norm(phrase)
        if p and p in text:
            hits.append(phrase)
    return sorted(set(hits))


def _dimension(text: str, reject_phrases: list[str], review_phrases: list[str]) -> dict:
    reject_hits = _matched(text, reject_phrases)
    review_hits = _matched(text, review_phrases)
    if reject_hits:
        return {
            "status": "REJECT",
            "evidence": reject_hits,
            "reason": "clear phrase match in observable channel/video metadata",
        }
    if review_hits:
        return {
            "status": "REVIEW",
            "evidence": review_hits,
            "reason": "possible dependency detected; requires later editorial confirmation",
        }
    return {
        "status": "PASS",
        "evidence": [],
        "reason": "no clear dependency found in current metadata",
    }


def _data_gate(channel: dict) -> dict:
    quality = (channel.get("bands") or {}).get("data_quality")
    candidates = channel.get("candidate_videos") or []

    if OPPORTUNITY_GATE_REJECT_BAD_DATA and quality == "BAD":
        return {
            "status": "REJECT",
            "evidence": ["data_quality:BAD"],
            "reason": "Stage 3 evidence is too incomplete to support downstream judgement",
        }

    if candidates and OPPORTUNITY_GATE_REJECT_ALL_SPAM_CANDIDATES:
        spammy = [v for v in candidates if v.get("spam_flags")]
        if len(spammy) == len(candidates):
            return {
                "status": "REJECT",
                "evidence": ["all_candidate_videos_spam_flagged"],
                "reason": "all landed candidate evidence is spam-flagged",
            }

    if quality == "QUESTIONABLE":
        return {
            "status": "REVIEW",
            "evidence": ["data_quality:QUESTIONABLE"],
            "reason": "usable but uncertain Stage 3 evidence",
        }

    return {
        "status": "PASS",
        "evidence": [],
        "reason": "Stage 3 evidence is usable",
    }


def gate_channel(channel: dict) -> dict:
    text = _evidence_text(channel)

    gates = {
        "data_quality": _data_gate(channel),
        "asset_dependency": _dimension(
            text,
            OPPORTUNITY_GATE_ASSET_REJECT_PHRASES,
            OPPORTUNITY_GATE_ASSET_REVIEW_PHRASES,
        ),
        "performance_dependency": _dimension(
            text,
            OPPORTUNITY_GATE_PERFORMANCE_REJECT_PHRASES,
            OPPORTUNITY_GATE_PERFORMANCE_REVIEW_PHRASES,
        ),
        "cadence_dependency": _dimension(
            text,
            OPPORTUNITY_GATE_CADENCE_REJECT_PHRASES,
            OPPORTUNITY_GATE_CADENCE_REVIEW_PHRASES,
        ),
    }

    statuses = [g["status"] for g in gates.values()]
    if "REJECT" in statuses:
        decision = "REJECT"
    elif "REVIEW" in statuses:
        decision = "REVIEW"
    else:
        decision = "PASS"

    reject_reasons = []
    review_reasons = []
    for name, gate in gates.items():
        if gate["status"] == "REJECT":
            reject_reasons.append(f"{name}: {gate['reason']}")
        elif gate["status"] == "REVIEW":
            review_reasons.append(f"{name}: {gate['reason']}")

    return {
        **channel,
        "stage4": {
            "decision": decision,
            "gates": gates,
            "reject_reasons": reject_reasons,
            "review_reasons": review_reasons,
        },
    }


def run_opportunity_gates() -> dict:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing {INPUT_FILE}. Run V2 Stage 3 first."
        )

    payload = json.loads(INPUT_FILE.read_text())
    channels = payload.get("channels")
    if not isinstance(channels, list):
        raise ValueError("opportunity_enriched.json: channels must be a list")

    gated = [gate_channel(c) for c in channels]
    survivors = [c for c in gated if c["stage4"]["decision"] != "REJECT"]

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    base = {
        "schema_version": 1,
        "run_id": payload.get("run_id"),
        "generated_at": generated_at,
        "source_mode": payload.get("source_mode"),
    }

    OUTPUT_FILE.write_text(json.dumps({**base, "channels": gated}, indent=2))
    SURVIVORS_FILE.write_text(json.dumps({**base, "channels": survivors}, indent=2))

    decision_counts = {}
    dimension_counts = {
        "data_quality": {},
        "asset_dependency": {},
        "performance_dependency": {},
        "cadence_dependency": {},
    }
    for c in gated:
        decision = c["stage4"]["decision"]
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        for dimension in dimension_counts:
            status = c["stage4"]["gates"][dimension]["status"]
            dimension_counts[dimension][status] = dimension_counts[dimension].get(status, 0) + 1

    stats = {
        "run_id": payload.get("run_id"),
        "channels_examined": len(gated),
        "survivors": len(survivors),
        "rejected": len(gated) - len(survivors),
        "decision_distribution": decision_counts,
        "gate_distributions": dimension_counts,
        "rejected_channels": [
            {
                "channel_id": c.get("channel_id"),
                "title": c.get("title"),
                "reasons": c["stage4"]["reject_reasons"],
            }
            for c in gated
            if c["stage4"]["decision"] == "REJECT"
        ],
        "review_channels": [
            {
                "channel_id": c.get("channel_id"),
                "title": c.get("title"),
                "reasons": c["stage4"]["review_reasons"],
            }
            for c in gated
            if c["stage4"]["decision"] == "REVIEW"
        ],
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2))

    print(f"Stage 4 opportunity gates: {len(gated)} channels examined")
    print(f"  survivors: {len(survivors)}")
    print(f"  rejected: {stats['rejected']}")
    print(f"  decisions: {decision_counts}")
    for dimension, counts in dimension_counts.items():
        print(f"  {dimension}: {counts}")
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Wrote {SURVIVORS_FILE}")
    print(f"Wrote {STATS_FILE}")

    return {**base, "channels": survivors}


if __name__ == "__main__":
    run_opportunity_gates()
