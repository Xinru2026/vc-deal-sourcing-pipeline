import feedparser
import anthropic
import os
import json
import re
import shutil
from datetime import datetime

# ── 配置区 ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

OBSIDIAN_VAULT = r"C:\Users\zxr\Documents"
OBSIDIAN_FOLDER = "PXN Deal Sourcing Results"

# GitHub Pages 输出目录（本地 repo 路径）
SITE_OUTPUT_DIR = r"D:\Zinnia桌面\个人管理\2-出国\1-爱丁堡\09-工作\PXN\docs"

RSS_FEEDS = [
    "https://www.uktech.news/feed",
    "https://sifted.eu/feed",
    "https://www.beauhurst.com/blog/feed/",
    "https://www.businesscloud.co.uk/feed/",
    "https://techcrunch.com/feed/",
    "https://www.eu-startups.com/feed/",
    "https://www.finsmes.com/feed/",
    "https://www.insider.co.uk/feed/",
    "https://www.prolificnorth.co.uk/feed/",
    "https://technation.io/feed/",
    "https://www.scotsman.com/business/feed",
]

FUNDING_KEYWORDS = [
    "funding", "raises", "raised", "investment", "seed", "series a", "series b",
    "backed", "venture", "million", "£", "$m", "grant", "pre-seed", "fundraise",
    "investors", "capital", "round"
]

MAX_ARTICLES = 40
# ────────────────────────────────────────────────────────


def fetch_articles(feeds, max_total):
    articles = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                published = entry.get("published", "")

                if not any(kw in title.lower() for kw in FUNDING_KEYWORDS):
                    continue

                articles.append({
                    "title": title,
                    "summary": summary[:800],
                    "link": link,
                    "published": published,
                    "source": feed.feed.get("title", url),
                })
                if len(articles) >= max_total:
                    return articles
        except Exception as e:
            print(f"   ⚠️  Failed to fetch {url}: {e}")
    return articles


