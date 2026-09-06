import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anthropic
import feedparser

from config import (
    ANTHROPIC_API_KEY, DB_PATH, FUNDING_KEYWORDS, MAX_ARTICLES,
    OBSIDIAN_FOLDER, OBSIDIAN_VAULT, RSS_FEEDS, SITE_OUTPUT_DIR,
)
from database import complete_run, connect, fail_run, init_db, start_run, store_analysis, store_articles
from scoring import apply_scoring
from validation import validate_and_normalize


def canonical_url(url):
    try:
        parts = urlsplit(url)
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    except Exception:
        return url


def canonical_title(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def fetch_articles(feeds, max_total):
    articles, seen_urls, seen_titles = [], set(), set()
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = str(entry.get("title", "")).strip()
                summary = str(entry.get("summary", entry.get("description", ""))).strip()
                link = canonical_url(str(entry.get("link", "")).strip())
                if not any(keyword in title.lower() for keyword in FUNDING_KEYWORDS):
                    continue
                title_key = canonical_title(title)
                if (link and link in seen_urls) or (title_key and title_key in seen_titles):
                    continue
                seen_urls.add(link)
                seen_titles.add(title_key)
                articles.append({
                    "title": title,
                    "summary": summary[:1200],
                    "link": link,
                    "published": str(entry.get("published", "")),
                    "source": feed.feed.get("title", feed_url),
                })
                if len(articles) >= max_total:
                    return articles
        except Exception as exc:
            print(f"Failed to fetch {feed_url}: {exc}")
    return articles


def extract_with_claude(articles, api_key):
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    client = anthropic.Anthropic(api_key=api_key)
    article_text = ""
    for i, a in enumerate(articles, start=1):
        article_text += f"\n[{i}] {a['title']}\nSource: {a['source']}\nSummary: {a['summary']}\nURL: {a['link']}\n"

    prompt = f"""You are an information-extraction assistant for an early-stage UK VC.

Your role is narrow: filter articles, extract facts, and return short exact evidence quotes.
Do NOT calculate a score. Do NOT assign a tier. Do NOT infer facts from general knowledge.

Skip if: HQ is outside the UK; pure market commentary; public/listed company; Series C or later.
Passing stages: Pre-Seed, Seed, Series A, Series B.

Extract: name, category [AI/DeepTech/SaaS/HealthTech/CleanTech/Other], stage, hq, description.

Signals: regulatory_driver, structural_demand, process_embedding, data_flywheel,
vertical_specificity, named_customers, strategic_investor, geography_fit,
vague_target, undifferentiated.

Only include a signal when the supplied title/summary contains direct evidence.
For every signal include a SHORT EXACT QUOTE from the supplied text.

Return ONLY JSON:
{{
  "companies": [{{
    "article_index": 1,
    "name": "Company",
    "category": "AI",
    "stage": "Seed",
    "hq": "Edinburgh, Scotland",
    "description": "One factual sentence.",
    "signals_hit": [{{"name": "geography_fit", "evidence": "exact quote"}}],
    "follow_up": ["question requiring information not in the article"]
  }}],
  "filtered_out": [{{"article_index": 2, "reason": "HQ outside UK"}}]
}}

ARTICLES
{article_text}
"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def build_stats(data, articles):
    companies = data.get("companies", [])
    return {
        "articles_ingested": len(articles),
        "companies_scored": len(companies),
        "noise_filtered_pct": round((len(articles) - len(companies)) / len(articles) * 100) if articles else 0,
        "priority_deals": sum(c.get("tier") == "priority" for c in companies),
    }


def render_html(data, today):
    stats = data["stats"]
    cards = []
    for company in data.get("companies", []):
        signals = "".join(
            f"<li><b>{s['name']}</b>: {s.get('evidence','')}</li>" for s in company.get("signals_hit", [])
        )
        cards.append(f"""<article><h2>{company['name']} <small>{company['net_score']:+d}</small></h2>
<p>{company['category']} · {company['stage']} · {company.get('hq','')}</p>
<p>{company.get('description','')}</p><ul>{signals}</ul>
<p><a href=\"{company.get('source_url','')}\">source</a></p></article>""")
    validation = data.get("validation_summary", {})
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Deal Sourcing Results</title><style>body{{max-width:900px;margin:40px auto;padding:0 20px;font-family:Georgia,serif;background:#efe7d4;color:#243a21}}article{{border:1px solid #9d9d85;padding:20px;margin:18px 0;border-radius:8px}}small{{float:right}}.stats{{padding:15px;background:#243a21;color:#e89cb1}}</style></head><body>
<h1>Deal Sourcing Results — {today}</h1><div class='stats'>Articles: {stats['articles_ingested']} · Companies: {stats['companies_scored']} · Noise filtered: {stats['noise_filtered_pct']}% · Priority: {stats['priority_deals']} · Ungrounded signals rejected: {validation.get('evidence_rejected',0)}</div>
{''.join(cards)}</body></html>"""


def save_outputs(data, today):
    site_dir = Path(SITE_OUTPUT_DIR)
    site_dir.mkdir(parents=True, exist_ok=True)
    day_path = site_dir / f"{today}.html"
    day_path.write_text(render_html(data, today), encoding="utf-8")
    dates = sorted((p.stem for p in site_dir.glob("????-??-??.html")), reverse=True)
    links = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in dates)
    (site_dir / "index.html").write_text(f"<h1>Deal Sourcing History</h1><ul>{links}</ul>", encoding="utf-8")

    if OBSIDIAN_VAULT:
        folder = Path(OBSIDIAN_VAULT) / OBSIDIAN_FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{today} Deal Sourcing Results.md").write_text(
            f"# Deal Sourcing Results — {today}\n\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n",
            encoding="utf-8",
        )
    return day_path


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = connect(DB_PATH)
    init_db(conn)
    run_id = start_run(conn)
    try:
        articles = fetch_articles(RSS_FEEDS, MAX_ARTICLES)
        if not articles:
            raise RuntimeError("No articles matched the pre-filter")
        article_ids = store_articles(conn, run_id, articles)
        data = extract_with_claude(articles, ANTHROPIC_API_KEY)
        data = validate_and_normalize(data, articles)
        data = apply_scoring(data)
        data["stats"] = build_stats(data, articles)
        data["run_id"] = run_id
        store_analysis(conn, run_id, data, article_ids)
        complete_run(conn, run_id, data["stats"], llm_calls=1)
        path = save_outputs(data, today)
        print(f"Done: {path}")
    except Exception as exc:
        fail_run(conn, run_id, exc)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
