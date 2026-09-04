"""
Scout V2 Stage 7: self-contained HTML opportunity report.

Input:
  data/opportunity_stage6.json
  data/opportunity_stage6_stats.json (optional)

Output:
  data/opportunity_report.html
  data/opportunity_reports/opportunity_report_<run_id>.html

No external JS/CSS dependencies. Designed as the human decision surface for
weekly Scout V2 runs.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from config import (
    DATA_DIR,
    OPPORTUNITY_REPORT_FILE,
    OPPORTUNITY_REPORTS_ARCHIVE_DIR,
)

INPUT_FILE = DATA_DIR / "opportunity_stage6.json"
STATS_FILE = DATA_DIR / "opportunity_stage6_stats.json"


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def badge(text: str, tone: str = "neutral") -> str:
    return f'<span class="badge {esc(tone)}">{esc(text)}</span>'


def verdict_tone(v: str) -> str:
    return {"MAKE": "make", "WATCH": "watch", "REJECT": "reject"}.get(v, "neutral")


def risk_tone(v: str) -> str:
    return {"LOW": "make", "MEDIUM": "watch", "HIGH": "reject"}.get(v, "neutral")


def factory_tone(v: str) -> str:
    return {"A": "make", "B": "watch", "C": "watch", "D": "reject"}.get(v, "neutral")


def trunc(text: str | None, n: int = 220) -> str:
    s = (text or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "—"


def candidate_summary(c: dict) -> dict:
    candidates = c.get("candidate_videos") or []
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda v: (
            -(v.get("effective_outlier_multiple") or 0),
            -(v.get("view_count") or 0),
        ),
    )[0]


def build_format_section(formats: list[dict], channels_by_id: dict[str, dict]) -> str:
    if not formats:
        return '<section><h2>Recurring formats</h2><div class="empty">No recurring format cluster cleared the minimum evidence bar this run.</div></section>'

    cards = []
    for f in formats:
        members = []
        for cid in f.get("channel_ids") or []:
            c = channels_by_id.get(cid)
            if c:
                members.append(f'<li><strong>{esc(c.get("title"))}</strong> <span class="muted">{esc(c.get("stage6",{}).get("verdict"))}</span></li>')
        cards.append(f"""
        <article class="format-card">
          <div class="format-head">
            <h3>{esc(f.get("name","Unnamed format"))}</h3>
            {badge(f.get("status","UNKNOWN"), "neutral")}
          </div>
          <p>{esc(f.get("description",""))}</p>
          <div class="mini-label">Evidence channels</div>
          <ul class="member-list">{''.join(members)}</ul>
        </article>
        """)
    return f'<section><h2>Recurring formats</h2><div class="format-grid">{"".join(cards)}</div></section>'


def build_channel_card(c: dict) -> str:
    a = c.get("stage6") or {}
    cand = candidate_summary(c)
    verdict = a.get("verdict", "UNKNOWN")
    fp = a.get("format_fingerprint") or {}
    clusters = a.get("format_clusters") or []
    q = c.get("discovered_by_queries") or []
    flags = a.get("semantic_red_flags") or []

    evidence_bits = []
    if cand:
        evidence_bits.append(f'{fmt_int(cand.get("view_count"))} views')
        if cand.get("effective_outlier_multiple") is not None:
            evidence_bits.append(f'{cand.get("effective_outlier_multiple")}× trusted outlier')
        elif cand.get("raw_outlier_multiple") is not None:
            evidence_bits.append(f'{cand.get("raw_outlier_multiple")}× raw outlier')
    if c.get("subscriber_count") is not None:
        evidence_bits.append(f'{fmt_int(c.get("subscriber_count"))} subscribers')

    return f"""
    <article class="op-card {esc(verdict.lower())}">
      <div class="card-top">
        <div>
          <div class="eyebrow">{' · '.join(esc(x) for x in q) if q else 'Opportunity'}</div>
          <h3>{esc(c.get("title","Unknown channel"))}</h3>
        </div>
        <div class="verdict">{badge(verdict, verdict_tone(verdict))}</div>
      </div>

      <div class="evidence-line">{esc(" · ".join(evidence_bits))}</div>
      <div class="candidate-title">{esc(cand.get("title","No candidate title available"))}</div>

      <div class="metric-grid">
        <div><span>Factory fit</span>{badge(a.get("factory_fit","?"), factory_tone(a.get("factory_fit","")))}</div>
        <div><span>Rights</span>{badge(a.get("rights_risk","?"), risk_tone(a.get("rights_risk","")))}</div>
        <div><span>Monetisation</span>{badge(a.get("monetisation","?"), "neutral")}</div>
        <div><span>Saturation</span>{badge(a.get("saturation","?"), risk_tone(a.get("saturation","")))}</div>
        <div><span>Emergence</span>{badge(a.get("emergence","?"), "neutral")}</div>
      </div>

      <div class="why">
        <div class="mini-label">Why this verdict</div>
        <p>{esc(trunc(a.get("verdict_reason"), 320))}</p>
      </div>

      <div class="test-box">
        <div class="mini-label">Cheapest test</div>
        <p>{esc(a.get("cheapest_test_video") or "Not specified")}</p>
      </div>

      <details>
        <summary>Format & evidence</summary>
        <div class="detail-grid">
          <div><b>Asset type</b><br>{esc(fp.get("asset_type","—"))}</div>
          <div><b>Structure</b><br>{esc(fp.get("structure","—"))}</div>
          <div><b>Typical length</b><br>{esc(fp.get("typical_length","—"))}</div>
          <div><b>Point of view</b><br>{esc(fp.get("point_of_view","—"))}</div>
          <div><b>Title pattern</b><br>{esc(fp.get("title_pattern","—"))}</div>
          <div><b>Format cluster</b><br>{esc(", ".join(clusters) if clusters else "No recurring cluster yet")}</div>
        </div>
        <div class="detail-block"><b>Factory fit:</b> {esc(a.get("factory_fit_reason",""))}</div>
        <div class="detail-block"><b>Rights:</b> {esc(a.get("rights_reason",""))}</div>
        <div class="detail-block"><b>Monetisation:</b> {esc(a.get("monetisation_reason",""))}</div>
        <div class="detail-block"><b>Saturation:</b> {esc(a.get("saturation_reason",""))}</div>
        <div class="detail-block"><b>Emergence:</b> {esc(a.get("emergence_reason",""))}</div>
        {f'<div class="warning"><b>Red flags:</b> {esc(", ".join(flags))}</div>' if flags else ''}
        {f'<div class="warning"><b>Evaluation issue:</b> {esc(a.get("fatal_issue"))}</div>' if a.get("fatal_issue") else ''}
      </details>
    </article>
    """


def build_section(title: str, rows: list[dict], intro: str) -> str:
    if not rows:
        return f'<section><h2>{esc(title)}</h2><div class="empty">None this run.</div></section>'
    return f"""
    <section>
      <div class="section-head">
        <div><h2>{esc(title)}</h2><p>{esc(intro)}</p></div>
        <div class="count">{len(rows)}</div>
      </div>
      <div class="cards">{''.join(build_channel_card(c) for c in rows)}</div>
    </section>
    """


def generate_opportunity_report() -> str:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing {INPUT_FILE}. Run V2 Stage 6 first.")

    payload = load_json(INPUT_FILE, {})
    stats = load_json(STATS_FILE, {})
    channels = payload.get("channels") or []
    formats = payload.get("formats") or []
    run_id = payload.get("run_id") or "unknown"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    makes = [c for c in channels if (c.get("stage6") or {}).get("verdict") == "MAKE"]
    watches = [c for c in channels if (c.get("stage6") or {}).get("verdict") == "WATCH"]
    rejects = [c for c in channels if (c.get("stage6") or {}).get("verdict") == "REJECT"]

    order = {"MAKE":0,"WATCH":1,"REJECT":2}
    for rows in (makes,watches,rejects):
        rows.sort(key=lambda c: (
            order.get((c.get("stage6") or {}).get("verdict"),9),
            -((c.get("evidence") or {}).get("effective_max_outlier_multiple") or 0),
            str(c.get("title") or "").lower(),
        ))

    channels_by_id = {c.get("channel_id"): c for c in channels}
    warnings = stats.get("warnings") or []

    html_doc=f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scout V2 Opportunity Report</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--ink:#18212f;--muted:#667085;--line:#e5e9f0;--make:#0f9d58;--watch:#d97706;--reject:#d14343;--navy:#162033;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 20px 60px}}
.hero{{background:linear-gradient(135deg,#162033,#253653);color:white;border-radius:18px;padding:28px;margin-bottom:22px;box-shadow:0 10px 30px rgba(17,24,39,.12)}}
.hero h1{{margin:0 0 6px;font-size:30px}} .hero p{{margin:0;color:#cbd5e1}}
.summary{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:22px}}
.stat{{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:14px}}
.stat b{{display:block;font-size:24px}} .stat span{{font-size:12px;color:#cbd5e1}}
.health{{margin:16px 0 0;padding:12px 14px;border-radius:10px;background:rgba(255,255,255,.08);font-size:14px}}
section{{margin-top:30px}} h2{{margin:0 0 4px;font-size:22px}} .section-head{{display:flex;justify-content:space-between;align-items:end;margin-bottom:12px}}
.section-head p{{margin:0;color:var(--muted);font-size:14px}} .count{{font-size:28px;font-weight:700;color:#98a2b3}}
.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.op-card,.format-card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 4px 15px rgba(16,24,40,.04)}}
.op-card.make{{border-top:4px solid var(--make)}} .op-card.watch{{border-top:4px solid var(--watch)}} .op-card.reject{{border-top:4px solid var(--reject)}}
.card-top,.format-head{{display:flex;justify-content:space-between;gap:12px;align-items:start}} h3{{margin:2px 0 0;font-size:18px}}
.eyebrow,.mini-label{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#98a2b3;font-weight:700}}
.badge{{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;background:#eef2f7;color:#344054}}
.badge.make{{background:#dcfce7;color:#166534}} .badge.watch{{background:#fef3c7;color:#92400e}} .badge.reject{{background:#fee2e2;color:#991b1b}}
.evidence-line{{font-size:13px;color:#667085;margin-top:10px}} .candidate-title{{font-weight:650;margin:4px 0 12px}}
.metric-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:11px 0}}
.metric-grid div span:first-child{{display:block;font-size:10px;text-transform:uppercase;color:#98a2b3;margin-bottom:4px}}
.why p,.test-box p{{margin:4px 0 0;line-height:1.45}} .why{{margin-top:12px}}
.test-box{{margin-top:12px;background:#f8fafc;border-radius:10px;padding:12px}}
details{{margin-top:12px}} summary{{cursor:pointer;font-weight:650;color:#475467}}
.detail-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;font-size:13px}}
.detail-block{{margin-top:8px;font-size:13px;line-height:1.45}} .warning{{margin-top:8px;padding:9px;background:#fff7ed;border-radius:8px;font-size:13px}}
.format-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .format-card p{{color:#475467;line-height:1.45}}
.member-list{{margin:8px 0 0;padding-left:18px}} .member-list li{{margin:4px 0}} .muted{{color:#98a2b3;font-size:12px}}
.empty{{background:white;border:1px dashed #ccd3dd;border-radius:12px;padding:18px;color:#667085}}
footer{{margin-top:34px;text-align:center;color:#98a2b3;font-size:12px}}
@media(max-width:800px){{.summary{{grid-template-columns:repeat(2,1fr)}}.cards,.format-grid{{grid-template-columns:1fr}}.metric-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body><div class="wrap">
<div class="hero">
  <h1>Scout V2 — Opportunity Report</h1>
  <p>Run {esc(run_id)} · generated {esc(now)}</p>
  <div class="summary">
    <div class="stat"><b>{len(channels)}</b><span>channels judged</span></div>
    <div class="stat"><b>{len(makes)}</b><span>MAKE</span></div>
    <div class="stat"><b>{len(watches)}</b><span>WATCH</span></div>
    <div class="stat"><b>{len(rejects)}</b><span>REJECT</span></div>
    <div class="stat"><b>{len(formats)}</b><span>recurring formats</span></div>
  </div>
  <div class="health"><b>Run health:</b> {esc(", ".join(warnings) if warnings else "No discrimination warnings")}</div>
</div>

{build_format_section(formats,channels_by_id)}

{build_section("MAKE",makes,"The few opportunities that currently clear the action bar.")}
{build_section("WATCH",watches,"Real signal, but one condition or uncertainty still blocks action.")}
{build_section("REJECT",rejects,"Useful evidence, but not a current production opportunity.")}

<footer>Self-contained Scout V2 report · no external dependencies · source JSON remains in data/ for audit.</footer>
</div></body></html>"""

    OPPORTUNITY_REPORT_FILE.write_text(html_doc,encoding="utf-8")
    OPPORTUNITY_REPORTS_ARCHIVE_DIR.mkdir(parents=True,exist_ok=True)
    archive=OPPORTUNITY_REPORTS_ARCHIVE_DIR / f"opportunity_report_{run_id}.html"
    archive.write_text(html_doc,encoding="utf-8")
    print(f"Stage 7 complete: {OPPORTUNITY_REPORT_FILE}")
    print(f"Archived: {archive}")
    return html_doc


if __name__=="__main__":
    generate_opportunity_report()
