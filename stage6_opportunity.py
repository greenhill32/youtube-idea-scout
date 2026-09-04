"""
Scout V2 Stage 6: semantic opportunity judgement + format clustering.

Input:
  data/opportunity_format_evidence.json

Outputs:
  data/opportunity_stage6.json
  data/opportunity_stage6_stats.json

Per-channel judgement uses Claude CLI, then a second Claude pass clusters recurring
production formats. Failures fail closed to REJECT for the affected channel.
"""

from __future__ import annotations
import json, re, subprocess
from datetime import datetime, timezone
from config import (
    DATA_DIR, OPPORTUNITY_PRODUCTION_PROFILE, OPPORTUNITY_STAGE6_MODEL,
    OPPORTUNITY_STAGE6_TIMEOUT_SECONDS, OPPORTUNITY_STAGE6_MIN_FORMAT_CHANNELS,
    OPPORTUNITY_STAGE6_MAX_MAKE_RATE, OPPORTUNITY_STAGE6_COLLAPSE_WARNING_RATE,
)

INPUT_FILE = DATA_DIR / "opportunity_format_evidence.json"
OUTPUT_FILE = DATA_DIR / "opportunity_stage6.json"
STATS_FILE = DATA_DIR / "opportunity_stage6_stats.json"

VALID_FACTORY = {"A","B","C","D"}
VALID_MON = {"HIGH","MEDIUM","LOW","UNKNOWN"}
VALID_RISK = {"LOW","MEDIUM","HIGH","UNKNOWN"}
VALID_SAT = {"LOW","MEDIUM","HIGH","UNKNOWN"}
VALID_EM = {"STRONG","MODERATE","WEAK","INSUFFICIENT"}
VALID_VERDICTS = {"MAKE","WATCH","REJECT"}

def _run_claude(prompt:str)->dict:
    r=subprocess.run(["claude","--model",OPPORTUNITY_STAGE6_MODEL,"-p",prompt],
                     capture_output=True,text=True,timeout=OPPORTUNITY_STAGE6_TIMEOUT_SECONDS)
    if r.returncode!=0: raise RuntimeError(f"claude exited {r.returncode}: {r.stderr[:200]}")
    m=re.search(r"\{[\s\S]*\}",r.stdout)
    if not m: raise ValueError("no JSON object")
    return json.loads(m.group())

def _channel_prompt(c:dict)->str:
    ev=c.get("format_evidence",{})
    compact={
        "channel_id":c.get("channel_id"),"channel":c.get("title"),
        "subscribers":c.get("subscriber_count"),"bands":c.get("bands"),
        "evidence":c.get("evidence"),"stage4":c.get("stage4"),
        "format_evidence":ev,
    }
    return f"""You are judging one YouTube opportunity for Scout V2.

Current production capability:
{OPPORTUNITY_PRODUCTION_PROFILE}

Evidence:
{json.dumps(compact, ensure_ascii=False)}

Return ONLY JSON with:
{{
 "format_fingerprint": {{
   "asset_type":"short concrete phrase",
   "structure":"short concrete phrase",
   "typical_length":"short concrete phrase",
   "point_of_view":"short concrete phrase",
   "title_pattern":"short concrete phrase"
 }},
 "factory_fit":"A|B|C|D",
 "factory_fit_reason":"brief evidence-grounded reason",
 "test_days": 1,
 "rights_risk":"LOW|MEDIUM|HIGH|UNKNOWN",
 "rights_reason":"brief reason",
 "monetisation":"HIGH|MEDIUM|LOW|UNKNOWN",
 "monetisation_reason":"brief reason",
 "saturation":"LOW|MEDIUM|HIGH|UNKNOWN",
 "saturation_reason":"brief reason based only on supplied evidence",
 "emergence":"STRONG|MODERATE|WEAK|INSUFFICIENT",
 "emergence_reason":"brief reason",
 "cheapest_test_video":"one specific test concept",
 "semantic_red_flags":["..."],
 "verdict":"MAKE|WATCH|REJECT",
 "verdict_reason":"brief reason"
}}

Rules:
- Do not invent RPMs or facts not in evidence.
- Asset dependence means copyrighted third-party footage is core to the proposition.
- Presenter/lip-sync/heavy 3D/real-world filming dependency counts against factory fit.
- MAKE only if factory_fit is A, or B with LOW rights risk; saturation is not HIGH; emergence is supported; and there is no clear semantic red flag.
- WATCH if there is real emergence but exactly one MAKE condition fails or evidence is ambiguous.
- Otherwise REJECT.
- If the channel is a trailer/promo/film-distributor clip channel, reflect that in rights risk/factory fit even if Stage 4 missed it.
"""

def _validate(a:dict)->dict:
    if a.get("factory_fit") not in VALID_FACTORY: raise ValueError("bad factory_fit")
    if a.get("monetisation") not in VALID_MON: raise ValueError("bad monetisation")
    if a.get("rights_risk") not in VALID_RISK: raise ValueError("bad rights_risk")
    if a.get("saturation") not in VALID_SAT: raise ValueError("bad saturation")
    if a.get("emergence") not in VALID_EM: raise ValueError("bad emergence")
    if a.get("verdict") not in VALID_VERDICTS: raise ValueError("bad verdict")
    fp=a.get("format_fingerprint")
    if not isinstance(fp,dict) or not all(k in fp for k in ["asset_type","structure","typical_length","point_of_view","title_pattern"]):
        raise ValueError("bad format_fingerprint")
    return a

