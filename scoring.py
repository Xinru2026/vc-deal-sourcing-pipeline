POSITIVE_SIGNALS = (
    "regulatory_driver",
    "structural_demand",
    "process_embedding",
    "data_flywheel",
    "vertical_specificity",
    "named_customers",
    "strategic_investor",
    "geography_fit",
)

NEGATIVE_SIGNALS = (
    "vague_target",
    "undifferentiated",
)

ALL_SIGNALS = POSITIVE_SIGNALS + NEGATIVE_SIGNALS


def score_company(company):
    """Apply deterministic business rules after LLM extraction."""
    hit_names = {
        signal.get("name")
        for signal in company.get("signals_hit", [])
        if signal.get("name") in ALL_SIGNALS
    }

    positive_score = sum(name in hit_names for name in POSITIVE_SIGNALS)
    negative_score = sum(name in hit_names for name in NEGATIVE_SIGNALS)
    net_score = positive_score - negative_score

    stage = company.get("stage", "")
    if stage == "Series B":
        tier = "series_b"
    elif net_score >= 3:
        tier = "priority"
    elif net_score >= 1:
        tier = "watch"
    else:
        tier = "pending"

    company["positive_score"] = positive_score
    company["negative_score"] = negative_score
    company["net_score"] = net_score
    company["tier"] = tier
    company["signals_missing"] = [
        name for name in ALL_SIGNALS if name not in hit_names
    ]
    return company


def apply_scoring(data):
    companies = [score_company(company) for company in data.get("companies", [])]
    tier_rank = {"priority": 0, "watch": 1, "series_b": 2, "pending": 3}
    companies.sort(
        key=lambda c: (tier_rank.get(c.get("tier"), 99), -c.get("net_score", 0))
    )
    data["companies"] = companies
    return data
