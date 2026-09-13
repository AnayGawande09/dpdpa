# DPDP Compliance Analyzer

A batch pipeline that scans an uploaded dataset for potential PII exposure
and evaluates it against a configurable set of DPDP Act 2023 / DPDP Rules
2025 compliance rules, producing explainable findings and a weighted risk
score. See [SCOPE.md](SCOPE.md) for the guardrails this build stays inside.

Uploads accept files up to `MAX_UPLOAD_MB` (`.env`, default 2048 MB / 2 GB)
and are streamed to disk in chunks rather than buffered in memory, so the
limit scales to real dataset sizes without risking an out-of-memory crash
on a large upload. Raise `MAX_UPLOAD_MB` further in `.env` if you need to
accept larger files than the default. Note this doesn't change how the
detection pipeline itself loads a file — `pandas.read_csv`/`read_excel`
still parse the whole file into memory once uploaded, so very large files
(multi-GB) will be slower to scan and use more RAM during that step; this
is a batch-pipeline tool (see `SCOPE.md`), not a streaming/chunked
processor.

## Stack

- **Backend**: FastAPI (async)
- **Database**: SQLite via SQLAlchemy (async) + aiosqlite, migrations via Alembic
- **PII detection**: regex + spaCy NER (`en_core_web_sm`) + column-name heuristics
- **Compliance rules**: versioned JSON (`app/rules/rules.json`), evaluated generically
- **Frontend**: plain HTML/CSS/JS + Chart.js
- **PDF reports**: reportlab
- **Testing**: pytest + httpx `AsyncClient`
- **Auth**: JWT (python-jose) + bcrypt — demo-grade only

## Setup (Windows PowerShell)

```powershell
cd dpdp-compliance-analyzer
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # required from Phase 2 onward
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

> **Every command below assumes the venv is activated in that shell**
> (`.\venv\Scripts\Activate.ps1`). If a module import fails (e.g.
> `ModuleNotFoundError: No module named 'pytest_asyncio'`), the venv
> isn't active in that shell — re-run the activate line first.

Verify the server is up (run in a second PowerShell window, first one is
running `uvicorn`):

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
# expect: status : ok    db_check : 1
```

## Setup (bash / macOS / Linux)

```bash
cd dpdp-compliance-analyzer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # required from Phase 2 onward
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Project layout

```
app/
  main.py          FastAPI app, router mounts, CORS
  config.py        Pydantic Settings (.env)
  db.py            Async SQLAlchemy engine/session + get_db dependency
  models/          SQLAlchemy ORM models (populated per phase)
  schemas/         Pydantic request/response schemas (populated per phase)
  routers/         auth, ingestion, pii, rules, findings, reports
  pipeline/        detection, classification, rules_engine, gap_detector, risk_engine
  rules/rules.json Versioned compliance rule library
alembic/           Async-engine migrations
frontend/          index.html, dashboard.html, static/css, static/js
reports/           Generated PDF reports land here
data/              Sample datasets for testing
```

## Demo login (seeded automatically on startup)

```
email:    admin@example.com
password: DemoPass123!
```

## Manual API testing in PowerShell

PowerShell aliases `curl` to `Invoke-WebRequest`, which does **not** accept
bash-style flags (`-X`, `-d`, `-H`, `-F`). Every manual test step in this
guide from here on uses `Invoke-RestMethod` instead — copy-paste these
patterns for any new endpoint in later phases.

**Log in and store the token** (reusable in every PowerShell session):

```powershell
$login = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
  -Method Post `
  -Body @{ username = "admin@example.com"; password = "DemoPass123!" } `
  -ContentType "application/x-www-form-urlencoded"