def _fail_closed(c:dict, reason:str)->dict:
    return {
      "format_fingerprint":{"asset_type":"unknown","structure":"unknown","typical_length":"unknown","point_of_view":"unknown","title_pattern":"unknown"},
      "factory_fit":"D","factory_fit_reason":"semantic evaluation failed","test_days":None,
      "rights_risk":"UNKNOWN","rights_reason":"semantic evaluation failed",
      "monetisation":"UNKNOWN","monetisation_reason":"semantic evaluation failed",
      "saturation":"UNKNOWN","saturation_reason":"semantic evaluation failed",
      "emergence":"INSUFFICIENT","emergence_reason":"semantic evaluation failed",
      "cheapest_test_video":None,"semantic_red_flags":["stage6_evaluation_failure"],
      "verdict":"REJECT","verdict_reason":"Stage 6 evaluation failed closed",
      "fatal_issue":reason
    }

def _cluster_prompt(rows:list[dict])->str:
    mini=[{"channel_id":r["channel_id"],"channel":r["title"],"fingerprint":r["stage6"]["format_fingerprint"],"verdict":r["stage6"]["verdict"]} for r in rows]
    return f"""Cluster these channel format fingerprints into recurring production formats.
Evidence:
{json.dumps(mini, ensure_ascii=False)}

Return ONLY JSON:
{{"formats":[{{"name":"concise reusable format name","description":"brief","channel_ids":["UC..."],"status":"EMERGING|SPREADING|SATURATED|FADED"}}]}}

Rules:
- A format must contain at least {OPPORTUNITY_STAGE6_MIN_FORMAT_CHANNELS} unrelated channels.
- Cluster by production format, not merely subject.
- Do not force every channel into a cluster.
- If fewer than {OPPORTUNITY_STAGE6_MIN_FORMAT_CHANNELS} truly share a format, omit it.
"""

def run_opportunity_stage6()->dict:
    payload=json.loads(INPUT_FILE.read_text())
    channels=payload.get("channels",[])
    out=[]
    for i,c in enumerate(channels,1):
        print(f"Stage 6 semantic judgement {i}/{len(channels)}: {c.get('title')}")
        try: a=_validate(_run_claude(_channel_prompt(c)))
        except Exception as e: a=_fail_closed(c,str(e))
        out.append({**c,"stage6":a})

    try:
        clusters=_run_claude(_cluster_prompt(out)).get("formats",[])
        clusters=[f for f in clusters if isinstance(f,dict) and len(set(f.get("channel_ids",[])))>=OPPORTUNITY_STAGE6_MIN_FORMAT_CHANNELS]
    except Exception as e:
        clusters=[]
        cluster_error=str(e)
    else:
        cluster_error=None

    membership={}
    for f in clusters:
        for cid in f.get("channel_ids",[]): membership.setdefault(cid,[]).append(f.get("name"))
    for r in out: r["stage6"]["format_clusters"]=membership.get(r.get("channel_id"),[])

    verdicts={}
    dims={"factory_fit":{},"rights_risk":{},"monetisation":{},"saturation":{},"emergence":{}}
    failures=0
    for r in out:
        a=r["stage6"]; verdicts[a["verdict"]]=verdicts.get(a["verdict"],0)+1
        if a.get("fatal_issue"): failures+=1
        for d in dims: dims[d][a[d]]=dims[d].get(a[d],0)+1

    n=max(len(out),1); warnings=[]
    if verdicts.get("MAKE",0)/n>OPPORTUNITY_STAGE6_MAX_MAKE_RATE: warnings.append("MAKE_RATE_HIGH")
    for d,counts in dims.items():
        if counts and max(counts.values())/n>OPPORTUNITY_STAGE6_COLLAPSE_WARNING_RATE: warnings.append(f"{d.upper()}_COLLAPSE")
    if verdicts and max(verdicts.values())/n>OPPORTUNITY_STAGE6_COLLAPSE_WARNING_RATE: warnings.append("VERDICT_COLLAPSE")

    generated=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    result={"schema_version":1,"run_id":payload.get("run_id"),"generated_at":generated,"channels":out,"formats":clusters}
    OUTPUT_FILE.write_text(json.dumps(result,indent=2))
    stats={"run_id":payload.get("run_id"),"channels_examined":len(out),"verdict_distribution":verdicts,"dimension_histograms":dims,
           "format_cluster_count":len(clusters),"editorial_failures":failures,"cluster_error":cluster_error,"warnings":warnings}
    STATS_FILE.write_text(json.dumps(stats,indent=2))
    print(f"Stage 6 complete: {verdicts}; formats={len(clusters)}; warnings={warnings}")
    return result

if __name__=="__main__": run_opportunity_stage6()
