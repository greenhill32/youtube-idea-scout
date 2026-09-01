#!/usr/bin/env bash
# Scheduled weekly run of the YouTube Idea Scout pipeline.
# Triggered by cron (see: crontab -l). Runs the full pipeline, captures
# the outcome, and emails an alert either way — so a crash gets reported
# just as loudly as a success.
#
# Email mechanism (2026-08-22, revised): SSH to lees-mac-mini and invoke
# ~/.discovery-engine/notify.py there — plain Gmail SMTP with an app
# password from that machine's ~/.env, already working for Lee's daily
# Discovery Engine brief. Reuses existing working credentials instead of
# duplicating a Gmail app password onto this NUC. Originally this script
# used `claude -p` + the Gmail MCP connector, but that connector was
# never authenticated (`claude mcp list` showed "Needs authentication")
# and OAuth for it can't be completed non-interactively from a cron job
# anyway. See progress.txt, 2026-08-22, "Scheduled run email alerting".
# Requires: passwordless SSH to lees-mac-mini (already set up) and
# ~/.env on that machine holding GMAIL_ADDRESS / GMAIL_APP_PASSWORD.

set -uo pipefail

# cron runs with a minimal PATH that doesn't include where `claude` lives
# (/home/lee/.local/bin) -- without this, preflight's shutil.which("claude")
# and stage6's `claude` subprocess calls both fail. Bit us on the first real
# Friday run (2026-08-28, exit 1 at preflight). See progress.txt.
export PATH="/home/lee/.local/bin:$PATH"

PROJECT_DIR="/home/lee/Documents/Projects/youtube-idea-scout"
LOG_DIR="$PROJECT_DIR/data/scheduled_runs"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/${TS}.log"

send_alert() {
    # $1 = subject, body read from stdin
    ssh lees-mac-mini "python3 ~/.discovery-engine/notify.py '$1'"
}

mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR" || {
    # Can't even cd -- send what we can without the log file.
    echo "The Friday 19:30 scheduled run could not cd into $PROJECT_DIR. Nothing ran." \
        | send_alert "YouTube Idea Scout: scheduled run FAILED TO START" >/dev/null 2>&1
    exit 1
}

START_UTC="$(date -u +"%Y-%m-%d %H:%M UTC")"
python3 -u scout.py >"$LOG_FILE" 2>&1
EXIT_CODE=$?
END_UTC="$(date -u +"%Y-%m-%d %H:%M UTC")"

if [ "$EXIT_CODE" -eq 0 ]; then
    STATUS="SUCCEEDED"
    RUN_ID="$(cat "$PROJECT_DIR/data/run_id.txt" 2>/dev/null || echo "unknown")"
    TAIL="$(tail -n 20 "$LOG_FILE")"
    SUBJECT="YouTube Idea Scout: scheduled run SUCCEEDED (run_id $RUN_ID)"
    BODY="The Friday scheduled run completed successfully.

Started:  $START_UTC
Finished: $END_UTC
Run ID:   $RUN_ID
Log file: $LOG_FILE
Report:   $PROJECT_DIR/data/report.html

Last 20 lines of output:
$TAIL"
else
    STATUS="FAILED"
    TAIL="$(tail -n 40 "$LOG_FILE")"
    SUBJECT="YouTube Idea Scout: scheduled run FAILED (exit $EXIT_CODE)"
    BODY="The Friday scheduled run did not complete successfully.

Started:  $START_UTC
Ended:    $END_UTC
Exit code: $EXIT_CODE
Log file: $LOG_FILE

Last 40 lines of output:
$TAIL"
fi

echo "[$END_UTC] Scheduled run $STATUS (exit $EXIT_CODE). Log: $LOG_FILE" >> "$LOG_DIR/scheduled_runs.log"

# Send the alert. If SSH or the Mac's notify.py fails, that failure is
# recorded in scheduled_runs.log but does not affect the pipeline run
# itself (exit code below still reflects scout.py's own outcome).
echo "$BODY" | send_alert "$SUBJECT" >>"$LOG_DIR/scheduled_runs.log" 2>&1

exit "$EXIT_CODE"
