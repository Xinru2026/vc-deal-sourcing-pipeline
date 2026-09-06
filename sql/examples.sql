-- 1) How many companies were found in each category?
SELECT category, COUNT(*) AS company_count
FROM companies
GROUP BY category
ORDER BY company_count DESC;

-- 2) Which priority companies were found most recently?
SELECT r.run_id, c.name, c.category, c.stage, c.net_score
FROM companies c
JOIN runs r ON c.run_id = r.run_id
WHERE c.tier = 'priority'
ORDER BY r.run_id DESC, c.net_score DESC;

-- 3) Which companies hit at least three positive signals?
SELECT c.name, COUNT(*) AS positive_signals
FROM companies c
JOIN signals s ON c.company_id = s.company_id
WHERE s.is_hit = 1 AND s.is_positive = 1
GROUP BY c.company_id, c.name
HAVING COUNT(*) >= 3
ORDER BY positive_signals DESC;

-- 4) Which signals appear most often?
SELECT signal_name, COUNT(*) AS times_hit
FROM signals
WHERE is_hit = 1
GROUP BY signal_name
ORDER BY times_hit DESC;

-- 5) How efficient was each pipeline run?
SELECT run_id, articles_ingested, companies_scored, noise_filtered_pct,
       priority_deals, llm_calls
FROM runs
WHERE status = 'completed'
ORDER BY run_id DESC;
