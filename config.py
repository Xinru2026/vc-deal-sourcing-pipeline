from pathlib import Path
import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

DB_PATH = Path(os.environ.get("DEAL_DB_PATH", "data/deals.db"))
SITE_OUTPUT_DIR = Path(os.environ.get("SITE_OUTPUT_DIR", "docs"))

OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")
OBSIDIAN_FOLDER = os.environ.get("OBSIDIAN_FOLDER", "PXN Deal Sourcing Results")

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
    "investors", "capital", "round",
]

MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "40"))
