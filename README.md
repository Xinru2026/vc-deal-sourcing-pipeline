# AI-assisted VC Deal Sourcing Pipeline

An end-to-end AI data product that turns noisy startup-funding news into a structured, auditable VC sourcing workflow.

## What it does

```text
RSS sources
  ↓
Python ingestion + keyword pre-filter + deduplication
  ↓
OpenAI GPT-5.3-Codex API: factual extraction + exact evidence quotes
  ↓
Python validation: schema checks + evidence grounding
  ↓
Python deterministic scoring
  ↓
SQLite relational database
  ↓
SQL analysis + HTML dashboard
  ↓
Human review + evaluation
```

The key design principle is to separate probabilistic AI output from deterministic business logic: the model extracts facts and evidence, while Python validates and scores them.

## Why Python + SQL?

Python is the orchestration layer: it fetches RSS feeds, calls the OpenAI API, validates output, applies rules, and generates the dashboard.

SQLite is the structured data store. SQL is the language used to query and analyse the stored results.

> **Python runs the workflow. SQLite stores the results. SQL asks questions of the stored results.**

## Five upgrades in this version

### 1. Better documentation

This README explains the business problem, architecture, data model, design choices, and evaluation process.

### 2. SQLite + SQL data layer

Each run is stored in relational tables:

- `runs` — one row per pipeline execution
- `articles` — articles sent to the model after the cheap pre-filter
- `companies` — validated company-level output
- `signals` — one row per company/signal, including evidence
- `filtered_articles` — screening decisions and reasons

Example query:

```sql
SELECT category, COUNT(*) AS company_count
FROM companies
GROUP BY category
ORDER BY company_count DESC;
```

More examples are in [`sql/examples.sql`](sql/examples.sql).

### 3. Data-quality validation

The pipeline validates:

- allowed categories;
- allowed funding stages;
- article-to-company linkage;
- duplicate/unknown signal names;
- whether every signal evidence quote actually appears in the supplied article text.

If evidence cannot be grounded in the source text, Python rejects that signal before scoring.

### 4. LLM extraction separated from scoring

The model no longer returns `net_score` or `tier`.

```text
GPT-5.3-Codex → facts + exact evidence
Python → validation
Python → score = positive signals - negative signals
Python → tier assignment
```

Current tiers:

- `priority`: Pre-Seed / Seed / Series A with net score >= 3
- `watch`: Pre-Seed / Seed / Series A with net score 1–2
- `pending`: Pre-Seed / Seed / Series A with net score <= 0
- `series_b`: Series B

The OpenAI call also uses Structured Outputs with a JSON schema so the extraction format is machine-checkable before the existing validation layer runs.

### 5. Evaluation framework

After running the pipeline, export a sample:

```bash
python evaluation/export_sample.py --sample-size 50
```

Fill `human_label` in `evaluation/labels.csv`:

- `1` = relevant early-stage UK deal
- `0` = not relevant

Then run:

```bash
python evaluation/evaluate.py
```

The script reports precision, recall, F1, accuracy, TP, FP, TN, and FN.

## Additional workflow improvements

- **Deduplication:** canonical URL/title checks reduce duplicate articles before the model call.
- **Run tracking:** each execution receives a `run_id`, making historical performance queryable.
- **Structured Outputs:** OpenAI is constrained to the expected extraction schema.
- **Environment-based configuration:** API keys and machine-specific paths are not hard-coded.

## Original prototype result

The original 2026-06-22 dashboard processed **40 articles**, surfaced **4 companies**, and marked **3 as priority**, corresponding to **90% of articles being filtered**.

Those figures describe one prototype run only. They are not accuracy metrics; precision/recall should only be reported after human labelling.

## Repository structure

```text
.
├── deal_scout.py             # backward-compatible entry point
├── pipeline.py               # upgraded end-to-end workflow
├── config.py                 # environment-based configuration
├── database.py               # SQLite schema and persistence
├── scoring.py                # deterministic business rules
├── validation.py             # schema + evidence grounding checks
├── evaluation/
│   ├── export_sample.py
│   └── evaluate.py
├── sql/
│   └── examples.sql
├── docs/                     # GitHub Pages output
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
set OPENAI_API_KEY=your_key_here
set OPENAI_MODEL=gpt-5.3-codex
python deal_scout.py
```

For PowerShell:

```powershell
$env:OPENAI_API_KEY="your_key_here"
$env:OPENAI_MODEL="gpt-5.3-codex"
python deal_scout.py
```

For a cheap first test, also set:

```text
MAX_ARTICLES=10
```

By default, SQLite data is written to:

```text
data/deals.db
```

and site output is written to:

```text
docs/
```

Optional overrides are shown in `.env.example`.

### API access note

Using the Codex desktop app through a ChatGPT plan and calling the OpenAI API from Python are separate access paths. This pipeline uses the OpenAI API and therefore needs an `OPENAI_API_KEY` with API billing/access. The model is configurable through `OPENAI_MODEL`; the default is `gpt-5.3-codex`.

## Useful SQL for an interview walkthrough

```sql
SELECT
    c.name,
    COUNT(*) AS positive_signals
FROM companies c
JOIN signals s
    ON c.company_id = s.company_id
WHERE s.is_hit = 1
  AND s.is_positive = 1
GROUP BY c.company_id, c.name
HAVING COUNT(*) >= 3
ORDER BY positive_signals DESC;
```

This query demonstrates `JOIN`, `WHERE`, `COUNT`, `GROUP BY`, `HAVING`, and `ORDER BY` on a real product dataset.

## What this project demonstrates

- translating an investment workflow into data/system requirements;
- integrating an OpenAI model into a practical business process;
- separating probabilistic extraction from deterministic rules;
- relational data modelling with SQLite;
- SQL querying and aggregation;
- data-quality controls and traceability;
- human-labelled evaluation;
- basic cost awareness through pre-filtering, deduplication, and run tracking.
