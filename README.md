# AI-assisted VC Deal Sourcing Pipeline

An end-to-end AI data product that turns noisy startup-funding news into a structured, auditable VC sourcing workflow.

## What it does

```text
RSS sources
  ↓
Python ingestion + keyword pre-filter + deduplication
  ↓
Claude API: factual extraction + exact evidence quotes
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

The key design principle is to separate probabilistic AI output from deterministic business logic: the LLM extracts facts and evidence, while Python validates and scores them.

## Why Python + SQL?

Python is the orchestration layer: it fetches RSS feeds, calls the Claude API, validates output, applies rules, and generates the dashboard.

SQLite is the structured data store. SQL is the language used to query and analyse the stored results.

In short:

> **Python runs the workflow. SQLite stores the results. SQL asks questions of the stored results.**

## Five upgrades in this version

### 1. Better documentation

This README explains the business problem, architecture, data model, design choices, and evaluation process.

### 2. SQLite + SQL data layer

Each run is stored in relational tables:

- `runs` — one row per pipeline execution
- `articles` — articles sent to the LLM after the cheap pre-filter
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

The pipeline now validates:

- allowed categories;
- allowed funding stages;
- article-to-company linkage;
- duplicate/unknown signal names;
- whether every signal evidence quote actually appears in the supplied article text.

If evidence cannot be grounded in the source text, Python rejects that signal before scoring.

### 4. LLM extraction separated from scoring

The LLM no longer returns `net_score` or `tier`.

Instead:

```text
Claude → facts + evidence
Python → validation
Python → score = positive signals - negative signals
Python → tier assignment
```

Current tiers:

- `priority`: Pre-Seed / Seed / Series A with net score >= 3
- `watch`: Pre-Seed / Seed / Series A with net score 1–2
- `pending`: Pre-Seed / Seed / Series A with net score <= 0
- `series_b`: Series B

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

This means the project can distinguish between “we filtered 90% of articles” and “the filter is actually accurate.”

## Additional workflow improvements

Two small improvements were added because they support the same product goal:

- **Deduplication:** canonical URL/title checks reduce duplicate articles before the LLM call.
- **Run tracking:** each execution receives a `run_id`, making historical performance queryable.

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
set ANTHROPIC_API_KEY=your_key_here
python deal_scout.py
```

By default, SQLite data is written to:

```text
data/deals.db
```

and the site output is written to:

```text
docs/
```

Machine-specific local paths are no longer hard-coded. Optional overrides are shown in `.env.example`.

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

This one query demonstrates `JOIN`, `WHERE`, `COUNT`, `GROUP BY`, `HAVING`, and `ORDER BY` on a real product dataset.

## What this project demonstrates

- translating an investment workflow into data/system requirements;
- integrating an LLM into a practical business process;
- separating probabilistic extraction from deterministic rules;
- relational data modelling with SQLite;
- SQL querying and aggregation;
- data-quality controls and traceability;
- human-labelled evaluation;
- basic cost awareness through pre-filtering, deduplication, and run tracking.
