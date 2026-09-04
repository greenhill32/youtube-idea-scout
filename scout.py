"""
youtube-idea-scout — main entry point.

Runs all stages in order:
  preflight → autocomplete → search → enrich → filter → captions → analysis → report

Usage:
  python scout.py            # Full run
  python scout.py --from 5   # Resume from stage 5 (captions)
  python scout.py --preflight                      # Preflight checks only
  python scout.py --mode opportunity               # V2 Stage 0, Stage 3, Stage 4, then Stage 5
  python scout.py --mode opportunity --from 3      # V2 Stage 3 then Stage 4 using existing Stage 0 output
  python scout.py --mode opportunity --from 4      # V2 Stage 4 then Stage 5 using existing Stage 3 output
  python scout.py --mode opportunity --from 5      # V2 Stage 5 using existing Stage 4 survivors
  python scout.py --mode opportunity --source import # V2 Stage 0, external JSON feed
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

from config import DATA_DIR
from preflight import run_preflight
from stage1_autocomplete import run_autocomplete
from stage2_search import run_search
from stage3_enrich import run_enrichment
from stage4_filter import run_filter
from stage5_captions import run_captions
from stage6_analysis import run_analysis
from stage7_report import generate_report
from stage0_opportunity import run_opportunity_radar
from stage3_opportunity import run_opportunity_enrichment
from stage4_opportunity import run_opportunity_gates
from stage5_opportunity import run_opportunity_format_evidence


def main():
    parser = argparse.ArgumentParser(description="YouTube Idea Scout")
    parser.add_argument("--from", dest="from_stage", type=int, default=1,
                        help="Resume from stage N (1-7)")
    parser.add_argument("--preflight", action="store_true",
                        help="Run preflight checks only")
    parser.add_argument("--mode", choices=["idea", "opportunity"], default="idea",
                        help="idea = frozen V1 path (default); opportunity = V2 Stage 0 radar")
    parser.add_argument("--source", choices=["self", "import"], default=None,
                        help="Opportunity radar source override: self or import")
    args = parser.parse_args()

    print(f"=== YouTube Idea Scout ===")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    # Always run preflight
    if not run_preflight():
        sys.exit(1)
    print()

    if args.preflight:
        return

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "opportunity":
        opportunity_stages = [
            (0, "Opportunity radar", lambda: run_opportunity_radar(args.source)),
            (3, "Opportunity enrichment", run_opportunity_enrichment),
            (4, "Opportunity hard gates", run_opportunity_gates),
            (5, "Opportunity format evidence", run_opportunity_format_evidence),
        ]
        for stage_num, name, fn in opportunity_stages:
            if stage_num < args.from_stage:
                print(f"Stage {stage_num}: {name} — SKIPPED (resuming from {args.from_stage})")
                continue
            print("\n" + "="*60)
            print(f"Stage {stage_num}: {name}")
            print("="*60)
            try:
                fn()
            except Exception as e:
                print(f"\nFATAL: Stage {stage_num} ({name}) failed: {e}")
                sys.exit(1)
            if stage_num == 5:
                print("\nV2 Stage 5 built. Per the stage-gate rule, Stage 6 is not wired yet.")
                print("Verify data/opportunity_format_evidence.json and opportunity_stage5_stats.json before continuing.")
        return

    stages = [
        (1, "Autocomplete expansion", run_autocomplete),
        (2, "YouTube search", run_search),
        (3, "Enrichment + scoring", run_enrichment),
        (4, "Filtering", run_filter),
        (5, "Caption fetch", run_captions),
        (6, "Gap analysis", run_analysis),
        (7, "Report generation", generate_report),
    ]

    for stage_num, name, fn in stages:
        if stage_num < args.from_stage:
            print(f"Stage {stage_num}: {name} — SKIPPED (resuming from {args.from_stage})")
            continue

        print(f"\n{'='*60}")
        print(f"Stage {stage_num}: {name}")
        print(f"{'='*60}")

        try:
            fn()
        except Exception as e:
            print(f"\nFATAL: Stage {stage_num} ({name}) failed: {e}")
            print(f"Fix the error and resume with: python scout.py --from {stage_num}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"DONE — report at: {DATA_DIR / 'report.html'}")
    print(f"Finished: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
