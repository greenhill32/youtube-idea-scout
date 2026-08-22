"""
Stage 4: Filter enriched ideas down to report-worthy survivors.

Input:  data/enriched.json
Output: data/survivors.json — the ideas worth analysing further
        data/filter_stats.json — funnel counts for Stage 7's summary block

Pipeline (v0.2):
1. Eligibility — deterministic structural rules, no score bar (channel
   relevance, minimum demand, saturation cap).
2. Near-duplicate clustering — collapse ideas that are the same
   underlying opportunity in different phrasing.
3. Quality threshold — every distinct opportunity must independently
   clear MIN_SCORE_THRESHOLD. MAX_REPORT_IDEAS is a cap on how many of
   those qualifying ideas get shown, never a target to fill.
4. Zero-result fallback — if nothing clears the quality bar, show the
   best few candidates anyway, clearly labelled as not having qualified.
"""

import json
from config import (
    DATA_DIR,
    MAX_REPORT_IDEAS,
    MIN_SCORE_THRESHOLD,
    MIN_VIEWS_PER_DAY,
    MAX_SATURATION_COUNT,
    NEAR_DUPLICATE_OVERLAP_THRESHOLD,
    FALLBACK_CANDIDATE_COUNT,
)
from common import current_run_id


def passes_eligibility(idea: dict) -> bool:
    """Structural legitimacy only — not a quality judgement, no score bar."""
    signals = idea.get("signals", {})
    if signals.get("channel_fit", 0) <= 0:
        # Hard relevance gate (2026-08-21 relevance fix, carried into v0.2
        # unchanged). channel_fit is now weighted/topical rather than a
        # raw "why"+"humans" count, but the gate logic is the same: zero
        # topical connection to the channel is disqualifying.
        return False
    if signals.get("raw_best_vpd", 0) < MIN_VIEWS_PER_DAY:
        return False  # Topic is too dead
    if signals.get("raw_video_count", 0) >= MAX_SATURATION_COUNT:
        return False  # Too saturated
    return True


def passes_quality(idea: dict) -> bool:
    """The final quality bar. Never lowered to fill report slots."""
    return idea["idea_score"] >= MIN_SCORE_THRESHOLD


def _video_signature(idea: dict) -> frozenset:
    return frozenset(v.get("id") for v in idea.get("videos", []) if v.get("id"))


def dedupe_near_duplicates(ideas: list[dict]) -> list[dict]:
    """
    Collapse ideas that are the same underlying opportunity in different
    phrasing, e.g. "why are humans apex predators" / "why are humans
    considered apex predators" / "why are humans top of the food chain".
    These share no useful token overlap ("apex predator" and "top of the
    food chain" are synonyms, not shared words) so word-overlap dedup
    would miss them. Instead this uses competing-video overlap: if two
    queries' top search results are substantially the same videos, they
    are the same real-world opportunity, regardless of phrasing — a
    deterministic signal already present in the data, no LLM needed.

    `ideas` must already be sorted best-first (score desc, then query —
    see Stage 3). The first idea in a cluster becomes the representative;
    the rest are folded in as alternate_phrasings. Because the ordering
    is deterministic, so is which idea becomes the representative.
    """
    representatives: list[dict] = []
    signatures: list[frozenset] = []

    for idea in ideas:
        sig = _video_signature(idea)
        matched_index = None
        if sig:
            for i, rep_sig in enumerate(signatures):
                union = sig | rep_sig
                if not union:
                    continue
                overlap = len(sig & rep_sig) / len(union)
                if overlap >= NEAR_DUPLICATE_OVERLAP_THRESHOLD:
                    matched_index = i
                    break

        if matched_index is not None:
            representatives[matched_index]["alternate_phrasings"].append(idea["query"])
        else:
            rep = dict(idea)
            rep["alternate_phrasings"] = []
            representatives.append(rep)
            signatures.append(sig)

    return representatives


def run_filter() -> dict:
    """
    Filter enriched ideas to survivors.
    Writes data/survivors.json and data/filter_stats.json.
    """
    run_id = current_run_id(DATA_DIR)
    print(f"Run ID: {run_id}")

    with open(DATA_DIR / "enriched.json") as f:
        enriched = json.load(f)  # already sorted deterministically by Stage 3

    print(f"Stage 4: Filtering {len(enriched)} candidates...")

    eligible = [idea for idea in enriched if passes_eligibility(idea)]
    print(f"  Eligibility: {len(eligible)} passed, {len(enriched) - len(eligible)} rejected")

    deduped = dedupe_near_duplicates(eligible)
    merged = len(eligible) - len(deduped)
    print(f"  Near-duplicate clustering: {len(deduped)} distinct opportunities "
          f"({merged} phrasing(s) merged into an existing opportunity)")

    qualifying = [idea for idea in deduped if passes_quality(idea)]
    print(f"  Quality threshold (score >= {MIN_SCORE_THRESHOLD}): {len(qualifying)} passed")

    is_fallback = False
    if qualifying:
        survivors = qualifying[:MAX_REPORT_IDEAS]
        if len(qualifying) > MAX_REPORT_IDEAS:
            print(f"  {len(qualifying)} qualified; report capped at "
                  f"MAX_REPORT_IDEAS={MAX_REPORT_IDEAS} -> showing top {len(survivors)}")
        else:
            print(f"  {len(qualifying)} qualified; showing all of them "
                  f"(MAX_REPORT_IDEAS={MAX_REPORT_IDEAS} is a cap, not a target — "
                  f"unused slots were not filled with lower-quality ideas)")
    else:
        is_fallback = True
        # Fallback pool draws from ALL enriched ideas, not just eligible
        # ones — "best available candidates" per the spec, not "best
        # eligible candidates". Deduped independently of the main pipeline.
        fallback_pool = dedupe_near_duplicates(enriched)
        survivors = fallback_pool[:FALLBACK_CANDIDATE_COUNT]
        for idea in survivors:
            idea["is_fallback"] = True
        print(f"  WARNING: zero ideas passed the quality threshold. "
              f"Falling back to the best {len(survivors)} available candidate(s), "
              f"labelled BELOW NORMAL THRESHOLD / FALLBACK.")

    stats = {
        "run_id": run_id,
        "candidates_examined": len(enriched),
        "initial_eligibility_count": len(eligible),
        "distinct_after_clustering": len(deduped),
        "passing_final_threshold": len(qualifying),
        "reported": len(survivors),
        "is_fallback": is_fallback,
        "max_report_ideas": MAX_REPORT_IDEAS,
    }

    print(f"Stage 4 complete: {len(survivors)} survivors "
          f"({'FALLBACK' if is_fallback else 'quality-qualified'}).")

    out_path = DATA_DIR / "survivors.json"
    with open(out_path, "w") as f:
        json.dump(survivors, f, indent=2)
    print(f"Wrote {out_path} ({len(survivors)} survivors)")

    stats_path = DATA_DIR / "filter_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Wrote {stats_path}: {stats}")

    if survivors:
        print("Survivors (score desc):")
        for idea in survivors:
            alt = idea.get("alternate_phrasings") or []
            alt_note = f"  [+{len(alt)} alt phrasing(s)]" if alt else ""
            fb_note = "  [FALLBACK]" if idea.get("is_fallback") else ""
            print(f"  - {idea['idea_score']:.3f}  \"{idea['query']}\"{alt_note}{fb_note}")
    else:
        print("  WARNING: zero survivors at all — report will be empty. "
              "This means enriched.json itself was empty or every idea failed "
              "even the fallback dedup pool.")

    return {"survivors": survivors, "stats": stats}


if __name__ == "__main__":
    run_filter()
