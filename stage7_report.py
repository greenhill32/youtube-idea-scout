"""
Stage 7: Generate report.html from survivors and analyses, then append one
line to run_history.jsonl for this completed run.

Input:  data/survivors.json + data/filter_stats.json + data/analyses/*.json
        + data/stage1_stats.json / stage2_stats.json / stage6_stats.json
          (all optional — Stage 7 tolerates any of them being absent)
Output: data/report.html
        run_history.jsonl (appended, never overwritten)

One self-contained HTML file. No external dependencies.
Opens in any browser. Designed for morning reading.

v0.21: Stage 6 now issues a MAKE/REJECT verdict per idea (editorial gate,
independent of the Stage 4 score threshold). The report shows MAKE ideas
as full recommendation cards; REJECTed ideas are listed compactly rather
than dropped, in the same deterministic order Stage 3/4 already produced
(never resorted by analysis/completion order). If zero ideas got MAKE,
the report falls back to the best-scoring REJECTed candidates, clearly
labelled — the same fallback UI Stage 4's own zero-qualifying case uses.
"""

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from config import (
    DATA_DIR, ANALYSES_DIR, REPORT_FILE, REPORTS_ARCHIVE_DIR, MAX_REPORT_IDEAS,
    FALLBACK_CANDIDATE_COUNT, RUN_HISTORY_FILE,
)
from common import current_run_id


def esc(value) -> str:
    """HTML-escape a value for safe interpolation into the report.
    Video titles/queries routinely contain quotes, &, and occasionally
    angle brackets (clickbait formatting) — unescaped, these corrupt
    the HTML structure. Caught during Stage 7 verification.
    """
    return html.escape(str(value))


def load_analyses() -> dict[int, dict]:
    """Load all analysis JSON files, keyed by index."""
    analyses = {}
    for f in sorted(ANALYSES_DIR.glob("*.json")):
        try:
            index = int(f.stem)
            analyses[index] = json.loads(f.read_text())
        except (ValueError, json.JSONDecodeError):
            continue
    return analyses


