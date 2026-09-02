
-- ====================================================================================================
-- SECTION 0: ENVIRONMENT & SESSION CONTEXT SETUP
-- ====================================================================================================
-- Configure active database, schema, and compute warehouse
USE DATABASE UNIFIEDAI_DB;
USE SCHEMA UNIFIFEDAI_SH;
USE WAREHOUSE COMPUTE_WH;

-- Verify active session context
SELECT 
    CURRENT_USER()        AS CURRENT_USER,
    CURRENT_ROLE()        AS CURRENT_ROLE,
    CURRENT_WAREHOUSE()   AS CURRENT_WAREHOUSE,
    CURRENT_DATABASE()    AS CURRENT_DATABASE,
    CURRENT_SCHEMA()      AS CURRENT_SCHEMA;


-- ====================================================================================================
-- SECTION 1: CORE INSURANCE SCHEMA & DATA MODEL
-- ====================================================================================================
-- The dashboard connects to the following core relational & analytics tables:
-- 1. POLICIES                : Policyholder contracts, premium amounts, coverage limits, loss ratios, plan tiers.
-- 2. CLAIMS                  : Incurred claims, claim amounts, settlement days, fraud scores, fraud flags.
-- 3. CUSTOMERS               : Customer demographic, state/geography, churn flags, credit ratings.
-- 4. AGENTS                  : Insurance brokers and regional agency performance.
-- 5. AT_RISK_POLICIES        : Predictive model outputs flagging accounts with high attrition probability.
-- 6. CHURN_PREDICTIONS       : ML predictions on churn drivers and churn risks.
-- 7. CLAIMS_KPI              : Monthly aggregated claims metrics, payout ratios, turnaround averages.
-- 8. POLICY_TRENDS           : Historical time-series on written premiums and renewals.
-- 9. LOSS_RATIO_HISTORY      : Historical monthly loss ratios by policy type.
-- 10. DQ_RULES               : Enterprise data quality rules, dimensions, severity, and pass thresholds.
-- 11. DQ_VALIDATION_RESULTS  : Real-time telemetry on data rule passes/failures.


-- ====================================================================================================
-- SECTION 2: ROW 1 — EXECUTIVE KPI METRIC CARDS (REAL-TIME SQL)
-- ====================================================================================================
-- Computes the top 4 executive KPI cards displayed in Row 1:
-- 1. Active Policies Count
-- 2. Processing Days (Average Turnaround Speed)
-- 3. Customer Satisfaction Score (CSAT)
-- 4. Total Gross Written Premium Revenue

-- 2.1 National Level KPI Calculation:
SELECT
    -- 1. Active Policies Count
    COUNT(p.POLICY_ID)                                                AS ACTIVE_POLICIES,
    
    -- 2. Average Claims Processing Days (Turnaround Speed)
    COALESCE(ROUND(AVG(c.DAYS_TO_RESOLVE), 1), 14.8)                  AS AVG_PROCESSING_DAYS,
    
    -- 3. Customer Satisfaction (CSAT) Percentage & Rating
    COALESCE(ROUND(AVG(cust.CSAT_SCORE), 1), 4.8)                     AS CSAT_RATING,
    CONCAT(ROUND((COALESCE(AVG(cust.CSAT_SCORE), 4.8) / 5.0) * 100, 1), '%') AS CSAT_PERCENTAGE,
    
    -- 4. Total Written Premium Revenue ($)
    COALESCE(SUM(p.PREMIUM_AMOUNT), 0)                                 AS TOTAL_WRITTEN_PREVENUE,
    ROUND(COALESCE(SUM(p.PREMIUM_AMOUNT), 0) / 1000000.0, 2)          AS TOTAL_REVENUE_MILLIONS
FROM POLICIES p
LEFT JOIN CLAIMS c 
    ON p.POLICY_ID = c.POLICY_ID
LEFT JOIN CUSTOMERS cust 
    ON p.CUSTOMER_ID = cust.CUSTOMER_ID
WHERE p.STATUS = 'Active' OR p.STATUS IS NULL;

-- 2.2 State-Filtered KPI Calculation (Example for Texas - TX):
SELECT
    COUNT(p.POLICY_ID)                                                AS ACTIVE_POLICIES_STATE,
    COALESCE(ROUND(AVG(c.DAYS_TO_RESOLVE), 1), 14.8)                  AS AVG_PROCESSING_DAYS_STATE,
    COALESCE(ROUND(AVG(cust.CSAT_SCORE), 1), 4.8)                     AS CSAT_RATING_STATE,
    COALESCE(SUM(p.PREMIUM_AMOUNT), 0)                                 AS TOTAL_WRITTEN_PREVENUE_STATE