def screen_and_analyse(articles, api_key):
    """用 Claude 筛选并返回结构化 JSON"""
    client = anthropic.Anthropic(api_key=api_key)

    article_list = ""
    for i, a in enumerate(articles):
        article_list += f"\n[{i+1}] {a['title']}\nSource: {a['source']}\nSummary: {a['summary']}\nURL: {a['link']}\n"

    screening_prompt = f"""You are a deal sourcing assistant for PXN Ventures, an Edinburgh-based early-stage technology VC managing £750m+ AUM with 160+ portfolio companies. PXN invests from Pre-Seed to Series B, with a focus on Scotland and the North of England.

Your job is NOT to judge whether a company is a good investment. Your job is to extract facts from today's news, count how many signals are present, and present ranked cards so the investment team can make their own judgement.

---

STEP 1 — FILTER
Skip the article if ANY of the following apply:
(1) The company is headquartered outside the UK
(2) Pure market commentary with no specific identifiable company
(3) The company is listed / publicly traded
(4) The funding round is Series C or later

If it covers an identifiable early-stage private UK company at Pre-Seed, Seed, Series A, or Series B → proceed.

---

STEP 2 — EXTRACT FIELDS
Fill from the article text. If not mentioned, write "not mentioned".

- Company name
- Category: [AI / DeepTech / SaaS / HealthTech / CleanTech / Other]
- Funding stage: [Pre-Seed / Seed / Series A / Series B]
- HQ location
- One-line business description

---

STEP 3 — SCORE SIGNALS
Only score +1 if the article contains DIRECT, EXPLICIT evidence.

POSITIVE signals (+1 each if explicitly evidenced):
- regulatory_driver: regulation/compliance mandate cited as direct demand driver
- structural_demand: labour shortage, supply chain risk, or structural problem cited
- process_embedding: product embedded in workflows, high switching cost, multi-year contracts
- data_flywheel: proprietary dataset, model improves with use, accuracy increases over time
- vertical_specificity: specific sub-industry or use case named (not "various industries")
- named_customers: specific named organisations as customers
- strategic_investor: named specialist/strategic investor (not generic seed fund)
- geography_fit: Scotland or North of England HQ or strong regional connection

NEGATIVE signals (-1 each):
- vague_target: value proposition applies to everyone, no specific segment
- undifferentiated: described as all-in-one or replaceable by ChatGPT

---

STEP 4 — CLASSIFY
- tier "priority": Pre-Seed/Seed/Series A with net score ≥ 3
- tier "watch": Pre-Seed/Seed/Series A with net score 1-2
- tier "series_b": Series B (any score)
- tier "pending": Pre-Seed/Seed/Series A with net score ≤ 0

---

STEP 5 — OUTPUT
Respond with ONLY a JSON object, no markdown, no explanation. Format:

{{
  "stats": {{
    "articles_ingested": <total articles received>,
    "companies_scored": <number that passed filter>,
    "noise_filtered_pct": <percentage filtered out as integer>
  }},
  "companies": [
    {{
      "name": "Company Name",
      "category": "AI",
      "stage": "Seed",
      "hq": "Edinburgh, Scotland",
      "description": "One-line description.",
      "net_score": 5,
      "tier": "priority",
      "signals_hit": [
        {{"name": "data_flywheel", "evidence": "direct quote from article"}},
        {{"name": "geography_fit", "evidence": "direct quote from article"}}
      ],
      "signals_missing": ["process_embedding", "named_customers"],
      "follow_up": [
        "Specific question to resolve before progressing",
        "Another follow-up question"
      ],
      "source_url": "https://...",
      "source_name": "uktech.news"
    }}
  ],
  "filtered_out": [
    {{"index": 2, "title": "Article title", "reason": "HQ outside UK"}},
    {{"index": 3, "title": "Article title", "reason": "Market commentary"}}
  ]
}}

Sort companies by net_score descending within each tier.

---
{article_list}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": screening_prompt}]
    )

    raw = message.content[0].text.strip()
    # strip markdown fences if present
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ── HTML generation ──────────────────────────────────────

SIGNAL_LABELS = {
    "regulatory_driver":   "Regulatory driver",
    "structural_demand":   "Structural demand driver",
    "process_embedding":   "Process embedding",
    "data_flywheel":       "Data flywheel",
    "vertical_specificity":"Vertical specificity",
    "named_customers":     "Named customer validation",
    "strategic_investor":  "Strategic investor",
    "geography_fit":       "Geography fit",
    "vague_target":        "Vague target (−1)",
    "undifferentiated":    "Undifferentiated (−1)",
}

CSS = """
:root {
  --green:      #2e4a2a;
  --green-deep: #243a21;
  --green-lite: #3a5a36;
  --pink:       #e89cb1;
  --pink-deep:  #d27e96;
  --cream:      #efe7d4;
  --cream-2:    #e6dcc4;
  --ink:        #1a1a17;
  --serif: "Source Serif 4", "Source Serif Pro", Georgia, serif;
  --mono:  "JetBrains Mono", ui-monospace, Menlo, monospace;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--cream); color: var(--ink); font-family: var(--serif); font-size: 15px; line-height: 1.55; }

header { background: var(--green); color: var(--pink); padding: 36px 60px 32px; display: flex; align-items: flex-end; justify-content: space-between; gap: 40px; }
.logo-eyebrow { font-family: var(--mono); font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--pink); opacity: 0.7; margin-bottom: 8px; }
.logo-title { font-family: var(--serif); font-size: 52px; font-weight: 500; line-height: 0.95; letter-spacing: -0.02em; color: var(--pink); }
.header-date { font-family: var(--mono); font-size: 13px; letter-spacing: 0.1em; color: var(--pink); opacity: 0.65; }

.stats-row { background: var(--green-deep); display: flex; border-bottom: 1px solid rgba(232,156,177,0.15); }
.stat-cell { flex: 1; padding: 20px 32px; border-right: 1px solid rgba(232,156,177,0.12); }
.stat-cell:last-child { border-right: none; }
.stat-num { font-family: var(--serif); font-size: 36px; font-weight: 500; color: var(--pink); line-height: 1; }
.stat-lbl { font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--pink); opacity: 0.5; margin-top: 4px; }

