# Scout V2 — Stage 7, 90-Day History, Weekly Report and Codex Provider Action Plan

**Status:** Approved implementation plan  
**Target branch:** `v2-opportunity`  
**Starting point:** Stage 6 has completed a 36-channel retest and is accepted for forward progress with known warnings.  
**Primary outcome:** Every production run is retained for 90 days, a useful weekly HTML decision report is generated, and repeated runs can reveal sustained trends without introducing a hosted database or dashboard.

---

## 1. Product outcome

Scout should answer three practical questions:

1. **What are the best videos to make this week?**
2. **What changed since previous runs?**
3. **Which apparent opportunities are becoming sustained trends rather than one-off spikes?**

The report is a decision surface for a human. It must not autonomously publish, tune itself, or treat model judgements as facts.

The simplest acceptable implementation is:

- immutable per-run snapshots;
- a lightweight local SQLite history;
- deterministic cross-run comparisons;
- one polished, self-contained weekly HTML report;
- 90-day retention;
- optional Codex CLI analysis authenticated through the user's ChatGPT subscription;
- Claude Haiku retained as a configurable fallback.

Do not add a web application, external database, vector database, queue, agent framework or dashboard.

---

## 2. Current checkpoint and constraints

Before changing code, inspect:

- `git status --short`
- `git diff`
- `TODO.txt`
- `progress.txt`
- `todo_result.txt`
- `run_history.jsonl`
- `config.py`
- `scout.py`
- `stage6_opportunity.py`
- the existing Stage 7 implementation;
- existing tests;
- current files under `data/opportunity_reports/`.

Preserve all existing user and validation changes. Do not discard or overwrite an uncommitted Stage 6 prompt correction or validation evidence.

Known Stage 6 retest state:

- 36/36 cached Stage 5 channels processed;
- zero editorial failures;
- five valid clusters, all with at least three channels;
- HanWay Films remains REJECT with HIGH rights risk;
- Forbidden Mysteries remains WATCH and is not rejected merely for “Full Episode”;
- MEDIUM rights risk is never MAKE;
- monetisation histogram: MEDIUM 21, LOW 13, HIGH 1, UNKNOWN 1;
- verdicts: MAKE 12, WATCH 6, REJECT 18;
- warnings: `MAKE_RATE_HIGH`, `RIGHTS_RISK_COLLAPSE`;
- `MONETISATION_COLLAPSE` cleared;
- some monetisation prose still contains unsupported CPM, revenue, sponsorship or advertiser-demand claims.

Proceed without tuning the MAKE percentage. Preserve the remaining model-quality limitations as visible warnings. Stage 7 must not prominently repeat unsupported commercial claims.

---

## 3. Delivery phases

Implement in small, independently testable phases.

### Phase A — Record the accepted Stage 6 checkpoint

1. Preserve the failed baseline and latest retest separately in `todo_result.txt`.
2. Append the completed retest to `run_history.jsonl`; never edit historical rows.
3. Mark the retest as accepted with warnings, not a clean validation PASS.
4. Record the known unsupported-monetisation-language limitation in `progress.txt`.
5. Do not make another Stage 6 prompt change as part of this plan.

Acceptance:

- existing history remains unchanged;
- exactly one new history row is appended;
- warnings are retained;
- no Stage 1–6 input/output is silently regenerated.

### Phase B — Immutable per-run archive

Each successful or partially successful opportunity run must create:

```text
data/opportunity_runs/
└── <run_id>/
    ├── manifest.json
    ├── stage6.json
    ├── stage6_stats.json
    ├── opportunities.json
    └── report.html
```

Use the existing canonical `run_id`. Do not create a second timestamp when a run already has one.

`manifest.json` minimum fields:

```json
{
  "schema_version": 1,
  "run_id": "20260905-1830",
  "started_at": "ISO-8601 UTC",
  "completed_at": "ISO-8601 UTC",
  "pipeline_mode": "opportunity",
  "provider": "claude|codex",
  "model": "configured model name",
  "status": "PASS|ACCEPTED_WITH_WARNINGS|FAIL",
  "source_stage5_run_id": "string or null",
  "channel_count": 36,
  "verdict_counts": {
    "MAKE": 12,
    "WATCH": 6,
    "REJECT": 18
  },
  "warnings": [],
  "files": {
    "stage6": "stage6.json",
    "stage6_stats": "stage6_stats.json",
    "opportunities": "opportunities.json",
    "report": "report.html"
  }
}
```

