"""
Stage 4: Filter enriched ideas down to survivors.

Input:  data/enriched.json
Output: data/survivors.json — the top ideas worth analysing further

Filtering strategy:
1. Hard Python rules (score threshold, minimum demand, saturation cap)
2. If too many remain, take top N by score
3. Optional: local LLM tiebreaker for borderline cases (off by default)
"""

import json
import subprocess
from config import (
    DATA_DIR,
    SURVIVOR_TARGET,
    MIN_SCORE_THRESHOLD,
    MIN_VIEWS_PER_DAY,
    MAX_SATURATION_COUNT,
    USE_LOCAL_LLM_FILTER,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_URL,
)


def passes_hard_rules(idea: dict) -> bool:
    """Apply deterministic rejection rules."""
    if idea["idea_score"] < MIN_SCORE_THRESHOLD:
        return False
    signals = idea.get("signals", {})
    if signals.get("raw_best_vpd", 0) < MIN_VIEWS_PER_DAY:
        return False  # Topic is too dead
    if signals.get("raw_video_count", 0) >= MAX_SATURATION_COUNT:
        return False  # Too saturated
    return True


def local_llm_filter(borderline_ideas: list[dict]) -> list[dict]:
    """
    Optional: ask a local LLM (via Ollama) to pick the best from borderline ideas.
    Only called when USE_LOCAL_LLM_FILTER is True and there are too many survivors.

    The LLM receives a numbered list of idea queries with their scores
    and returns the indices of the ones worth keeping.
    """
    if not borderline_ideas:
        return []

    # Build a concise prompt — just queries and scores, no video details
    idea_list = "\n".join(
        f"{i+1}. \"{idea['query']}\" (score: {idea['idea_score']}, "
        f"demand: {idea['signals'].get('demand', '?')}, "
        f"competition: {idea['signals'].get('competition', '?')})"
        for i, idea in enumerate(borderline_ideas)
    )

    prompt = f"""You are filtering YouTube video ideas. Below is a numbered list of
candidate ideas with their scores. Pick the ones most likely to attract viewers
for a channel about human psychology, evolution, history, and "why do humans do this?"

Return ONLY a JSON array of the numbers you want to keep. Example: [1, 3, 7]

{idea_list}"""

    try:
        result = subprocess.run(
            ["curl", "-s", LOCAL_LLM_URL,
             "-d", json.dumps({
                 "model": LOCAL_LLM_MODEL,
                 "prompt": prompt,
                 "stream": False
             })],
            capture_output=True, text=True, timeout=60
        )
        response = json.loads(result.stdout)
        answer = response.get("response", "")

        # Extract JSON array from response
        import re
        match = re.search(r"\[[\d\s,]+\]", answer)
        if match:
            keep_indices = json.loads(match.group())
            return [borderline_ideas[i - 1] for i in keep_indices
                    if 1 <= i <= len(borderline_ideas)]
    except Exception as e:
        print(f"  Warning: local LLM filter failed: {e}")
        print("  Falling back to score-based cutoff.")

    return borderline_ideas  # On failure, keep all borderline ideas


def run_filter() -> list[dict]:
    """
    Filter enriched ideas to survivors.
    Writes data/survivors.json.
    """
    with open(DATA_DIR / "enriched.json") as f:
        enriched = json.load(f)

    print(f"Stage 4: Filtering {len(enriched)} ideas...")

    # Step 1: hard rules
    passed = [idea for idea in enriched if passes_hard_rules(idea)]
    rejected = len(enriched) - len(passed)
    print(f"  Hard rules: {len(passed)} passed, {rejected} rejected")

    # Step 2: if still too many, split into safe keepers and borderline
    if len(passed) <= SURVIVOR_TARGET:
        survivors = passed
    elif USE_LOCAL_LLM_FILTER:
        # Top half are safe keepers; bottom half go to LLM for tiebreaking
        safe = passed[:SURVIVOR_TARGET // 2]
        borderline = passed[SURVIVOR_TARGET // 2:]
        llm_picks = local_llm_filter(borderline)
        survivors = safe + llm_picks[:SURVIVOR_TARGET - len(safe)]
        print(f"  Local LLM kept {len(llm_picks)} from {len(borderline)} borderline ideas")
    else:
        # Just take top N by score
        survivors = passed[:SURVIVOR_TARGET]

    print(f"Stage 4 complete: {len(survivors)} survivors.")

    out_path = DATA_DIR / "survivors.json"
    with open(out_path, "w") as f:
        json.dump(survivors, f, indent=2)

    print(f"Wrote {out_path} ({len(survivors)} survivors)")

    if survivors:
        print("Survivors (score desc):")
        for idea in survivors:
            print(f"  - {idea['idea_score']:.3f}  \"{idea['query']}\"")
    else:
        print("  WARNING: zero survivors — report will be empty. "
              "Check MIN_SCORE_THRESHOLD / MIN_VIEWS_PER_DAY / MAX_SATURATION_COUNT in config.py "
              "against the actual score/signal distribution in data/enriched.json.")

    rejected_ideas = [idea for idea in enriched if not passes_hard_rules(idea)]
    if rejected_ideas:
        print(f"\nSample of rejected ideas ({len(rejected_ideas)} total):")
        for idea in rejected_ideas[:3]:
            print(f"  - {idea['idea_score']:.3f}  \"{idea['query']}\"  "
                  f"(vpd={idea['signals'].get('raw_best_vpd', '?')}, "
                  f"count={idea['signals'].get('raw_video_count', '?')})")

    return survivors


if __name__ == "__main__":
    run_filter()