def load_json_if_exists(path: Path) -> dict:
    """Load a stats JSON file if present; empty dict otherwise. Every
    stats file Stage 7 reads is optional, so it works whether or not
    the full pipeline (Stages 1/2/6) ran before it."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def confidence_colour(confidence: str) -> str:
    """CSS colour for confidence level."""
    return {
        "high": "#22c55e",
        "medium": "#eab308",
        "low": "#ef4444",
    }.get(str(confidence).lower(), "#888")


def score_bar(score: float) -> str:
    """HTML for a simple visual score bar."""
    pct = int(score * 100)
    colour = "#22c55e" if pct >= 70 else "#eab308" if pct >= 40 else "#ef4444"
    return f'''<div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle">
        <div style="background:{colour};height:100%;width:{pct}%;border-radius:4px"></div>
    </div> <span style="font-size:0.85em;color:#666">{pct}%</span>'''


def build_summary_block(filter_stats: dict, stage1_stats: dict, stage2_stats: dict,
                         stage6_stats: dict, reported: int, run_id: str) -> str:
    """Run summary: funnel counts through every gate, including the v0.21
    editorial verdict tally and evaluation-failure count."""
    max_ideas = filter_stats.get("max_report_ideas", MAX_REPORT_IDEAS)
    passing = filter_stats.get("passing_final_threshold", None)

    lines = [f'<span>Run ID</span><span style="text-align:right">{esc(run_id)}</span>']
    if "queries_generated" in stage1_stats:
        lines.append(f'<span>Queries generated (Stage 1)</span><span style="text-align:right">{stage1_stats["queries_generated"]}</span>')
    if "queries_searched" in stage2_stats:
        lines.append(f'<span>Queries searched (Stage 2)</span><span style="text-align:right">{stage2_stats["queries_searched"]}</span>')
    if filter_stats:
        lines.append(f'<span>Candidates examined</span><span style="text-align:right">{filter_stats.get("candidates_examined", "?")}</span>')
        lines.append(f'<span>Passed initial eligibility</span><span style="text-align:right">{filter_stats.get("initial_eligibility_count", "?")}</span>')
        lines.append(f'<span>Distinct opportunities after clustering</span><span style="text-align:right">{filter_stats.get("distinct_after_clustering", "?")}</span>')
        lines.append(f'<span>Passed final quality threshold</span><span style="text-align:right">{passing if passing is not None else "?"}</span>')
    if stage6_stats:
        lines.append(f'<span>Editorial verdicts — MAKE</span><span style="text-align:right">{stage6_stats.get("make", "?")}</span>')
        lines.append(f'<span>Editorial verdicts — REJECT</span><span style="text-align:right">{stage6_stats.get("reject", "?")}</span>')
        failures = stage6_stats.get("editorial_failures", 0)
        fail_colour = "#b91c1c" if failures else "inherit"
        lines.append(f'<span>Editorial evaluation failures</span><span style="text-align:right;color:{fail_colour}">{failures}</span>')
    lines.append(f'<span>Recommended</span><span style="text-align:right">{reported}</span>')

    rows = f"""
    <div style="background:white;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;margin-bottom:20px;font-size:0.9em;color:#374151">
        <div style="font-weight:600;margin-bottom:8px">Run summary</div>
        <div style="display:grid;grid-template-columns:1fr auto;gap:4px 20px">
            {''.join(lines)}
        </div>"""

    if filter_stats and passing is not None and not filter_stats.get("is_fallback", False) and passing < max_ideas:
        plural = "y" if passing == 1 else "ies"
        rows += f"""
        <div style="margin-top:10px;padding-top:10px;border-top:1px solid #e5e7eb;color:#6b7280">
            Only {passing} opportunit{plural} passed the quality threshold this run
            (report cap is {max_ideas}). Unused report slots were intentional —
            the threshold was not lowered to fill them.
        </div>"""

    rows += "</div>"
    return rows


def build_fallback_banner(reported: int) -> str:
    """Prominent, unambiguous banner for the zero-MAKE / zero-qualifying case."""
    return f"""
    <div style="background:#fef2f2;border:2px solid #ef4444;border-radius:8px;padding:16px 20px;margin-bottom:20px">
        <div style="font-weight:700;color:#b91c1c;margin-bottom:6px">⚠ FALLBACK — BELOW NORMAL THRESHOLD</div>
        <div style="color:#7f1d1d">No sufficiently strong opportunities were found in this run.
        The {reported} idea{'s' if reported != 1 else ''} below {'are' if reported != 1 else 'is'} the best
        available candidate{'s' if reported != 1 else ''}, but {'they' if reported != 1 else 'it'} did not
        meet the normal quality threshold.</div>
    </div>"""


def truncate(text: str, max_len: int = 280) -> str:
    """Keep a summary genuinely concise even if the model runs long."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def assessment_tag(label: str, value: str) -> str:
    """Small pill for a Stage 6 editorial assessment (adequate/inadequate)."""
    is_adequate = str(value).lower() == "adequate"
    colour = "#16a34a" if is_adequate else "#dc2626"
    bg = "#dcfce7" if is_adequate else "#fee2e2"
    return (f'<span style="font-size:0.75em;font-weight:600;padding:2px 8px;border-radius:3px;'
            f'background:{bg};color:{colour}">{esc(label)}: {esc(value)}</span>')