Rules:

- archive files are immutable after a run is finalized;
- rerunning report generation for the same run must be idempotent;
- never silently overwrite different content for an existing `run_id`;
- if the same archive already exists with matching content, no-op;
- if it exists with different content, fail clearly;
- copy source JSON byte-for-byte where practical;
- report HTML is presentation; JSON remains auditable truth;
- a failed Stage 6 run may be archived if it contains useful diagnostics, but must never appear as a normal recommendation report.

Continue writing the latest convenience outputs at their current paths so existing commands do not break.

### Phase C — 90-day SQLite history

Use the already configured:

- `OPPORTUNITY_WATCHLIST_DB`
- `OPPORTUNITY_WATCH_DAYS = 90`

Create a focused history module, preferably `opportunity_history.py`. Keep database access behind explicit functions and transactions.

Recommended schema:

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    status TEXT NOT NULL,
    channel_count INTEGER NOT NULL,
    make_count INTEGER NOT NULL,
    watch_count INTEGER NOT NULL,
    reject_count INTEGER NOT NULL,
    warnings_json TEXT NOT NULL,
    archive_path TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);

CREATE TABLE channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE channel_snapshots (
    run_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    subscriber_count INTEGER,
    video_count INTEGER,
    total_views INTEGER,
    verdict TEXT NOT NULL,
    factory_fit TEXT,
    rights_risk TEXT,
    monetisation TEXT,
    saturation TEXT,
    emergence TEXT,
    verdict_reason TEXT,
    cheapest_test_video TEXT,
    PRIMARY KEY (run_id, channel_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
);

CREATE TABLE videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    published_at TEXT,
    title TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
);