$TOKEN = $login.access_token
$Headers = @{ Authorization = "Bearer $TOKEN" }
```

**Upload a file** (multipart/form-data). This machine runs **Windows
PowerShell 5.1**, which has no `-Form` parameter (that's PowerShell 7+
only) — use this `Invoke-FileUpload` helper instead, defined once per
session:

```powershell
function Invoke-FileUpload {
    param([string]$Uri, [string]$FilePath, [hashtable]$Headers)
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    foreach ($key in $Headers.Keys) { $client.DefaultRequestHeaders.Add($key, $Headers[$key]) }
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileBytes = [System.IO.File]::ReadAllBytes($FilePath)
    $fileContent = New-Object System.Net.Http.ByteArrayContent(,$fileBytes)  # comma protects the array from splatting
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/csv")
    $content.Add($fileContent, "file", [System.IO.Path]::GetFileName($FilePath))
    $result = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
    $body = $result.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $client.Dispose()
    if (-not $result.IsSuccessStatusCode) { throw "Upload failed ($($result.StatusCode)): $body" }
    return $body | ConvertFrom-Json
}

$upload = Invoke-FileUpload -Uri "http://localhost:8000/datasets/upload" -FilePath "data/clean_sample.csv" -Headers $Headers
$upload
$SCAN_ID = $upload.scan_id
```

**GET a dataset's metadata:**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID" -Headers $Headers
```

**Submit processing context (required before scanning — Phase 4):**

```powershell
$context = @{
  purpose = "Marketing"
  consent_status = "Not available"
  retention_value = 5
  retention_unit = "years"
  access_scope = "Marketing,Sales"
  encryption_enabled = $false
  access_control_enabled = $false
  notice_status = "Missing"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/context" -Method Post `
  -Headers $Headers -Body $context -ContentType "application/json"
```

**Trigger a scan** (returns 400 if context hasn't been submitted yet):

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/scan" -Method Post -Headers $Headers
```

**Confirm a 404 for an unknown scan_id** (`Invoke-RestMethod` throws on
non-2xx, so wrap it to inspect the status code):

```powershell
try {
  Invoke-RestMethod -Uri "http://localhost:8000/datasets/does-not-exist" -Headers $Headers
} catch {
  $_.Exception.Response.StatusCode.value__   # expect: 404
}
```

**Confirm a 401 with no token:**

```powershell
try {
  Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID"
} catch {
  $_.Exception.Response.StatusCode.value__   # expect: 401
}
```

**Check rule evaluations after a scan (Phase 5):**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/rules" -Headers $Headers | Format-Table
```

**Check findings and risk score after a scan (Phase 6):**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/findings" -Headers $Headers | Format-List
$risk = Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/risk" -Headers $Headers
$risk.score; $risk.band; $risk.breakdown | Format-Table
```

**View scan history (paginated, Phase 7):**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets?page=1&page_size=5" -Headers $Headers
```

**Generate and download a report (Phase 8):**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/datasets/$SCAN_ID/report" -Method Post -Headers $Headers
Invoke-WebRequest -Uri "http://localhost:8000/datasets/$SCAN_ID/report" -Headers $Headers -OutFile "report.pdf"
```

**View the audit log (Phase 8):**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/audit-log?action=report_exported" -Headers $Headers
```

**View the dashboard:** open `http://localhost:5500/dashboard.html?scan_id=<SCAN_ID>` in a browser
after logging in via `index.html` in the same browser (the dashboard reuses the JWT from
`localStorage`).

For later phases: GET/POST-without-a-file endpoints follow the same
`Invoke-RestMethod -Uri ... -Headers $Headers` pattern shown above (add
`-Method Post -Body (... | ConvertTo-Json) -ContentType "application/json"`
for JSON bodies); only file uploads need the `Invoke-FileUpload` helper.

## Demo script

Runs end to end in under 3 minutes. Two terminals, then a browser.

**Terminal 1 — backend:**

```powershell
cd dpdp-compliance-analyzer
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

**Terminal 2 — frontend:**

```powershell
cd dpdp-compliance-analyzer\frontend
python -m http.server 5500
```

**In the browser**, go to `http://localhost:5500/index.html`:

1. **Log in** — email and password are pre-filled (`admin@example.com` /
   `DemoPass123!`). Click **Log in**.
2. **Upload** — click **Choose File**, pick `data/messy_sample.csv` from the
   repo (this is the "bad" dataset — no consent, no encryption, broad
   access). Click **Upload**. Row count and columns appear immediately.