def build_idea_card(i: int, idea: dict, analysis: dict, is_fallback_display: bool) -> str:
    """Full recommendation card — used for MAKE ideas, and for the
    best-available candidates shown in a zero-MAKE fallback run.

    v0.21.1: MAKE ideas lead with a prominent MAKE badge and a "WHY MAKE
    THIS?" synthesis (Stage 6's own reasoning, not a rewrite), with the
    Gap/Fit editorial assessments surfaced as tags right below it. The
    deterministic numeric score/signals move down into a smaller,
    secondary row — still visible, no longer the first thing you read.
    Fallback (REJECT-but-shown) cards keep the plainer layout: calling
    something "why make this" when the verdict was REJECT would misstate
    what the card is.
    """
    query = idea["query"]
    score = idea["idea_score"]
    signals = idea.get("signals", {})
    alt_phrasings = idea.get("alternate_phrasings") or []

    video_rows = ""
    for v in idea.get("videos", [])[:3]:
        video_rows += f"""<tr>
            <td style="padding:4px 8px"><a href="{esc(v.get('url', '#'))}" target="_blank"
                style="color:#2563eb;text-decoration:none">{esc(v.get('title', 'Unknown')[:80])}</a></td>
            <td style="padding:4px 8px;text-align:right">{v.get('view_count', 0):,}</td>
            <td style="padding:4px 8px;text-align:right">{v.get('views_per_day', 0):,.0f}</td>
            <td style="padding:4px 8px">{esc(v.get('channel', 'Unknown'))}</td>
        </tr>"""

    alt_html = ""
    if alt_phrasings:
        items = "".join(f"<li>{esc(p)}</li>" for p in alt_phrasings)
        alt_html = f"""
        <div style="margin-top:8px;font-size:0.85em;color:#666">
            <strong>Also matched ({len(alt_phrasings)} alternate phrasing{'s' if len(alt_phrasings) != 1 else ''}):</strong>
            <ul style="margin:4px 0 0 0;padding-left:20px">{items}</ul>
        </div>"""

    # Secondary row: deterministic numeric score + Stage 3 signals. Still
    # here, still readable — just no longer the visual headline.
    secondary_signals_html = f"""
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:14px;font-size:0.8em;color:#9ca3af;margin:10px 0 12px 0;padding-top:10px;border-top:1px solid #f3f4f6">
        <span>Score {score:.2f}</span>
        {score_bar(score)}
        <span>Demand: {signals.get('demand', '?')}</span>
        <span>Competition: {signals.get('competition', '?')}</span>
        <span>Breakout: {'Yes' if signals.get('breakout', 0) > 0 else 'No'}</span>
        <span>Channel fit: {signals.get('channel_fit', '?')}</span>
    </div>"""

    make_header_html = ""
    analysis_html = ""

    if analysis and not analysis.get("fatal_issue"):
        conf = analysis.get("confidence", "unknown")
        gap = analysis.get("gap_assessment")
        fit = analysis.get("fit_assessment")

        if not is_fallback_display:
            # WHY MAKE THIS? — Stage 6's own reasoning, verbatim (truncated
            # only for safety), not a separate rewrite. Gap/Fit tags sit
            # directly beneath it since they're what the verdict rests on.
            tags = "".join([
                assessment_tag("Gap", gap) if gap else "",
                assessment_tag("Fit", fit) if fit else "",
                f'<span style="font-size:0.75em;padding:2px 8px;border-radius:3px;'
                f'background:{confidence_colour(conf)};color:white">{esc(conf)} confidence</span>',
            ])
            make_header_html = f"""
            <div style="margin:10px 0 4px 0">
                <div style="font-weight:700;font-size:0.8em;letter-spacing:0.5px;color:#166534;margin-bottom:4px">WHY MAKE THIS?</div>
                <p style="margin:0 0 8px 0;color:#1f2937">{esc(truncate(analysis.get('reasoning', ''), 320))}</p>
                <div style="display:flex;gap:6px;flex-wrap:wrap">{tags}</div>
            </div>"""

        analysis_html = f"""
        <div style="margin-top:12px;padding:12px;background:#f0fdf4;border-radius:6px;border-left:3px solid {confidence_colour(conf)}">
            <div style="font-weight:600;margin-bottom:6px">Gap Analysis detail</div>
            <p style="margin:4px 0"><strong>Competitors cover:</strong> {esc(analysis.get('what_competitors_cover', 'N/A'))}</p>
            <p style="margin:4px 0"><strong>Competitors miss:</strong> {esc(analysis.get('what_competitors_miss', 'N/A'))}</p>
            <p style="margin:4px 0;padding:8px;background:#dcfce7;border-radius:4px">
                <strong>Suggested angle:</strong> {esc(analysis.get('suggested_angle', 'N/A'))}
            </p>
        </div>"""
    elif analysis and analysis.get("fatal_issue"):
        analysis_html = (f'<div style="margin-top:12px;padding:8px;background:#fef2f2;border-radius:4px;'
                          f'font-size:0.9em;color:#b91c1c">Editorial evaluation failed: {esc(analysis["fatal_issue"])}</div>')
    else:
        analysis_html = '<div style="margin-top:12px;padding:8px;background:#fef3c7;border-radius:4px;font-size:0.9em">Gap analysis not available for this idea.</div>'

    if is_fallback_display:
        verdict_badge = ('<span style="font-size:0.75em;font-weight:700;padding:3px 10px;border-radius:4px;'
                          'background:#ef4444;color:white;letter-spacing:0.5px">FALLBACK — BELOW THRESHOLD</span>')
        card_border = "#ef4444"
    else:
        verdict_badge = ('<span style="font-size:0.75em;font-weight:700;padding:3px 10px;border-radius:4px;'
                          'background:#16a34a;color:white;letter-spacing:0.5px">MAKE</span>')
        card_border = "#e5e7eb"

    return f"""
    <div style="border:1px solid {card_border};border-radius:8px;padding:20px;margin-bottom:16px;background:white">
        <div style="margin-bottom:6px">{verdict_badge}</div>
        <h3 style="margin:0;font-size:1.1em">#{i+1} — "{esc(query)}"</h3>
        {make_header_html}
        {secondary_signals_html}
        <table style="width:100%;border-collapse:collapse;font-size:0.9em;margin-bottom:8px">
            <thead>
                <tr style="border-bottom:1px solid #e5e7eb;text-align:left">
                    <th style="padding:4px 8px">Video</th>
                    <th style="padding:4px 8px;text-align:right">Views</th>
                    <th style="padding:4px 8px;text-align:right">Views/day</th>
                    <th style="padding:4px 8px">Channel</th>
                </tr>
            </thead>
            <tbody>{video_rows}</tbody>
        </table>
        {alt_html}
        {analysis_html}
    </div>"""