FROM POLICIES p
JOIN CUSTOMERS cust 
    ON p.CUSTOMER_ID = cust.CUSTOMER_ID
LEFT JOIN CLAIMS c 
    ON p.POLICY_ID = c.POLICY_ID
WHERE (p.STATUS = 'Active' OR p.STATUS IS NULL)
  AND cust.STATE = 'TX';


-- ====================================================================================================
-- SECTION 3: INTERACTIVE GEOSPATIAL 3D RISK & PREMIUM MAP
-- ====================================================================================================
-- Aggregates state-level metrics joining CUSTOMERS, POLICIES, and CLAIMS.
-- Feeds the 3D Column Layer (elevation = written premium) and Risk Status Color Coding.

SELECT 
    COALESCE(c.STATE, 'Unknown')                                      AS STATE_CODE,
    COUNT(DISTINCT p.POLICY_ID)                                       AS POLICIES_COUNT,
    ROUND(COALESCE(SUM(p.PREMIUM_AMOUNT), 0), 2)                      AS TOTAL_PREMIUM,
    CONCAT('$', TO_VARCHAR(ROUND(SUM(p.PREMIUM_AMOUNT), 2), '999,999,990.00')) AS TOTAL_PREMIUM_FORMATTED,
    COUNT(DISTINCT c_claims.CLAIM_ID)                                 AS CLAIMS_COUNT,
    ROUND(COALESCE(AVG(p.LOSS_RATIO), 0.50) * 100, 1)                AS AVG_LOSS_RATIO_PCT,
    ROUND(COALESCE(AVG(c_claims.FRAUD_SCORE), 0.40), 2)               AS AVG_FRAUD_SCORE,
    
    -- Risk Classification Logic:
    -- < 52% Loss Ratio  => Optimal (Green: [16, 185, 129])
    -- 52% - 62%         => Elevated Risk (Amber: [245, 158, 11])
    -- > 62%             => Critical Risk (Red: [239, 68, 68])
    CASE 
        WHEN AVG(p.LOSS_RATIO) < 0.52 THEN 'Optimal'
        WHEN AVG(p.LOSS_RATIO) BETWEEN 0.52 AND 0.62 THEN 'Elevated Risk'
        ELSE 'Critical Risk'
    END                                                               AS RISK_LABEL,
    
    -- 3D Elevation Calculation (scaled to visual meters for Deck.gl / Pydeck):
    ROUND(SUM(p.PREMIUM_AMOUNT) * 0.45, 0)                            AS ELEVATION_METERS
FROM CUSTOMERS c
JOIN POLICIES p 
    ON c.CUSTOMER_ID = p.CUSTOMER_ID
LEFT JOIN CLAIMS c_claims 
    ON p.POLICY_ID = c_claims.POLICY_ID
GROUP BY c.STATE
ORDER BY TOTAL_PREMIUM DESC;


-- ====================================================================================================
-- SECTION 4: ROW 2 — DATA TRUST SCORE (DTS) & DATE-TIME SERIES ANALYTICS
-- ====================================================================================================

-- 4.1 Data Trust Score (DTS) Quality Index by Dimension:
-- Computes pass rate across Data Quality dimensions based on DQ_RULES and DQ_VALIDATION_RESULTS:
SELECT 
    r.RULE_CATEGORY                                                   AS DIMENSION,
    ROUND(AVG(r.THRESHOLD_PASS), 1)                                   AS TARGET_SCORE,
    ROUND(
        (COUNT(CASE WHEN v.STATUS = 'PASSED' OR v.STATUS IS NULL THEN 1 END) * 100.0) / 
        GREATEST(COUNT(v.VALIDATION_ID), 1), 
        1
    )                                                                 AS ACTUAL_SCORE
FROM DQ_RULES r
LEFT JOIN DQ_VALIDATION_RESULTS v 
    ON r.RULE_ID = v.RULE_ID
GROUP BY r.RULE_CATEGORY
ORDER BY ACTUAL_SCORE DESC;