3. **Processing context** — the form pre-fills with weak defaults on
   purpose. For the full "bad" demo, leave Purpose as **Other**, Consent
   status as **Unknown**/**Not available**, leave Encryption and Access
   control unchecked, leave Notice status as **Missing**. Click
   **Save context**.
4. **Scan** — click **Run Compliance Scan**. A spinner and status text show
   the scan running in the background (the button doesn't freeze — other
   tabs/requests keep working while this runs). When it finishes, click
   **View Dashboard →**.
5. **Dashboard** — you'll see: a red **alert banner** at the top (risk band
   High/Critical) with the top recommended action; a PII Summary chart; a
   Risk Score with a full points breakdown; Compliance Rule Outcomes
   (PASS/FAIL/UNKNOWN counts); a sortable Findings table (click a row to
   expand rule_id/evidence/explanation); an Audit Log panel; and Scan
   History.
6. **Download the report** — click **Download Report** in the Report panel;
   a real PDF downloads with the PII summary, every finding, the risk
   breakdown, and the required disclaimer footer.
7. **Repeat with the clean dataset** — go back to `index.html`, upload
   `data/clean_sample.csv`, this time fill the context form with strong
   values (Purpose: Marketing, Consent: Available, check both Encryption
   and Access control, Notice: Available, and put something like
   `grievance officer: privacy@example.com` in Access scope), scan, and
   view its dashboard — no alert banner this time, and the risk band is
   Low.

Sample login: `admin@example.com` / `DemoPass123!` (seeded automatically on
backend startup).

## Status

- Phase 0 complete: scaffold, async DB engine, Alembic wired to the async
  engine, guardrails documented, `/health` doing a real DB round-trip.
- Phase 1 complete: JWT auth with a seeded demo admin, file upload
  (csv/json/txt/xlsx) with validation, dataset metadata storage, a
  `/scan` stub, and a login + upload frontend page.
- Phase 2 complete: real PII detection (regex + spaCy NER + column-name
  heuristics) wired into `/scan`, agreement-based confidence scoring,
  masking on every value before it leaves the pipeline, and
  `GET /datasets/{scan_id}/pii`.
- Phase 3 complete: deterministic detector_type -> category/subtype
  classification against the 6-category DPDP taxonomy, a keyword-based
  fallback path for column_heuristic-only detections, wired into `/scan`,
  and `GET /datasets/{scan_id}/pii/summary`.
- Phase 4 complete: processing-context capture (purpose, consent,
  retention, access scope, encryption, access control, notice), a hard
  gate so `/scan` returns 400 without it, pre-filled defaults, and a
  frontend context form that blocks scanning until saved.
- Phase 5 complete: a versioned rule library (`app/rules/rules.json`, 7
  rules across all 6 DPDP categories, citations grounded in confirmed
  DPDP Act 2023 section numbers) evaluated by a fully generic engine —
  editing rules.json changes `/rules` output with zero code changes
  (verified by hand and in tests) — wired into `/scan`, plus
  `GET /datasets/{scan_id}/rules`.
- Phase 6 complete: gap detection turns every FAILed rule into a finding
  with a templated (non-LLM) explanation citing the real affected fields,
  purpose, and rule_id; an explainable weighted 0-100 risk engine with
  named weight constants and a `score_breakdown` that always sums exactly
  to the score; wired into `/scan` (which now also cleans up prior rows on
  a rescan), plus `GET /datasets/{scan_id}/findings` and
  `GET /datasets/{scan_id}/risk`. The "bad" messy-sample scenario lands at
  76/100 (High), the "good" scenario at 28/100 (Low).
- Phase 7 complete: `frontend/dashboard.html` renders live PII summary and
  risk-breakdown charts (Chart.js), a sortable/expandable findings table,
  rule pass/fail/unknown counts, and a paginated scan history — all wired
  to the real API with no mock data. An alert banner fires when the risk
  band is High/Critical or any finding is CRITICAL, showing the top
  recommended action. `GET /datasets` (paginated, newest-first) was added
  to back the scan history table. Verified in an actual headless Chromium
  session (Playwright): zero console errors, zero CORS errors, all panels
  driven by real 200 responses, banner correctly present for the "bad"
  scan and absent for the "clean" scan.
- Phase 8 complete: PDF report generation (reportlab) with dataset name,
  scan ID, timestamp, PII summary, full findings (rule_id/evidence/
  severity/remediation), risk score/breakdown, and the exact required
  disclaimer footer — handles the zero-findings case explicitly. A full
  `audit_log` (login/upload/context_submitted/scan_run/report_exported)
  is written at every one of those action points. `POST`/`GET
  /datasets/{scan_id}/report` and `GET /audit-log` (paginated, filterable
  by scan_id/user_id/action) are live; the dashboard has a working
  Download Report button and a real audit log panel. Verified end-to-end
  in a headless browser: real PDF downloaded and its extracted text
  checked for the disclaimer, findings, and risk sections.
- Phase 9 complete: `/scan` now runs as a FastAPI BackgroundTask with the
  CPU-bound pandas/spaCy work offloaded via `asyncio.to_thread`, so the
  API stays responsive during a scan (verified live: `/health` answered
  in ~0.21s during an in-flight scan, identical to its no-load baseline);
  the frontend polls `GET /datasets/{scan_id}` with a spinner instead of
  freezing the scan button. Added a "How this works" explainer panel
  (Detection → Classification → Rule Engine → Gap Detection → Risk
  Score). Audited `rules.json`: all 7 rules cite a real DPDP Act 2023
  section or an explicit "general obligation" fallback, consistent with
  SCOPE.md's no-fabricated-citations guardrail. Grepped the codebase for
  raw/unmasked PII leak paths (server has zero logging statements, and
  the only raw DataFrame reads feed straight into the masking pipeline or
  row/column-count extraction) — none found. Full end-to-end flow
  verified via headless browser on both sample datasets: login → upload →
  context → scan → dashboard (banner correct for both) → report download
  → audit log, all with zero console/CORS errors.
- Added rule **DPDP-R008 — Data Minimization**: flags PII categories
  detected in a dataset that aren't necessary for its declared purpose.
  Necessary categories are defined per purpose (Marketing, Customer
  Support, Analytics, Legal/Compliance) in
  `rules_engine.NECESSARY_CATEGORIES_BY_PURPOSE`; "Other" is intentionally
  left blank, so every detected field is flagged when the purpose is too
  generic to assess necessity against. Fits the existing generic
  rule-engine pattern (JSON rule + one registered condition function,
  zero changes to the evaluator loop) and automatically flows through the
  existing findings/risk/dashboard pipeline. The PDF report gets a new
  **Data Minimization** section: declared purpose, the necessary
  categories for that purpose, and a table of specific fields suggested
  for removal — verified live against both a Marketing-purpose scan
  (flagged `pan_num`/`aadhaar_num`/`ip_addr` as unnecessary) and an
  Other-purpose scan (blank necessary list, every field flagged).
- Redesigned the frontend as an enterprise audit-grade UI (`design-system.css`,
  shared token palette/typography/shape system): a "New Compliance Scan"
  intake page (drag-and-drop upload, step 1/2 layout, "How the Analyzer
  Works" and "Regulatory Baseline" panels) and a "Compliance Dashboard"
  with a circular risk gauge, KPI tiles (risk score, rule outcomes, PII
  fields detected, remediation urgency), an All/Failed/Passed-filterable
  findings table sourced from `GET /rules` (now enriched with each rule's
  `requirement`/`remediation` text), a weighted risk-breakdown bar list, a
  real audit-trail timeline, and scan history — all wired to the existing
  API with no mock data, plus a working re-scan button. Deliberately left
  out a couple of things from the reference mockup that weren't real:
  fabricated SHA-256 audit-hash claims (no such integrity chain exists)
  and a rule count that didn't match our actual library. Verified with a
  full headless-browser pass on both a "bad" and a "good" scan: zero
  console/JS errors throughout upload → context → scan → dashboard →
  tab-filtering → report download → re-scan.