def build_rejected_section(rejected: list[tuple[int, dict, dict]]) -> str:
    """
    Compact list of REJECTed ideas — not full cards (they weren't judged
    worth making), but not dropped either: visible, in the same
    deterministic score order Stage 3/4 produced (never resorted by
    analysis completion order, satisfying the "no thread/subprocess
    order" rule for rejected-item display).
    """
    if not rejected:
        return ""
    rows = ""
    for i, idea, analysis in rejected:
        reason = analysis.get("fatal_issue") or analysis.get("reasoning") or "no reason recorded"
        gap = analysis.get("gap_assessment")
        fit = analysis.get("fit_assessment")
        tag = ""
        if gap == "inadequate":
            tag = "gap inadequate"
        elif fit == "inadequate":
            tag = "off-territory"
        elif analysis.get("fatal_issue"):
            tag = "evaluation failed"
        tag_html = f'<span style="font-size:0.75em;padding:1px 6px;border-radius:3px;background:#fee2e2;color:#991b1b;margin-left:8px">{esc(tag)}</span>' if tag else ""
        rows += f"""<li style="margin-bottom:6px">
            <span style="color:#374151">"{esc(idea['query'])}"</span>
            <span style="color:#9ca3af;font-size:0.85em"> (score {idea['idea_score']:.2f})</span>
            {tag_html}
            <div style="font-size:0.8em;color:#9ca3af;margin-top:2px">{esc(reason)}</div>
        </li>"""
    return f"""
    <div style="margin-top:24px;padding:16px 20px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px">
        <div style="font-weight:600;margin-bottom:10px;color:#374151">Also considered, editorially rejected ({len(rejected)})</div>
        <ul style="margin:0;padding-left:20px;font-size:0.9em">{rows}</ul>
    </div>"""


