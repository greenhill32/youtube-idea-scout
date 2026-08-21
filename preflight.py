"""
Preflight checks. Run before any pipeline stage.
Exit with a clear error if anything required is broken.
"""

import subprocess
import sys
import shutil
from urllib.request import urlopen
from config import AUTOCOMPLETE_URL


def check_yt_dlp() -> bool:
    """Verify yt-dlp is installed AND can reach YouTube."""
    if not shutil.which("yt-dlp"):
        print("PREFLIGHT FAIL: yt-dlp is not installed or not on PATH.")
        print("  Fix: pip install yt-dlp")
        return False
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "ytsearch1:test"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print("PREFLIGHT FAIL: yt-dlp is installed but YouTube search failed.")
            print(f"  stderr: {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print("PREFLIGHT FAIL: yt-dlp YouTube search timed out (30s).")
        return False
    return True


def check_autocomplete() -> bool:
    """Verify YouTube autocomplete endpoint is reachable."""
    try:
        url = f"{AUTOCOMPLETE_URL}?client=youtube&q=test"
        response = urlopen(url, timeout=10)
        if response.status != 200:
            print(f"PREFLIGHT FAIL: Autocomplete returned status {response.status}")
            return False
    except Exception as e:
        print(f"PREFLIGHT FAIL: Cannot reach YouTube autocomplete: {e}")
        return False
    return True


def check_claude_code() -> bool:
    """Verify Claude Code CLI is available."""
    if not shutil.which("claude"):
        print("PREFLIGHT FAIL: 'claude' CLI is not installed or not on PATH.")
        print("  Fix: install Claude Code — see https://docs.anthropic.com")
        return False
    # Don't run an actual prompt — just confirm the binary exists and responds.
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print("PREFLIGHT FAIL: 'claude --version' failed.")
            return False
    except subprocess.TimeoutExpired:
        print("PREFLIGHT FAIL: 'claude --version' timed out.")
        return False
    return True


def run_preflight() -> bool:
    """Run all checks. Returns True if all pass."""
    print("Running preflight checks...")
    checks = [
        ("yt-dlp", check_yt_dlp),
        ("YouTube autocomplete", check_autocomplete),
        ("Claude Code CLI", check_claude_code),
    ]
    all_ok = True
    for name, check_fn in checks:
        ok = check_fn()
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False
    if not all_ok:
        print("\nPreflight failed. Fix the above before running the scout.")
    return all_ok


if __name__ == "__main__":
    if not run_preflight():
        sys.exit(1)
    print("\nAll preflight checks passed.")
