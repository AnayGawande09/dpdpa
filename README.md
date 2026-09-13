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

## Setup

```bash
cd dpdp-compliance-analyzer
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # required from Phase 2 onward
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Verify:

```bash
curl -i http://localhost:8000/health
# expect: HTTP/1.1 200 OK  {"status":"ok","db_check":1}
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

## Demo script

_(Will be filled in during Phase 9 with the exact click path, sample login
credentials, and a runnable end-to-end walkthrough under 3 minutes.)_

## Status

Phase 0 complete: scaffold, async DB engine, Alembic wired to the async
engine, guardrails documented, `/health` doing a real DB round-trip.