def append_run_history(run_id: str, investigated: int, make_count: int, reject_count: int,
                        is_fallback: bool, queries_generated, queries_searched,
                        distinct_opportunities) -> dict:
    """Append one JSON line for this completed run. Never overwrites —
    open in append mode, so historical run records always survive."""
    entry = {
        "run_id": run_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "investigated": investigated,
        "make": make_count,
        "reject": reject_count,
        "make_rate": round(make_count / investigated, 4) if investigated else 0.0,
        "fallback": is_fallback,
    }
    if queries_generated is not None:
        entry["queries_generated"] = queries_generated
    if queries_searched is not None:
        entry["queries_searched"] = queries_searched
    if distinct_opportunities is not None:
        entry["distinct_opportunities"] = distinct_opportunities

    with open(RUN_HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def generate_report() -> str:
    """Build the full HTML report and append this run's run_history.jsonl entry."""
    run_id = current_run_id(DATA_DIR)

    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    filter_stats = load_json_if_exists(DATA_DIR / "filter_stats.json")
    stage1_stats = load_json_if_exists(DATA_DIR / "stage1_stats.json")
    stage2_stats = load_json_if_exists(DATA_DIR / "stage2_stats.json")
    stage6_stats = load_json_if_exists(DATA_DIR / "stage6_stats.json")
    analyses = load_analyses()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Split survivors by editorial verdict, preserving the deterministic
    # order they already arrived in (Stage 3's (-score, query) sort,
    # carried through Stage 4's dedup) — never resorted here.
    make_ideas: list[tuple[int, dict, dict]] = []
    reject_ideas: list[tuple[int, dict, dict]] = []
    for i, idea in enumerate(survivors):
        analysis = analyses.get(i, {})
        verdict = analysis.get("verdict")
        if verdict == "MAKE":
            make_ideas.append((i, idea, analysis))
        else:
            reject_ideas.append((i, idea, analysis))

    stage4_fallback = filter_stats.get("is_fallback", False)
    is_fallback = stage4_fallback or (len(make_ideas) == 0 and len(survivors) > 0)

    if make_ideas:
        display_ideas = make_ideas
        rejected_for_display = reject_ideas
    elif reject_ideas:
        # Zero MAKE verdicts: fall back to the best-scoring rejected
        # candidates, in the same deterministic order, clearly labelled.
        display_ideas = reject_ideas[:FALLBACK_CANDIDATE_COUNT]
        rejected_for_display = []
    else:
        display_ideas = []
        rejected_for_display = []

    # display_position is sequential (#1, #2, #3...) even though the
    # underlying (idea, analysis) tuples carry their original survivor
    # index for analysis lookup — without this, REJECTed ideas being
    # filtered out would leave gaps like #1, #3, #5 in the report.
    cards_html = "".join(
        build_idea_card(display_position, idea, analysis, is_fallback_display=is_fallback)
        for display_position, (_, idea, analysis) in enumerate(display_ideas)
    )
    rejected_section = build_rejected_section(rejected_for_display)

    summary_block = build_summary_block(filter_stats, stage1_stats, stage2_stats,
                                         stage6_stats, len(display_ideas), run_id)
    fallback_banner = build_fallback_banner(len(display_ideas)) if is_fallback else ""

    # "X ideas reported" reads like a raw analysis dump; this report is a
    # decision surface. Fallback candidates never earned "recommended" —
    # say what they actually are instead of overselling them.
    if is_fallback:
        n = len(display_ideas)
        header_line = f"{n} fallback candidate{'s' if n != 1 else ''} shown (none met the normal quality threshold)"
    else:
        n = len(display_ideas)
        header_line = f"{n} recommended opportunit{'y' if n == 1 else 'ies'}"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Idea Scout Report — {now}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f9fafb;
            color: #1f2937;
        }}
        a {{ color: #2563eb; }}
    </style>
</head>
<body>
    <h1 style="margin-bottom:4px">YouTube Idea Scout Report</h1>
    <p style="color:#6b7280;margin-top:0">Generated {now} — run {esc(run_id)} — {header_line}</p>
    {fallback_banner}
    {summary_block}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">
    {cards_html}
    {rejected_section}
    <p style="text-align:center;color:#9ca3af;font-size:0.85em;margin-top:32px">
        End of report. Open competitor links in new tabs. Your call what to make.
    </p>
</body>
</html>"""

    REPORT_FILE.write_text(html_doc, encoding="utf-8")

    # report.html is overwritten every run; archive a run_id-keyed copy so
    # past reports survive the next run instead of being silently lost.
    REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_ARCHIVE_DIR / f"report_{run_id}.html").write_text(html_doc, encoding="utf-8")

    print(f"Stage 7 complete: report written to {REPORT_FILE}")
    print(f"Wrote {REPORT_FILE} ({len(html_doc)} bytes, {len(display_ideas)} idea cards, "
          f"{len(rejected_for_display)} rejected listed, fallback={is_fallback})")

    ideas_missing_analysis = sum(1 for i in range(len(survivors)) if i not in analyses)
    if ideas_missing_analysis:
        print(f"  WARNING: {ideas_missing_analysis}/{len(survivors)} cards have no gap analysis.")

    investigated = stage6_stats.get("investigated", len(survivors))
    make_count = stage6_stats.get("make", len(make_ideas))
    reject_count = stage6_stats.get("reject", len(reject_ideas))
    entry = append_run_history(
        run_id=run_id,
        investigated=investigated,
        make_count=make_count,
        reject_count=reject_count,
        is_fallback=is_fallback,
        queries_generated=stage1_stats.get("queries_generated"),
        queries_searched=stage2_stats.get("queries_searched"),
        distinct_opportunities=filter_stats.get("distinct_after_clustering"),
    )
    print(f"Appended to {RUN_HISTORY_FILE}: {entry}")

    return html_doc


if __name__ == "__main__":
    generate_report()
