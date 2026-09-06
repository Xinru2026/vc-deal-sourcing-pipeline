import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scoring import ALL_SIGNALS, POSITIVE_SIGNALS

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL,
  articles_ingested INTEGER DEFAULT 0,
  companies_scored INTEGER DEFAULT 0,
  noise_filtered_pct INTEGER DEFAULT 0,
  priority_deals INTEGER DEFAULT 0,
  llm_calls INTEGER DEFAULT 0,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS articles (
  article_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  article_index INTEGER NOT NULL,
  title TEXT NOT NULL,
  source TEXT,
  published TEXT,
  url TEXT,
  summary TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
  UNIQUE (run_id, article_index)
);
CREATE TABLE IF NOT EXISTS companies (
  company_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  article_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  stage TEXT NOT NULL,
  hq TEXT,
  description TEXT,
  positive_score INTEGER NOT NULL,
  negative_score INTEGER NOT NULL,
  net_score INTEGER NOT NULL,
  tier TEXT NOT NULL,
  source_url TEXT,
  source_name TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
  FOREIGN KEY (article_id) REFERENCES articles(article_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS signals (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  signal_name TEXT NOT NULL,
  is_hit INTEGER NOT NULL CHECK (is_hit IN (0,1)),
  is_positive INTEGER NOT NULL CHECK (is_positive IN (0,1)),
  evidence TEXT,
  FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
  UNIQUE (company_id, signal_name)
);
CREATE TABLE IF NOT EXISTS filtered_articles (
  filtered_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  article_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
  FOREIGN KEY (article_id) REFERENCES articles(article_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_companies_tier ON companies(tier);
CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);
CREATE INDEX IF NOT EXISTS idx_signals_name_hit ON signals(signal_name, is_hit);
"""


def connect(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def start_run(conn):
    cur = conn.execute(
        "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    return cur.lastrowid


def store_articles(conn, run_id, articles):
    ids = {}
    for idx, article in enumerate(articles, start=1):
        cur = conn.execute(
            """INSERT INTO articles
               (run_id, article_index, title, source, published, url, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, idx, article.get("title", ""), article.get("source", ""),
             article.get("published", ""), article.get("link", ""), article.get("summary", "")),
        )
        ids[idx] = cur.lastrowid
    conn.commit()
    return ids


def store_analysis(conn, run_id, data, article_ids):
    for company in data.get("companies", []):
        article_id = article_ids[company["article_index"]]
        cur = conn.execute(
            """INSERT INTO companies
               (run_id, article_id, name, category, stage, hq, description,
                positive_score, negative_score, net_score, tier, source_url, source_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, article_id, company["name"], company["category"], company["stage"],
             company.get("hq", ""), company.get("description", ""),
             company.get("positive_score", 0), company.get("negative_score", 0),
             company.get("net_score", 0), company.get("tier", "pending"),
             company.get("source_url", ""), company.get("source_name", "")),
        )
        company_id = cur.lastrowid
        evidence = {s["name"]: s.get("evidence", "") for s in company.get("signals_hit", [])}
        for name in ALL_SIGNALS:
            conn.execute(
                """INSERT INTO signals
                   (company_id, signal_name, is_hit, is_positive, evidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (company_id, name, int(name in evidence), int(name in POSITIVE_SIGNALS), evidence.get(name)),
            )
    for item in data.get("filtered_out", []):
        article_id = article_ids.get(item["article_index"])
        if article_id:
            conn.execute(
                "INSERT INTO filtered_articles (run_id, article_id, reason) VALUES (?, ?, ?)",
                (run_id, article_id, item.get("reason", "filtered")),
            )
    conn.commit()


def complete_run(conn, run_id, stats, llm_calls=1):
    conn.execute(
        """UPDATE runs SET completed_at=?, status='completed', articles_ingested=?,
           companies_scored=?, noise_filtered_pct=?, priority_deals=?, llm_calls=?
           WHERE run_id=?""",
        (datetime.now(timezone.utc).isoformat(), stats.get("articles_ingested", 0),
         stats.get("companies_scored", 0), stats.get("noise_filtered_pct", 0),
         stats.get("priority_deals", 0), llm_calls, run_id),
    )
    conn.commit()


def fail_run(conn, run_id, error):
    conn.execute(
        "UPDATE runs SET completed_at=?, status='failed', error_message=? WHERE run_id=?",
        (datetime.now(timezone.utc).isoformat(), str(error)[:1000], run_id),
    )
    conn.commit()


def latest_run_id(conn):
    row = conn.execute(
        "SELECT run_id FROM runs WHERE status='completed' ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row else None
