import re
import unicodedata

from scoring import ALL_SIGNALS

ALLOWED_CATEGORIES = {"AI", "DeepTech", "SaaS", "HealthTech", "CleanTech", "Other"}
ALLOWED_STAGES = {"Pre-Seed", "Seed", "Series A", "Series B"}


def _norm(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", value).strip().lower()


def validate_and_normalize(data, articles):
    """Validate schema and reject signal evidence that is not grounded in source text."""
    article_map = {i + 1: article for i, article in enumerate(articles)}
    clean_companies = []
    issues = []
    evidence_rejected = 0

    for raw in data.get("companies", []):
        company = dict(raw)
        try:
            article_index = int(company.get("article_index"))
        except (TypeError, ValueError):
            issues.append({"company": company.get("name", "unknown"), "issue": "invalid_article_index"})
            continue

        article = article_map.get(article_index)
        if not article:
            issues.append({"company": company.get("name", "unknown"), "issue": "article_index_out_of_range"})
            continue

        company["article_index"] = article_index
        company["name"] = str(company.get("name") or "").strip()
        company["category"] = str(company.get("category") or "Other").strip()
        company["stage"] = str(company.get("stage") or "").strip()
        company["hq"] = str(company.get("hq") or "not mentioned").strip()
        company["description"] = str(company.get("description") or "").strip()

        if not company["name"]:
            issues.append({"article_index": article_index, "issue": "missing_company_name"})
            continue
        if company["category"] not in ALLOWED_CATEGORIES:
            issues.append({"company": company["name"], "issue": f"invalid_category:{company['category']}"})
            company["category"] = "Other"
        if company["stage"] not in ALLOWED_STAGES:
            issues.append({"company": company["name"], "issue": f"invalid_stage:{company['stage'] or 'missing'}"})
            continue

        source_text = _norm(f"{article.get('title', '')} {article.get('summary', '')}")
        clean_signals = []
        seen = set()
        for signal in company.get("signals_hit", []):
            name = str(signal.get("name") or "").strip()
            evidence = str(signal.get("evidence") or "").strip()
            if name not in ALL_SIGNALS or name in seen:
                issues.append({"company": company["name"], "issue": f"unknown_or_duplicate_signal:{name}"})
                continue
            if not evidence or _norm(evidence) not in source_text:
                evidence_rejected += 1
                issues.append({"company": company["name"], "issue": f"ungrounded_evidence:{name}"})
                continue
            seen.add(name)
            clean_signals.append({"name": name, "evidence": evidence})

        company["signals_hit"] = clean_signals
        company["source_url"] = article.get("link", "")
        company["source_name"] = article.get("source", "")
        clean_companies.append(company)

    filtered = []
    for item in data.get("filtered_out", []):
        try:
            idx = int(item.get("article_index", item.get("index")))
        except (TypeError, ValueError):
            continue
        article = article_map.get(idx, {})
        filtered.append({
            "article_index": idx,
            "title": article.get("title", item.get("title", "")),
            "reason": str(item.get("reason") or "filtered by screening rule").strip(),
        })

    data["companies"] = clean_companies
    data["filtered_out"] = filtered
    data["validation_summary"] = {
        "companies_valid": len(clean_companies),
        "evidence_rejected": evidence_rejected,
        "issues": len(issues),
    }
    data["validation_issues"] = issues
    return data