CREATE TABLE video_snapshots (
    run_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    view_count INTEGER,
    baseline_views REAL,
    outlier_multiple REAL,
    PRIMARY KEY (run_id, video_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE formats (
    format_key TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    description TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE format_snapshots (
    run_id TEXT NOT NULL,
    format_key TEXT NOT NULL,
    status TEXT,
    channel_count INTEGER NOT NULL,
    channel_ids_json TEXT NOT NULL,
    PRIMARY KEY (run_id, format_key),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (format_key) REFERENCES formats(format_key)
);
```

Implementation requirements:

- enable foreign keys;
- wrap one run ingestion in one transaction;
- ingestion must be idempotent by `run_id`;
- reject conflicting re-ingestion rather than partially updating it;
- store timestamps as UTC ISO-8601;
- do not store whole unbounded source documents in SQLite;
- retain source JSON in the immutable archive;
- schema creation and migrations must be deterministic;
- include an integer schema version and a simple migration mechanism;
- no ORM is necessary.

Format identity is a risk: model-generated cluster names can drift. For V1 history, derive a stable normalized `format_key` from the cluster name and fingerprint fields, and preserve the original name. Do not claim two renamed formats are identical unless deterministic matching supports it.

### Phase D — Deterministic trend engine

Create a module such as `opportunity_trends.py`.

Trend detection must initially be deterministic and require no LLM call.

Do not report a “trend” from one run.

Suggested maturity states:

- **NEW:** first appearance;
- **REPEATING:** observed in at least two runs;
- **RISING:** evidence improves across at least three observations or three weekly runs;
- **STABLE:** recurring without material positive/negative movement;
- **FADING:** evidence weakens or disappears after repeated observation;
- **INSUFFICIENT_HISTORY:** too few comparable observations.

Minimum signals:

- number of runs observed;
- weeks observed;
- consecutive appearances;
- verdict path, such as `WATCH → WATCH → MAKE`;
- recurrence across unrelated channels;
- channel count change for a format;
- subscriber/view/outlier movement where comparable;
- first seen and last seen;
- age in days;
- whether the latest evidence is a one-run spike.

Guardrails:

- do not compare absent/null metrics as zero;
- avoid percentage growth where the baseline is zero;
- record why a state was assigned;
- distinguish channel growth from format spread;
- do not convert warnings into trend evidence;
- no model-generated predictions;
- no automatic promotion to MAKE;
- four weekly observations is a sensible point to show stronger trend language, but retain earlier “new/repeating” signals.

Expose trend results as JSON so the HTML renderer is not the only consumer.

### Phase E — Weekly decision report

Generate:

```text
data/weekly_reports/<ISO-year>-W<week>.html
data/weekly_reports/latest.html
```

Also copy the final weekly report into the corresponding immutable run archive.

The report must be self-contained HTML with no CDN or runtime network dependency.

#### Report structure

1. **Header**
   - week and generation timestamp;
   - provider/model;
   - number of runs included;
   - visible data-quality warnings.

2. **Make these this week**
   - default maximum: 5–10;
   - ranked by existing evidence and verdict logic;
   - do not invent a new opaque composite score;
   - show why it is timely;
   - show cheapest test video;
   - show evidence links;
   - show factory fit, rights risk, saturation and emergence;
   - show trend state only when supported.

3. **Rising opportunities**
   - repeated or rising formats/channels;
   - evidence of recurrence;
   - previous versus current verdict;
   - first/last seen and observation count.

4. **Watch next**
   - WATCH items closest to being actionable;
   - state the exact unresolved condition;
   - never present WATCH as MAKE.

5. **Cooling or saturated**
   - items that weakened, became saturated or lost evidence;
   - keep compact.

6. **Recurring production formats**
   - cluster name and status;
   - unrelated channel members;
   - observation history;
   - factory compatibility.

7. **Run health**
   - coverage;
   - editorial failures;
   - warnings;
   - model/provider;
   - link/path to archived run data.

8. **Compact rejects**
   - collapsed by default where HTML permits;
   - concrete rejection reason;
   - no rejected candidate displayed as recommended.

#### Presentation requirements

- polished modern SaaS-style layout;
- readable on desktop and mobile;
- accessible colour contrast;
- badges must include text, not colour alone;
- HTML-escape all model and source text;
- links use safe attributes;
- no JavaScript required for core content;
- optional small inline script only for harmless filtering/collapse;
- print-friendly;
- display “unverified monetisation commentary” warning while the known issue remains;
- unsupported CPM/RPM/revenue/sponsorship assertions must not appear in headline recommendation copy.

A weekly report should use the latest valid/accepted run in that ISO week. If multiple runs exist, it may incorporate deterministic changes across them, but must clearly identify the decision snapshot.

### Phase F — 90-day retention

Retention applies to archived run folders and SQLite historical rows older than `OPPORTUNITY_WATCH_DAYS`.

Safety requirements:

- implement a dry-run mode first;
- validate that deletion targets are direct children of the configured archive directory;
- never recursively delete a configurable, unresolved or broad path;
- never delete the latest successful/accepted run even if clock data is malformed;
- calculate age from validated manifest timestamps, not filenames alone;
- refuse deletion when a manifest is missing or malformed;
- delete database rows in dependency order inside a transaction;
- remove an archive only after database cleanup succeeds, or define and test the inverse recovery strategy;
- print each candidate and reason;
- record retention activity in logs;
- tests must use a temporary directory and temporary database;
- scheduled production invocation should support `--retention-dry-run`;
- do not enable destructive retention in cron until one real dry run has been reviewed.

Suggested commands:

```bash
python3 scout.py --mode opportunity --retention-dry-run
python3 scout.py --mode opportunity --apply-retention
```

The apply command is destructive and must be explicit. Routine report generation must not unexpectedly delete history.

### Phase G — Codex CLI provider using ChatGPT authentication

Generalize the current Claude-only call behind a provider adapter, for example:

```text
llm_provider.py
- run_json_prompt(prompt, purpose, timeout) -> dict
- ClaudeCLIProvider
- CodexCLIProvider
```

Configuration:

```python
OPPORTUNITY_STAGE6_PROVIDER = os.getenv("SCOUT_PROVIDER", "claude")
OPPORTUNITY_STAGE6_MODEL = os.getenv("SCOUT_MODEL", "haiku")
```

Do not assume the same model string is valid for both providers. Support provider-specific defaults if necessary.

Required behaviour:

- `SCOUT_PROVIDER=claude` preserves current behaviour;
- `SCOUT_PROVIDER=codex` invokes Codex CLI non-interactively;
- Codex uses the locally authenticated ChatGPT subscription session;
- do not require or silently fall back to an OpenAI API key;
- never print tokens, session files or credentials;
- check CLI availability and authentication during preflight;
- preserve timeout and fail-closed behaviour;
- parse exactly one JSON result using a provider-specific reliable output mode where available;
- malformed output, non-zero exit or timeout fails closed;
- no automatic paid retry loop;
- log provider and model in the manifest and history;
- cluster and per-channel calls use the same provider for one run unless explicitly configured otherwise.

Credit controls:

- support a preflight call-count estimate;
- print the expected number of model calls before Stage 6;
- reuse cached Stage 1–5 evidence;
- do not rerun completed channel judgements when a valid run cache exists;
- do not switch provider mid-run silently;
- allow a maximum-call guard;
- optional `--stage6-dry-run` prints intended calls without invoking a model.

Important: switching from Haiku to Codex creates a methodology boundary. Store provider/model with every run and show it in comparisons. Do not interpret provider-caused verdict changes as organic trends.

### Phase H — Pipeline integration

Preferred sequence for a normal opportunity run:

```text
Stages 0–5
    ↓
Stage 6 semantic judgement
    ↓
Validate and finalize run
    ↓
Archive immutable inputs/outputs
    ↓
Ingest history transaction
    ↓
Calculate deterministic trends
    ↓
Generate latest + weekly HTML
    ↓
Optionally run reviewed retention command
```

Update `scout.py` without breaking existing `--from 6` behaviour.

Add focused options rather than a second entrypoint where practical:

- `--provider claude|codex`;
- `--stage6-dry-run`;
- `--report-only`;
- `--history-rebuild`;
- `--retention-dry-run`;
- `--apply-retention`.

`--report-only` must not invoke a model.  
`--history-rebuild` must reconstruct SQLite deterministically from immutable archives.  
Retention must never run merely because `--report-only` was requested.

---

## 4. Ranking the weekly recommendations

Do not create another complicated scoring model.

Use a transparent ordering:

1. valid MAKE before WATCH;
2. sustained/repeating evidence before one-run evidence;
3. stronger emergence before weaker emergence;
4. LOW rights risk before MEDIUM/HIGH;
5. factory fit A before B/C/D;
6. lower saturation before higher saturation;
7. deterministic tie-breaker such as channel ID/title.

A new one-run MAKE can still appear, but label it **NEW / not yet a confirmed trend**.

The report must explain ordering in plain language.

---

## 5. Tests

Add tests before enabling scheduled use.

### Archive tests

- creates complete archive for a new run;
- idempotent on identical rerun;
- refuses conflicting same-`run_id` overwrite;
- manifest paths are relative and valid;
- latest convenience output remains available.

### Database tests

- creates schema from empty database;
- ingests one run atomically;
- identical ingestion is a no-op;
- conflicting ingestion fails without partial rows;
- foreign keys enforced;
- rebuild from archives produces equivalent history;
- null metrics remain null.

### Trend tests

Use synthetic dated fixtures:

- one observation → NEW;
- two appearances → REPEATING;
- three improving observations → RISING;
- repeated flat evidence → STABLE;
- weakening/disappearing evidence → FADING only when sufficient history exists;
- WATCH → MAKE transition recorded;
- provider change flagged as a methodology boundary;
- no division by zero;
- missing metrics do not become negative evidence.

### Report tests

- counts exactly match selected Stage 6 source;
- MAKE/WATCH/REJECT separation preserved;
- warnings visible;
- all untrusted text escaped;
- no unsupported monetisation claim promoted into recommendation summary;
- mobile viewport and print stylesheet present;
- every recommendation has an evidence path/link and reason;
- output is deterministic for fixed fixtures;
- no network dependencies.

### Retention tests

- dry run changes nothing;
- 89/90-day boundary is explicit and tested;
- malformed manifest is retained and warned;
- paths outside archive root are refused;
- latest accepted run protected;
- apply deletes only exact eligible fixtures;
- SQLite and filesystem remain consistent after simulated failure.

### Provider tests

Mock subprocess calls:

- Claude valid JSON;
- Codex valid JSON;
- non-zero exit;
- timeout;
- malformed JSON;
- wrong schema;
- unavailable CLI;
- unauthenticated Codex;
- maximum-call guard;
- provider/model written to manifest.

Do not spend model credits in unit tests.

---

## 6. Verification with current data

After implementation:

1. Run all deterministic tests.
2. Run `--report-only` against the accepted 36-channel Stage 6 output.
3. Confirm no LLM invocation occurs.
4. Inspect the weekly HTML at desktop and mobile widths.
5. Confirm:
   - 12 MAKE;
   - 6 WATCH;
   - 18 REJECT;
   - five valid clusters;
   - warnings visible;
   - HanWay Films not recommended;
   - Forbidden Mysteries represented as WATCH;
   - unsupported monetisation claims not used as headline evidence.
6. Rebuild the SQLite database from the archive and compare row counts.
7. Run retention in dry-run mode only.
8. Test Codex provider with the cheapest possible single synthetic/fixture-backed prompt or an explicit preflight, not another 36-channel production run.
9. Report the estimated call count before any future full provider comparison.

Do not rerun Stages 1–5 for this verification.

---

## 7. Documentation updates

Update:

- `README.md`: normal weekly run, report-only, history rebuild and provider selection;
- `TODO.txt`: replace completed plan items with concise verification/operations follow-ups;
- `progress.txt`: architecture decisions, known model limitations and methodology-boundary warning;
- sample environment/config documentation;
- cron documentation, but do not activate destructive retention automatically.

Document recovery:

- delete/rebuild `watchlist.db` from immutable archives;
- regenerate weekly HTML with `--report-only`;
- diagnose an incomplete archive;
- switch back to Claude provider;
- verify Codex ChatGPT authentication without exposing credentials.

---

## 8. Commit strategy

Keep commits reviewable:

1. `docs: add Stage 7 history and weekly report plan`
2. `feat: archive opportunity runs and persist history`
3. `feat: add deterministic opportunity trend analysis`
4. `feat: generate weekly opportunity decision report`
5. `feat: add codex cli analysis provider`
6. `test: cover history reporting retention and providers`
7. `docs: document weekly operation and recovery`

Do not mix another Stage 6 prompt-tuning experiment into these commits.

Do not commit runtime databases, credentials, CLI authentication state or large generated caches. Decide deliberately whether small fixture archives and representative generated HTML belong under `tests/fixtures/`.

---

## 9. Definition of done

This work is complete when:

- every finalized run produces an immutable archive;
- 90 days of history can be reconstructed from archives;
- SQLite ingestion is atomic and idempotent;
- a polished self-contained weekly HTML report identifies the best current options;
- repeated observations expose transparent NEW/REPEATING/RISING/STABLE/FADING states;
- provider/model changes are visible and never mistaken for organic trends;
- report-only and trend generation use no model credits;
- Codex CLI can be selected using ChatGPT subscription authentication;
- Claude Haiku remains available as fallback;
- the existing pipeline and `--from 6` workflow still work;
- retention is safe, explicit and dry-run tested;
- deterministic tests pass;
- the current 36-channel data produces correct counts and warnings;
- no unsupported monetisation speculation is elevated into recommendation headlines;
- no dashboard, hosted database or unnecessary infrastructure has been added.

---

## 10. Stop conditions

Stop and report rather than guessing if:

- existing uncommitted changes conflict with these files;
- the accepted Stage 6 output is missing or does not contain all 36 channels;
- archive identity cannot be tied to a reliable `run_id`;
- the existing Stage 7 implementation materially differs from this plan;
- Codex CLI authentication is unavailable;
- implementing Codex would require an API key despite the subscription requirement;
- retention cannot prove its deletion boundary;
- a schema change would destroy existing history;
- a model call would be required merely to rebuild reports or trends.

When stopped, leave changes non-destructive and provide the smallest next action.
