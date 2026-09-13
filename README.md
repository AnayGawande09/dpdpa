# DPDP Compliance Analyzer

A batch pipeline that scans an uploaded dataset for potential PII exposure
and evaluates it against a configurable set of DPDP Act 2023 / DPDP Rules
2025 compliance rules, producing explainable findings and a weighted risk
score. See [SCOPE.md](SCOPE.md) for the guardrails this build stays inside.

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

**Trigger a scan:**

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

For later phases: GET/POST-without-a-file endpoints follow the same
`Invoke-RestMethod -Uri ... -Headers $Headers` pattern shown above (add
`-Method Post -Body (... | ConvertTo-Json) -ContentType "application/json"`
for JSON bodies); only file uploads need the `Invoke-FileUpload` helper.

## Demo script

_(Will be filled in during Phase 9 with the exact click path and a runnable
end-to-end walkthrough under 3 minutes.)_

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