.filter-bar { background: var(--cream-2); padding: 14px 60px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid rgba(46,74,42,0.15); }
.filter-lbl { font-family: var(--mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--green); opacity: 0.6; margin-right: 4px; }
.fbtn { font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; padding: 5px 14px; border: 1px solid rgba(46,74,42,0.3); background: transparent; color: var(--green); border-radius: 2px; cursor: pointer; transition: all 0.15s; }
.fbtn:hover, .fbtn.on { background: var(--green); color: var(--pink); border-color: var(--green); }

main { padding: 48px 60px 72px; max-width: 1200px; }

.section-head { display: flex; align-items: baseline; gap: 20px; margin: 44px 0 20px; padding-bottom: 10px; border-bottom: 1.5px solid var(--green); }
.section-head:first-child { margin-top: 0; }
.section-head h2 { font-family: var(--serif); font-size: 28px; font-weight: 500; color: var(--green); letter-spacing: -0.01em; }
.s-meta { font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--green); opacity: 0.5; }

.card { background: var(--cream); border: 1.5px solid rgba(46,74,42,0.2); border-radius: 4px; margin-bottom: 16px; overflow: hidden; transition: border-color 0.15s, box-shadow 0.15s; }
.card:hover { border-color: var(--green); box-shadow: 0 2px 16px rgba(46,74,42,0.08); }
.card.priority { border-color: var(--green); background: #f7f3e8; }

.card-strip { background: var(--green); padding: 16px 28px; display: flex; align-items: baseline; justify-content: space-between; gap: 20px; }
.card-company { font-family: var(--serif); font-size: 22px; font-weight: 500; color: var(--pink); letter-spacing: -0.01em; }
.score-big { font-family: var(--serif); font-size: 40px; font-weight: 500; color: var(--pink); line-height: 1; }
.score-lbl { font-family: var(--mono); font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--pink); opacity: 0.6; }

.tags { padding: 10px 28px; display: flex; gap: 8px; align-items: center; border-bottom: 1px solid rgba(46,74,42,0.1); background: var(--cream-2); }
.tag { font-family: var(--mono); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 10px; border-radius: 2px; }
.tag-cat { background: var(--green); color: var(--pink); }
.tag-stage { background: var(--pink); color: var(--green-deep); }
.tag-priority { border: 1px solid var(--green); color: var(--green); background: transparent; }

.card-body { padding: 22px 28px 20px; }
.card-desc { font-family: var(--serif); font-size: 14px; color: var(--ink); opacity: 0.75; margin-bottom: 18px; line-height: 1.5; font-style: italic; max-width: 820px; }

.bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.bar-lbl { font-family: var(--mono); font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--green); opacity: 0.6; width: 110px; flex-shrink: 0; }
.bar-track { flex: 1; height: 4px; background: rgba(46,74,42,0.12); border-radius: 2px; max-width: 320px; }
.bar-fill { height: 100%; background: var(--green); border-radius: 2px; }
.bar-val { font-family: var(--mono); font-size: 10px; color: var(--green); opacity: 0.7; }

.sig-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 28px; margin-bottom: 18px; }
.sig-row { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.4; }
.sig-icon { font-family: var(--mono); font-size: 11px; font-weight: 700; flex-shrink: 0; width: 14px; margin-top: 1px; }
.sig-hit .sig-icon { color: var(--green); }
.sig-miss .sig-icon { color: rgba(46,74,42,0.25); }
.sig-hit .sig-name { color: var(--ink); }
.sig-miss .sig-name { color: rgba(46,74,42,0.4); }
.sig-evidence { font-size: 11px; color: rgba(26,26,23,0.5); font-style: italic; line-height: 1.4; padding-left: 22px; margin-top: 1px; margin-bottom: 4px; }

.flags-block { border-top: 1px solid rgba(46,74,42,0.12); padding-top: 14px; margin-top: 6px; }
.flags-hed { font-family: var(--mono); font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--pink-deep); margin-bottom: 8px; }
.flag-item { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: rgba(26,26,23,0.6); margin-bottom: 4px; line-height: 1.4; }
.flag-dot { color: var(--pink-deep); flex-shrink: 0; font-size: 10px; margin-top: 2px; }

