"""
Stage 7: Generate report.html from survivors and analyses.

Input:  data/survivors.json + data/analyses/*.json
Output: data/report.html

One self-contained HTML file. No external dependencies.
Opens in any browser. Designed for morning reading.
"""

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from config import DATA_DIR, ANALYSES_DIR, REPORT_FILE, MAX_IDEAS_IN_REPORT


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


def confidence_colour(confidence: str) -> str:
    """CSS colour for confidence level."""
    return {
        "high": "#22c55e",
        "medium": "#eab308",
        "low": "#ef4444",
    }.get(confidence.lower(), "#888")


def score_bar(score: float) -> str:
    """HTML for a simple visual score bar."""
    pct = int(score * 100)
    colour = "#22c55e" if pct >= 70 else "#eab308" if pct >= 40 else "#ef4444"
    return f'''<div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle">
        <div style="background:{colour};height:100%;width:{pct}%;border-radius:4px"></div>
    </div> <span style="font-size:0.85em;color:#666">{pct}%</span>'''


def generate_report() -> str:
    """Build the full HTML report."""
    with open(DATA_DIR / "survivors.json") as f:
        survivors = json.load(f)

    analyses = load_analyses()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Limit to configured maximum
    survivors = survivors[:MAX_IDEAS_IN_REPORT]

    # Build idea cards
    cards_html = ""
    for i, idea in enumerate(survivors):
        query = idea["query"]
        score = idea["idea_score"]
        signals = idea.get("signals", {})
        analysis = analyses.get(i, {})

        # Competitor video rows
        video_rows = ""
        for v in idea.get("videos", [])[:3]:
            video_rows += f"""<tr>
                <td style="padding:4px 8px"><a href="{esc(v.get('url', '#'))}" target="_blank"
                    style="color:#2563eb;text-decoration:none">{esc(v.get('title', 'Unknown')[:80])}</a></td>
                <td style="padding:4px 8px;text-align:right">{v.get('view_count', 0):,}</td>
                <td style="padding:4px 8px;text-align:right">{v.get('views_per_day', 0):,.0f}</td>
                <td style="padding:4px 8px">{esc(v.get('channel', 'Unknown'))}</td>
            </tr>"""

        # Analysis section
        analysis_html = ""
        if analysis:
            conf = analysis.get("confidence", "unknown")
            analysis_html = f"""
            <div style="margin-top:12px;padding:12px;background:#f0fdf4;border-radius:6px;border-left:3px solid {confidence_colour(conf)}">
                <div style="font-weight:600;margin-bottom:6px">
                    Gap Analysis
                    <span style="font-size:0.8em;padding:2px 6px;border-radius:3px;
                        background:{confidence_colour(conf)};color:white;margin-left:8px">
                        {esc(conf)} confidence
                    </span>
                </div>
                <p style="margin:4px 0"><strong>Competitors cover:</strong> {esc(analysis.get('what_competitors_cover', 'N/A'))}</p>
                <p style="margin:4px 0"><strong>Competitors miss:</strong> {esc(analysis.get('what_competitors_miss', 'N/A'))}</p>
                <p style="margin:4px 0;padding:8px;background:#dcfce7;border-radius:4px">
                    <strong>Suggested angle:</strong> {esc(analysis.get('suggested_angle', 'N/A'))}
                </p>
                <p style="margin:4px 0;font-size:0.9em;color:#666"><em>{esc(analysis.get('reasoning', ''))}</em></p>
            </div>"""
        else:
            analysis_html = '<div style="margin-top:12px;padding:8px;background:#fef3c7;border-radius:4px;font-size:0.9em">Gap analysis not available for this idea.</div>'

        cards_html += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px;background:white">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <h3 style="margin:0;font-size:1.1em">#{i+1} — "{esc(query)}"</h3>
                <div>{score_bar(score)}</div>
            </div>
            <div style="display:flex;gap:16px;font-size:0.85em;color:#666;margin-bottom:12px">
                <span>Demand: {signals.get('demand', '?')}</span>
                <span>Competition: {signals.get('competition', '?')}</span>
                <span>Breakout: {'Yes' if signals.get('breakout', 0) > 0 else 'No'}</span>
                <span>Channel fit: {signals.get('channel_fit', '?')}</span>
            </div>
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
            {analysis_html}
        </div>"""

    # Full HTML document
    html = f"""<!DOCTYPE html>
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
    <p style="color:#6b7280;margin-top:0">Generated {now} — {len(survivors)} ideas scored and analysed</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">
    {cards_html}
    <p style="text-align:center;color:#9ca3af;font-size:0.85em;margin-top:32px">
        End of report. Open competitor links in new tabs. Your call what to make.
    </p>
</body>
</html>"""

    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"Stage 7 complete: report written to {REPORT_FILE}")
    print(f"Wrote {REPORT_FILE} ({len(html)} bytes, {len(survivors)} idea cards)")

    ideas_missing_analysis = sum(1 for i in range(len(survivors)) if i not in analyses)
    if ideas_missing_analysis:
        print(f"  WARNING: {ideas_missing_analysis}/{len(survivors)} cards have no gap analysis.")

    return html


if __name__ == "__main__":
    generate_report()