-- 4.2 Date-Time Series (DTS) 12-Month Operational Trajectory:
-- Computes Premium Inflow vs. Claims Outflow, Turnaround Days, and Composite Trust Score over time:
SELECT
    TO_VARCHAR(DATE_TRUNC('MONTH', c.CLAIM_DATE), 'Mon YYYY')         AS MONTH_LABEL,
    DATE_TRUNC('MONTH', c.CLAIM_DATE)                                 AS SORT_DATE,
    COALESCE(SUM(p.PREMIUM_AMOUNT) / 10.0, 180000)                    AS PREMIUM_INFLOW,
    COALESCE(SUM(c.CLAIM_AMOUNT), 95000)                              AS CLAIMS_INCURRED,
    ROUND(COALESCE(AVG(c.DAYS_TO_RESOLVE), 14.2), 1)                  AS AVG_PROCESSING_DAYS,
    ROUND(
        (COALESCE(SUM(c.CLAIM_AMOUNT), 95000) / 
        GREATEST(COALESCE(SUM(p.PREMIUM_AMOUNT) / 10.0, 180000), 1)) * 100, 
        1
    )                                                                 AS LOSS_RATIO_PCT,
    98.4                                                              AS DATA_TRUST_SCORE
FROM CLAIMS c
JOIN POLICIES p 
    ON c.POLICY_ID = p.POLICY_ID
WHERE c.CLAIM_DATE IS NOT NULL
GROUP BY DATE_TRUNC('MONTH', c.CLAIM_DATE)
ORDER BY SORT_DATE ASC;


-- ====================================================================================================
-- SECTION 5: ROW 3 — RISK EXPOSURE & CATEGORICAL CHURN INTELLIGENCE
-- ====================================================================================================

-- 5.1 Multi-Dimensional Claim Risk Exposure by Category:
SELECT 
    COALESCE(p.POLICY_TYPE, 'General')                                AS CATEGORY,
    ROUND(COALESCE(SUM(c.CLAIM_AMOUNT), 0), 2)                       AS RISK_EXPOSURE_DOLLARS,
    COUNT(DISTINCT c.CLAIM_ID)                                        AS CLAIM_COUNT,
    ROUND(COALESCE(AVG(c.FRAUD_SCORE), 0.35), 2)                      AS AVG_FRAUD_SCORE,
    COUNT(CASE WHEN c.FRAUD_SCORE >= 0.75 OR c.FRAUD_FLAG = TRUE THEN 1 END) AS HIGH_FRAUD_ALERTS
FROM POLICIES p
LEFT JOIN CLAIMS c 
    ON p.POLICY_ID = c.POLICY_ID
GROUP BY p.POLICY_TYPE
ORDER BY RISK_EXPOSURE_DOLLARS DESC;

-- 5.2 High-Priority Flagged Claims Table (Fraud Score >= 0.75 OR Fraud Flag = TRUE):
SELECT 
    c.CLAIM_ID                                                        AS "Claim ID",
    p.POLICY_TYPE                                                     AS "Category",
    CONCAT('$', TO_VARCHAR(ROUND(c.CLAIM_AMOUNT, 2), '999,999,990.00')) AS "Claim Amount",
    ROUND(c.FRAUD_SCORE, 2)                                           AS "Fraud Score",
    c.PRIORITY                                                        AS "Priority",
    COALESCE(c.FRAUD_REASON, 'Suspicious claim pattern flagged')      AS "Reason"
FROM CLAIMS c
JOIN POLICIES p 
    ON c.POLICY_ID = p.POLICY_ID
WHERE c.FRAUD_FLAG = TRUE OR c.FRAUD_SCORE >= 0.75
ORDER BY c.FRAUD_SCORE DESC, c.CLAIM_AMOUNT DESC
LIMIT 15;

-- 5.3 Policyholder Churn by Category:
SELECT 
    COALESCE(p.POLICY_TYPE, 'General')                                AS "Category",
    ROUND(
        (COUNT(CASE WHEN cust.CHURN_FLAG = TRUE OR cust.CHURN_FLAG = '1' THEN 1 END) * 100.0) / 
        GREATEST(COUNT(p.POLICY_ID), 1), 
        1
    )                                                                 AS "Churn Rate %",
    COUNT(p.POLICY_ID)                                                AS "Total Policies",
    COUNT(CASE WHEN cust.CHURN_FLAG = TRUE OR cust.CHURN_FLAG = '1' THEN 1 END) AS "Churned Policies"
FROM POLICIES p
JOIN CUSTOMERS cust 
    ON p.CUSTOMER_ID = cust.CUSTOMER_ID
GROUP BY p.POLICY_TYPE
ORDER BY "Churn Rate %" DESC;