.card-foot { padding: 10px 28px; border-top: 1px solid rgba(46,74,42,0.1); background: var(--cream-2); }
.src-link { font-family: var(--mono); font-size: 9px; letter-spacing: 0.1em; color: var(--green); opacity: 0.55; text-decoration: none; transition: opacity 0.15s; }
.src-link:hover { opacity: 1; }

.log-block { background: var(--cream-2); border: 1.5px solid rgba(46,74,42,0.15); border-radius: 4px; padding: 24px 28px; margin-top: 8px; }
.log-title { font-family: var(--mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--green); opacity: 0.6; margin-bottom: 14px; }
table.log { width: 100%; border-collapse: collapse; font-size: 12px; }
table.log th { font-family: var(--mono); font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--green); opacity: 0.5; padding: 0 12px 8px 0; text-align: left; border-bottom: 1px solid rgba(46,74,42,0.15); }
table.log td { padding: 7px 12px 7px 0; border-bottom: 1px solid rgba(46,74,42,0.08); color: rgba(26,26,23,0.55); vertical-align: top; }
table.log tr:last-child td { border-bottom: none; }
table.log td:first-child { font-family: var(--mono); font-size: 10px; width: 28px; opacity: 0.4; }
table.log td:nth-child(2) { font-weight: 500; color: rgba(26,26,23,0.75); width: 200px; }
"""

JS = """
(function buildFilters() {
  const bar = document.getElementById('filter-bar');
  const cards = [...document.querySelectorAll('.card')];
  const cats = [...new Set(cards.map(c => c.dataset.cat).filter(Boolean))].sort();
  const buttons = [
    { label: 'All', type: 'all' },
    { label: 'Priority', type: 'priority' },
    ...cats.map(c => ({ label: c, type: c }))
  ];
  buttons.forEach((b, i) => {
    const btn = document.createElement('button');
    btn.className = 'fbtn' + (i === 0 ? ' on' : '');
    btn.textContent = b.label;
    btn.onclick = () => doFilter(b.type, btn);
    bar.appendChild(btn);
  });
})();

function doFilter(type, btn) {
  document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.card').forEach(c => {
    if (type === 'all') c.style.display = '';
    else if (type === 'priority') c.style.display = c.dataset.tier === 'priority' ? '' : 'none';
    else c.style.display = c.dataset.cat === type ? '' : 'none';
  });
  const log = document.getElementById('log-block');
  const logHead = document.getElementById('sh-log');
  if (log) log.style.display = type === 'all' ? '' : 'none';
  if (logHead) logHead.style.display = type === 'all' ? '' : 'none';
  ['sh-priority','sh-watch','sh-series-b','sh-pending'].forEach(id => {
    const sh = document.getElementById(id);
    if (!sh) return;
    const tier = sh.dataset.tier;
    const hasVisible = [...document.querySelectorAll(`.card[data-tier="${tier}"]`)]
      .some(c => c.style.display !== 'none');
    sh.style.display = hasVisible ? '' : 'none';
  });
}
"""


def _e(text):
    """HTML-escape"""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_card(c):
    tier = c.get("tier", "watch")
    is_priority = tier == "priority"
    score = c.get("net_score", 0)
    total_positive = 8
    bar_pct = max(0, min(100, int(score / total_positive * 100)))

    signals_hit = c.get("signals_hit", [])
    signals_missing = c.get("signals_missing", [])
    follow_up = c.get("follow_up", [])

    # build signal rows
    sig_rows = ""
    for s in signals_hit:
        label = SIGNAL_LABELS.get(s["name"], s["name"])
        evidence = _e(s.get("evidence", ""))
        sig_rows += f"""
        <div>
          <div class="sig-row sig-hit"><span class="sig-icon">✓</span><span class="sig-name">{_e(label)}</span></div>
          <div class="sig-evidence">{evidence}</div>
        </div>"""
    for name in signals_missing:
        label = SIGNAL_LABELS.get(name, name)
        sig_rows += f"""
        <div>
          <div class="sig-row sig-miss"><span class="sig-icon">–</span><span class="sig-name">{_e(label)}</span></div>
        </div>"""

    flags_html = ""
    if follow_up:
        items = "".join(f'<div class="flag-item"><span class="flag-dot">▸</span>{_e(f)}</div>' for f in follow_up)
        flags_html = f'<div class="flags-block"><div class="flags-hed">Manual follow-up</div>{items}</div>'

    priority_tag = '<span class="tag tag-priority">Priority</span>' if is_priority else ""
    score_sign = f"+{score}" if score >= 0 else str(score)

    return f"""
  <div class="card {'priority' if is_priority else ''}" data-cat="{_e(c.get('category',''))}" data-tier="{_e(tier)}">
    <div class="card-strip">
      <div class="card-company">{_e(c.get('name',''))}</div>
      <div>
        <div class="score-big">{score_sign}</div>
        <div class="score-lbl">Net score</div>
      </div>
    </div>
    <div class="tags">
      <span class="tag tag-cat">{_e(c.get('category',''))}</span>
      <span class="tag tag-stage">{_e(c.get('stage',''))} · {_e(c.get('hq',''))}</span>
      {priority_tag}
    </div>
    <div class="card-body">
      <div class="card-desc">{_e(c.get('description',''))}</div>
      <div class="bar-row">
        <span class="bar-lbl">Signal strength</span>
        <div class="bar-track"><div class="bar-fill" style="width:{bar_pct}%"></div></div>
        <span class="bar-val">{len(signals_hit)} / {total_positive}</span>
      </div>
      <div class="sig-grid">{sig_rows}</div>
      {flags_html}
    </div>
    <div class="card-foot">
      <a class="src-link" href="{_e(c.get('source_url',''))}" target="_blank">{_e(c.get('source_name',''))} →</a>
    </div>
  </div>"""


TIER_CONFIG = [
    ("priority",  "sh-priority",  "Priority",    "Net score ≥ 3"),
    ("watch",     "sh-watch",     "Worth a look","Net score 1–2"),
    ("series_b",  "sh-series-b",  "Series B watch", "Lower priority"),
    ("pending",   "sh-pending",   "Pending",     "Net score ≤ 0"),
]


def render_html(data, today):
    stats = data.get("stats", {})
    companies = data.get("companies", [])
    filtered_out = data.get("filtered_out", [])

    # stats bar
    stats_html = f"""
