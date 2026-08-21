"""
youtube-idea-scout — main entry point.

Runs all stages in order:
  preflight → autocomplete → search → enrich → filter → captions → analysis → report

Usage:
  python scout.py            # Full run
  python scout.py --from 5   # Resume from stage 5 (captions)
  python scout.py --preflight # Preflight checks only
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


def main():
    parser = argparse.ArgumentParser(description="YouTube Idea Scout")
    parser.add_argument("--from", dest="from_stage", type=int, default=1,
                        help="Resume from stage N (1-7)")
    parser.add_argument("--preflight", action="store_true",
                        help="Run preflight checks only")
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