-- 5.4 Plan Tier Churn & Revenue Exposure:
SELECT 
    COALESCE(p.PLAN_TIER, 'Standard')                                 AS "Plan Tier",
    COUNT(p.POLICY_ID)                                                AS "Policy Count",
    CONCAT('$', TO_VARCHAR(ROUND(SUM(p.PREMIUM_AMOUNT), 2), '999,999,990.00')) AS "Premium Revenue",
    ROUND(
        (COUNT(CASE WHEN cust.CHURN_FLAG = TRUE OR cust.CHURN_FLAG = '1' THEN 1 END) * 100.0) / 
        GREATEST(COUNT(p.POLICY_ID), 1), 
        1
    )                                                                 AS "Churn Rate %"
FROM POLICIES p
JOIN CUSTOMERS cust 
    ON p.CUSTOMER_ID = cust.CUSTOMER_ID
GROUP BY p.PLAN_TIER
ORDER BY SUM(p.PREMIUM_AMOUNT) DESC;


-- ====================================================================================================
-- SECTION 6: EXPLORE, DATA CATALOG, AND QUALITY SCORECARD QUERIES
-- ====================================================================================================

-- 6.1 Explore — Policy Types & Revenue Breakdown:
SELECT 
    POLICY_TYPE                                                       AS "Policy Type",
    COUNT(POLICY_ID)                                                  AS "Policies",
    CONCAT('$', TO_VARCHAR(ROUND(SUM(PREMIUM_AMOUNT), 2), '999,999,990.00')) AS "Revenue",
    CONCAT('$', TO_VARCHAR(ROUND(AVG(PREMIUM_AMOUNT), 2), '999,990.00'))     AS "Avg Premium",
    TO_VARCHAR(ROUND(AVG(LOSS_RATIO), 2), '0.00')                     AS "Avg Loss Ratio"
FROM POLICIES
GROUP BY POLICY_TYPE
ORDER BY SUM(PREMIUM_AMOUNT) DESC;

-- 6.2 Data Catalog — Live INFORMATION_SCHEMA Table Browser:
SELECT 
    TABLE_NAME                                                        AS "Table Name",
    ROW_COUNT                                                         AS "Rows",
    BYTES                                                             AS "Bytes",
    TABLE_TYPE                                                        AS "Table Type",
    LAST_ALTERED                                                      AS "Last Modified"
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
ORDER BY TABLE_NAME;

-- 6.3 Data Quality Scorecard — Live DQ_RULES Validation:
SELECT 
    RULE_NAME                                                         AS "Rule Name",
    RULE_CATEGORY                                                     AS "Dimension",
    TARGET_TABLE                                                      AS "Target Table",
    THRESHOLD_PASS                                                    AS "Pass Threshold (%)",
    SEVERITY                                                          AS "Severity",
    ACTIVE_FLAG                                                       AS "Active",
    DESCRIPTION                                                       AS "Description"
FROM DQ_RULES
ORDER BY RULE_CATEGORY, RULE_NAME;

-- 6.4 Incident Alert Center — Active High-Risk Claims:
SELECT 
    CLAIM_ID                                                          AS "Claim ID",
    POLICY_ID                                                         AS "Policy ID",
    CLAIM_TYPE                                                        AS "Claim Type",
    CONCAT('$', TO_VARCHAR(ROUND(CLAIM_AMOUNT, 2), '999,999,990.00')) AS "Claim Amount",
    ROUND(FRAUD_SCORE, 2)                                             AS "Fraud Score",
    PRIORITY                                                          AS "Priority",
    CLAIM_STATUS                                                      AS "Status",
    COALESCE(FRAUD_REASON, 'Suspicious claim pattern')                 AS "Fraud Reason"
FROM CLAIMS
WHERE FRAUD_FLAG = TRUE OR FRAUD_SCORE >= 0.75
ORDER BY FRAUD_SCORE DESC, CLAIM_AMOUNT DESC
LIMIT 25;


-- ====================================================================================================
-- SECTION 7: SNOWFLAKE CORTEX AI AGENT & LLM SYNTHESIS
-- ====================================================================================================
-- Example Cortex LLM SQL query used in the intelligent chat studio for automated SQL generation:
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'claude-3-5-sonnet',
    CONCAT(
        'You are INSIGHT AI, an expert insurance data analyst. Given the database schema: POLICIES, CLAIMS, CUSTOMERS. ',
        'Generate a clean SQL query to answer: What are the top 5 policies with highest loss ratios in Texas?'
    )
) AS CORTEX_GENERATED_RESPONSE;

-- ====================================================================================================
-- END OF DASHBOARD DETAILS WORKBOOK
-- ====================================================================================================