<div class="stats-row">
  <div class="stat-cell"><div class="stat-num">{stats.get('articles_ingested', '—')}</div><div class="stat-lbl">Articles ingested</div></div>
  <div class="stat-cell"><div class="stat-num">{stats.get('companies_scored', len(companies))}</div><div class="stat-lbl">Companies scored</div></div>
  <div class="stat-cell"><div class="stat-num">{stats.get('noise_filtered_pct', '—')}%</div><div class="stat-lbl">Noise filtered</div></div>
  <div class="stat-cell"><div class="stat-num">{sum(1 for c in companies if c.get('tier')=='priority')}</div><div class="stat-lbl">Priority deals</div></div>
  <div class="stat-cell"><div class="stat-num">10</div><div class="stat-lbl">Signals tracked</div></div>
</div>"""

    # cards grouped by tier
    cards_html = ""
    for tier_key, sh_id, label, meta in TIER_CONFIG:
        tier_companies = [c for c in companies if c.get("tier") == tier_key]
        if not tier_companies:
            continue
        count = len(tier_companies)
        cards_html += f"""
  <div class="section-head" id="{sh_id}" data-tier="{tier_key}">
    <h2>{label}</h2>
    <span class="s-meta">{meta} · {count} {'company' if count==1 else 'companies'}</span>
  </div>"""
        for c in tier_companies:
            cards_html += render_card(c)

    # filter log
    log_rows = ""
    for f in filtered_out:
        log_rows += f"<tr><td>{_e(f.get('index',''))}</td><td>{_e(f.get('title',''))}</td><td>{_e(f.get('reason',''))}</td></tr>"

    log_html = ""
    if log_rows:
        log_html = f"""
  <div class="section-head" id="sh-log">
    <h2>Articles filtered out</h2>
    <span class="s-meta">{len(filtered_out)} skipped at Step 1</span>
  </div>
  <div class="log-block" id="log-block">
    <div class="log-title">Step 1 filter decisions</div>
    <table class="log">
      <thead><tr><th>#</th><th>Article</th><th>Reason skipped</th></tr></thead>
      <tbody>{log_rows}</tbody>
    </table>
  </div>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>PXN Deal Sourcing Results — {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,500;8..60,600;8..60,700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
<style>{CSS}</style>
</head>
<body>
<header>
  <div>
    <div class="logo-eyebrow">PXN Ventures</div>
    <div class="logo-title">Deal Sourcing Results</div>
  </div>
  <div class="header-date">{today}</div>
</header>
{stats_html}
<div class="filter-bar" id="filter-bar">
  <span class="filter-lbl">Show</span>
</div>
<main>
{cards_html}
{log_html}
</main>
<script>{JS}</script>
</body>
</html>"""


# ── Index page ───────────────────────────────────────────

def render_index(run_dates):
    """生成首页，列出所有历史 run"""
    rows = ""
    for date in sorted(run_dates, reverse=True):
        rows += f'<div class="run-row"><a class="run-link" href="{date}.html">{date}</a><span class="run-arrow">→</span></div>\n'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>PXN Deal Sourcing Results</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,500;8..60,600;8..60,700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
<style>
{CSS}
.index-wrap {{ padding: 48px 60px; max-width: 640px; }}
.index-intro {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--green); opacity: 0.5; margin-bottom: 32px; }}
.run-row {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid rgba(46,74,42,0.12); }}
.run-row:first-of-type {{ border-top: 1.5px solid var(--green); }}
.run-link {{ font-family: var(--serif); font-size: 20px; font-weight: 500; color: var(--green); text-decoration: none; letter-spacing: -0.01em; transition: opacity 0.15s; }}
.run-link:hover {{ opacity: 0.6; }}
.run-arrow {{ font-family: var(--mono); font-size: 12px; color: var(--green); opacity: 0.3; }}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo-eyebrow">PXN Ventures</div>
    <div class="logo-title">Deal Sourcing Results</div>
  </div>
</header>
<div class="index-wrap">
  <div class="index-intro">All runs · most recent first</div>
  {rows}
</div>
</body>
</html>"""


# ── Save functions ───────────────────────────────────────

def save_to_obsidian(analysis_text, vault_path, folder_name, today):
    folder = os.path.join(vault_path, folder_name)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{today} Deal Sourcing Results.md")
    content = f"# PXN Deal Sourcing Results — {today}\n\n*Auto-generated by deal_scout.py*\n\n---\n\n{json.dumps(analysis_text, indent=2)}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def save_to_site(data, site_dir, today):
    """生成 HTML 并写入 docs/ 目录，更新 index.html"""
    os.makedirs(site_dir, exist_ok=True)

    # write today's page
    html = render_html(data, today)
    day_path = os.path.join(site_dir, f"{today}.html")
    with open(day_path, "w", encoding="utf-8") as f:
        f.write(html)

    # collect all existing run dates
    dates = []
    for fname in os.listdir(site_dir):
        if re.match(r"\d{4}-\d{2}-\d{2}\.html", fname):
            dates.append(fname.replace(".html", ""))

    # write index
    index_html = render_index(dates)
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    return day_path


# ── Main ─────────────────────────────────────────────────

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    print("🔍 Fetching articles...")
    articles = fetch_articles(RSS_FEEDS, MAX_ARTICLES)
    print(f"   → {len(articles)} articles passed keyword filter")

    if not articles:
        print("   ⚠️  No articles matched. Try expanding FUNDING_KEYWORDS or RSS_FEEDS.")
        return

    print("🤖 Screening with Claude...")
    data = screen_and_analyse(articles, ANTHROPIC_API_KEY)

    print("💾 Saving...")
    obs_path = save_to_obsidian(data, OBSIDIAN_VAULT, OBSIDIAN_FOLDER, today)
    print(f"   → Obsidian: {obs_path}")

    site_path = save_to_site(data, SITE_OUTPUT_DIR, today)
    print(f"   → Site: {site_path}")

    companies = data.get("companies", [])
    priority = [c for c in companies if c.get("tier") == "priority"]
    print(f"\n✅ Done. {len(priority)} priority deal(s) today.")
    for c in priority:
        print(f"   ★ {c['name']} ({c.get('category')}, {c.get('stage')}) — score {c.get('net_score')}")


if __name__ == "__main__":
    main()
