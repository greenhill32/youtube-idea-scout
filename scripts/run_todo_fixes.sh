#!/usr/bin/env bash
# Scheduled weekly maintenance run: implement whatever's queued under
# TODO.txt's NEXT section, unattended.
#
# Triggered by cron, Thursday evenings (see: crontab -l). Separate from
# scripts/run_scheduled.sh (Friday's full scout.py pipeline run) -- this
# one runs an autonomous `claude -p` coding session against this repo.
#
# Safety notes (read before changing this script):
#   - Does NOT run at all if TODO.txt's NEXT section has no unchecked
#     "[ ]" items -- checked in bash below, before any Claude session is
#     spun up, so an empty NEXT costs nothing and sends no email.
#   - Runs with --dangerously-skip-permissions because it's unattended
#     and nothing is present to approve a permission prompt. That means
#     the session has full local tool access (edit any file, run any
#     bash command) for the duration of the run. The prompt below
#     constrains it to NEXT-section work only, but the flag itself grants
#     more than that -- worth remembering if this script is ever repointed
#     at a different prompt.
#   - Does NOT git commit or push. Changes are left in the working tree
#     for human review. This is deliberate: per this project's working
#     agreement, commits only happen when explicitly requested.
#   - Emails a summary (via the same lees-mac-mini notify.py mechanism as
#     run_scheduled.sh) only when it actually did something or hit an
#     error -- not on the empty-NEXT no-op case.

set -uo pipefail

# cron runs with a minimal PATH that doesn't include where `claude` lives
# (/home/lee/.local/bin) -- this script calls `claude -p` directly, so it
# needs the same fix applied to run_scheduled.sh after the 2026-08-28
# preflight failure. See progress.txt.
export PATH="/home/lee/.local/bin:$PATH"

PROJECT_DIR="/home/lee/Documents/Projects/youtube-idea-scout"
LOG_DIR="$PROJECT_DIR/data/scheduled_runs"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/todo-fixes-${TS}.log"

send_alert() {
    # $1 = subject, body read from stdin
    ssh lees-mac-mini "python3 ~/.discovery-engine/notify.py '$1'"
}

mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR" || {
    echo "The Thursday TODO-fixes run could not cd into $PROJECT_DIR. Nothing ran." \
        | send_alert "YouTube Idea Scout: TODO-fixes run FAILED TO START" >/dev/null 2>&1
    exit 1
}

# Extract the NEXT section (between "NEXT\n----" and the next blank-then-
# header block) and check whether it has any unchecked items.
NEXT_SECTION="$(awk '/^NEXT$/{flag=1; next} /^----$/{if(flag==1){next}} /^[A-Z][A-Z ]*$/{if(flag==1 && NR>2)exit} flag' TODO.txt)"
if ! echo "$NEXT_SECTION" | grep -q '^\[ \]'; then
    echo "[$(date -u +"%Y-%m-%d %H:%M UTC")] NEXT section empty or has no unchecked items -- nothing to do, skipped." \
        >> "$LOG_DIR/todo_fixes_runs.log"
    exit 0
fi

START_UTC="$(date -u +"%Y-%m-%d %H:%M UTC")"

PROMPT="You are running as an unattended scheduled maintenance session for the
YouTube Idea Scout project at $PROJECT_DIR. Nobody is watching this run in
real time -- there is no human to ask clarifying questions of. Follow this
project's established working discipline:

1. Read TODO.txt in the project root. Implement ONLY the items currently
   listed under the NEXT section. Do not touch items under LATER or NOT NOW.
2. Read progress.txt in the project root FIRST, before touching any stage,
   for prior bugs/lessons relevant to what you're about to change. Do not
   knowingly reintroduce a previously-resolved problem.
3. For each NEXT item: implement it, then smoke-test it before moving to the
   next item. Do not mark anything done until it is implemented AND verified.
   Do not progress past a failing verification.
4. Do not change Stage 1-6 judgement/scoring/ranking logic unless the NEXT
   item explicitly calls for it. Do not add features, redesigns, or
   optimisations beyond what each NEXT item literally asks for -- no scope
   creep, this project has an explicit NOT NOW list for a reason.
5. If a NEXT item is ambiguous or you hit a genuine blocking decision only a
   human could make, do NOT guess and do NOT skip it silently. Leave it in
   NEXT with a note explaining what's blocking it (mirroring the existing
   NOTE format already used elsewhere in TODO.txt), and move on to other
   NEXT items.
6. When you finish an item (implemented + verified), move it out of NEXT
   into DONE with a short factual description of what was done and how it
   was verified -- follow the exact style of the existing DONE entries.
7. Only add an entry to progress.txt if you discover a genuine bug,
   regression, unexpected classification behaviour, or a reusable
   engineering lesson -- not for routine successful work. Follow the
   existing STATUS: RESOLVED / OPEN / WATCH format used there.
8. Do NOT run 'git commit', 'git push', or any git write operation. Leave
   all changes in the working tree uncommitted for human review.
9. Do NOT modify crontab, scripts/run_scheduled.sh, or scripts/run_todo_fixes.sh
   (this script) as part of implementing NEXT items, unless a NEXT item
   explicitly names one of those files.
10. At the end, print a concise plain-text summary: which NEXT items were
    completed, which (if any) were left blocked and why, and what files
    changed. This summary is emailed to the project owner verbatim, so
    write it for a human skimming an email, not as a chat transcript."

claude -p "$PROMPT" --dangerously-skip-permissions --model claude-sonnet-5 >"$LOG_FILE" 2>&1
EXIT_CODE=$?
END_UTC="$(date -u +"%Y-%m-%d %H:%M UTC")"

DIFF_STAT="$(git status --short 2>/dev/null | head -30)"
TAIL="$(tail -n 60 "$LOG_FILE")"

if [ "$EXIT_CODE" -eq 0 ]; then
    SUBJECT="YouTube Idea Scout: Thursday TODO-fixes run completed"
    BODY="The Thursday scheduled TODO-fixes session completed.

Started:  $START_UTC
Finished: $END_UTC
Log file: $LOG_FILE

Uncommitted changes now in the working tree (git status --short):
$DIFF_STAT

Nothing was committed or pushed -- review with 'git diff' and commit
yourself when you're happy with it.

Session output (last 60 lines):
$TAIL"
else
    SUBJECT="YouTube Idea Scout: Thursday TODO-fixes run FAILED (exit $EXIT_CODE)"
    BODY="The Thursday scheduled TODO-fixes session did not complete successfully.

Started:  $START_UTC
Ended:    $END_UTC
Exit code: $EXIT_CODE
Log file: $LOG_FILE

Uncommitted changes now in the working tree (git status --short), if any:
$DIFF_STAT

Session output (last 60 lines):
$TAIL"
fi

echo "[$END_UTC] TODO-fixes run exit $EXIT_CODE. Log: $LOG_FILE" >> "$LOG_DIR/todo_fixes_runs.log"
echo "$BODY" | send_alert "$SUBJECT" >>"$LOG_DIR/todo_fixes_runs.log" 2>&1

exit "$EXIT_CODE"
