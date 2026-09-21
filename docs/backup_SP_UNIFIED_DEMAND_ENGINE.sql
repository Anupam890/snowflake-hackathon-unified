CREATE OR REPLACE PROCEDURE "SP_UNIFIED_DEMAND_ENGINE"("P_QUESTION" VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS '
DECLARE
    v_intent_json VARIANT;
    v_intent VARCHAR;
    v_horizon_months INT DEFAULT 3;
    v_policy_type VARCHAR DEFAULT NULL;
    v_avg_premium FLOAT DEFAULT NULL;
    v_plan_tier VARCHAR DEFAULT NULL;
    v_state VARCHAR DEFAULT NULL;
    v_premium_change_pct FLOAT DEFAULT NULL;
    v_max_date TIMESTAMP_NTZ;
    v_last_avg_premium FLOAT;
    v_result VARCHAR DEFAULT '''';
    v_ai_response VARCHAR DEFAULT '''';
    v_elasticity_weight FLOAT DEFAULT 0.15;
    v_policies_affected INT;
    v_current_avg_premium FLOAT;
    v_projected_avg_premium FLOAT;
    v_current_total_revenue FLOAT;
    v_projected_total_revenue FLOAT;
    v_revenue_delta FLOAT;
    v_revenue_delta_pct FLOAT;
    v_current_avg_churn FLOAT;
    v_projected_avg_churn FLOAT;
    v_churn_delta FLOAT;
    v_estimated_policies_lost INT;
    v_net_revenue_impact FLOAT;
    v_change_multiplier FLOAT;
    v_baseline_new_3m INT DEFAULT 0;
    v_projected_new_3m INT DEFAULT 0;
    v_demand_delta INT DEFAULT 0;
    v_demand_revenue_impact FLOAT DEFAULT 0;
    v_combined_net_impact FLOAT DEFAULT 0;
    v_demand_available BOOLEAN DEFAULT FALSE;
    v_count_results INT DEFAULT 0;
    v_count_sims INT DEFAULT 0;
    v_count_trends INT DEFAULT 0;
    v_max_month VARCHAR DEFAULT '''';
BEGIN
    -- =====================================================
    -- STEP 1: CLASSIFY INTENT + EXTRACT PARAMETERS
    -- =====================================================
    SELECT PARSE_JSON(SNOWFLAKE.CORTEX.COMPLETE(
        ''llama3.1-70b'',
        ''You are a parameter extraction engine for an insurance demand forecasting system. '' ||
        ''Analyze the user question and return ONLY a valid JSON object with no extra text. '' ||
        ''Classify the intent into one of: TRAIN, FORECAST, WHATIF, SHOW_RESULTS, GENERAL. '' ||
        ''Rules: '' ||
        ''- TRAIN: user wants to retrain/rebuild/refresh the forecast model. '' ||
        ''- FORECAST: user wants to predict/forecast future demand or new policies. '' ||
        ''- WHATIF: user asks what happens if premiums change, rate simulation, pricing scenarios. '' ||
        ''- SHOW_RESULTS: user wants to see existing/current/latest forecast results or past predictions. '' ||
        ''- GENERAL: anything else about data, trends, summaries. '' ||
        ''Return JSON: '' ||
        ''{''''intent'''': one of TRAIN/FORECAST/WHATIF/SHOW_RESULTS/GENERAL, '' ||
        ''''''horizon_months'''': number 1-12 (default 3), '' ||
        ''''''policy_type'''': one of ''''Auto''''/''''Health''''/''''Home''''/''''Life'''' or null, '' ||
        ''''''avg_premium'''': number or null, '' ||
        ''''''plan_tier'''': one of ''''Bronze''''/''''Silver''''/''''Gold''''/''''Platinum'''' or null, '' ||
        ''''''state'''': two-letter US state or null, '' ||
        ''''''premium_change_pct'''': number or null}. '' ||
        ''User question: '' || :P_QUESTION
    )) INTO :v_intent_json;

    v_intent := COALESCE(:v_intent_json:intent::VARCHAR, ''GENERAL'');
    v_horizon_months := COALESCE(:v_intent_json:horizon_months::INT, 3);
    v_policy_type := :v_intent_json:policy_type::VARCHAR;
    v_avg_premium := :v_intent_json:avg_premium::FLOAT;
    v_plan_tier := :v_intent_json:plan_tier::VARCHAR;
    v_state := :v_intent_json:state::VARCHAR;
    v_premium_change_pct := :v_intent_json:premium_change_pct::FLOAT;

    -- =====================================================
    -- INTENT: TRAIN
    -- =====================================================
    IF (:v_intent = ''TRAIN'') THEN
        CREATE OR REPLACE SNOWFLAKE.ML.FORECAST UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_MODEL(
            INPUT_DATA          => TABLE(UNIFIEDAI_DB.ANALYTICS.V_DEMAND_FORECAST_TRAINING),
            SERIES_COLNAME      => ''POLICY_TYPE'',
            TIMESTAMP_COLNAME   => ''MONTH_YEAR'',
            TARGET_COLNAME      => ''NEW_POLICIES'',
            CONFIG_OBJECT       => {''ON_ERROR'': ''SKIP''}
        );
        v_result := ''MODEL TRAINING COMPLETE. Model: DEMAND_FORECAST_MODEL. Trained on V_DEMAND_FORECAST_TRAINING. Series: Auto, Health, Home, Life. Target: NEW_POLICIES. Exogenous: AVG_PREMIUM. Timestamp: '' || CURRENT_TIMESTAMP()::VARCHAR;

    -- =====================================================
    -- INTENT: FORECAST
    -- =====================================================
    ELSEIF (:v_intent = ''FORECAST'') THEN
        SELECT MAX(MONTH_YEAR) INTO :v_max_date
        FROM UNIFIEDAI_DB.ANALYTICS.V_DEMAND_FORECAST_TRAINING;

        CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FF AS
        SELECT
            t.POLICY_TYPE,
            DATEADD(''MONTH'', seq.N, :v_max_date)::TIMESTAMP_NTZ AS MONTH_YEAR,
            COALESCE(
                CASE WHEN :v_policy_type IS NULL OR t.POLICY_TYPE = :v_policy_type
                     THEN :v_avg_premium ELSE NULL END,
                t.LAST_AVG_PREMIUM
            ) AS AVG_PREMIUM
        FROM (
            SELECT POLICY_TYPE, AVG_PREMIUM AS LAST_AVG_PREMIUM
            FROM UNIFIEDAI_DB.ANALYTICS.V_DEMAND_FORECAST_TRAINING
            QUALIFY ROW_NUMBER() OVER (PARTITION BY POLICY_TYPE ORDER BY MONTH_YEAR DESC) = 1
        ) t
        CROSS JOIN (
            SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) AS N
            FROM TABLE(GENERATOR(ROWCOUNT => 12))
        ) seq
        WHERE seq.N <= :v_horizon_months;

        CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FC AS
        SELECT * FROM TABLE(UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_MODEL!FORECAST(
            INPUT_DATA        => TABLE(UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FF),
            SERIES_COLNAME    => ''POLICY_TYPE'',
            TIMESTAMP_COLNAME => ''MONTH_YEAR''
        ));

        INSERT INTO UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_RESULTS
            (POLICY_TYPE, FORECAST_MONTH, FORECAST_NEW_POLICIES, LOWER_BOUND, UPPER_BOUND, ASSUMED_AVG_PREMIUM, FORECAST_USER, FORECAST_RUN_TIMESTAMP)
        SELECT
            f.SERIES::VARCHAR, f.TS,
            GREATEST(ROUND(f.FORECAST, 0), 0),
            GREATEST(ROUND(f.LOWER_BOUND, 0), 0),
            GREATEST(ROUND(f.UPPER_BOUND, 0), 0),
            ff.AVG_PREMIUM, CURRENT_USER(), CURRENT_TIMESTAMP()
        FROM UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FC f
        JOIN UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FF ff
            ON f.SERIES::VARCHAR = ff.POLICY_TYPE AND f.TS = ff.MONTH_YEAR;

        SELECT
            ''DEMAND FORECAST ('' || :v_horizon_months::VARCHAR || ''-Month Projection): '' ||
            LISTAGG(
                f.SERIES::VARCHAR || '' | '' || TO_CHAR(f.TS, ''YYYY-MM'') || '' | Forecast: '' ||
                GREATEST(ROUND(f.FORECAST, 0), 0)::VARCHAR || '' new policies (range: '' ||
                GREATEST(ROUND(f.LOWER_BOUND, 0), 0)::VARCHAR || ''-'' ||
                GREATEST(ROUND(f.UPPER_BOUND, 0), 0)::VARCHAR || '') Premium: $'' ||
                ROUND(ff.AVG_PREMIUM, 2)::VARCHAR,
                '' || ''
            ) WITHIN GROUP (ORDER BY f.SERIES, f.TS)
        INTO :v_result
        FROM UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FC f
        JOIN UNIFIEDAI_DB.ANALYTICS._TMP_UNI_FF ff
            ON f.SERIES::VARCHAR = ff.POLICY_TYPE AND f.TS = ff.MONTH_YEAR;

    -- =====================================================
    -- INTENT: WHATIF
    -- =====================================================
    ELSEIF (:v_intent = ''WHATIF'') THEN
        v_plan_tier := COALESCE(:v_plan_tier, ''Gold'');
        v_state := COALESCE(:v_state, ''TX'');
        v_premium_change_pct := COALESCE(:v_premium_change_pct, 5);
        v_policy_type := COALESCE(:v_policy_type, ''Health'');

        BEGIN
            SELECT WEIGHT INTO :v_elasticity_weight FROM UNIFIEDAI_DB.RISK.RISK_FACTORS WHERE FACTOR_NAME = ''Price Sensitivity Index'' LIMIT 1;
        EXCEPTION WHEN OTHER THEN v_elasticity_weight := 0.15;
        END;

        v_change_multiplier := 1 + (:v_premium_change_pct / 100);

        SELECT COUNT(*), AVG(FINAL_PREMIUM), SUM(FINAL_PREMIUM), AVG(COALESCE(CHURN_PROBABILITY, 0.1))
        INTO :v_policies_affected, :v_current_avg_premium, :v_current_total_revenue, :v_current_avg_churn
        FROM UNIFIEDAI_DB.RISK.V_RISK_CHURN
        WHERE POLICY_TYPE = :v_policy_type AND PLAN_TIER = :v_plan_tier AND STATE = :v_state
          AND POLICY_STATUS = ''Active'' AND FINAL_PREMIUM IS NOT NULL;

        IF (:v_policies_affected = 0) THEN
            v_result := ''No active policies found for '' || :v_plan_tier || '' '' || :v_policy_type || '' in '' || :v_state || ''. Try different parameters.'';
        ELSE
            v_projected_avg_premium := :v_current_avg_premium * :v_change_multiplier;
            v_churn_delta := :v_elasticity_weight * (:v_premium_change_pct / 100) * CASE WHEN :v_premium_change_pct > 0 THEN 1.5 ELSE 0.8 END;
            v_projected_avg_churn := LEAST(GREATEST(:v_current_avg_churn + :v_churn_delta, 0.01), 0.95);
            v_estimated_policies_lost := GREATEST(ROUND(:v_policies_affected * ABS(:v_churn_delta), 0), 0);
            v_projected_total_revenue := (:v_policies_affected - :v_estimated_policies_lost) * :v_projected_avg_premium;
            v_revenue_delta := :v_projected_total_revenue - :v_current_total_revenue;
            v_revenue_delta_pct := DIV0NULL(:v_revenue_delta, :v_current_total_revenue) * 100;
            v_net_revenue_impact := :v_revenue_delta;

            BEGIN
                SELECT MAX(MONTH_YEAR) INTO :v_max_date FROM UNIFIEDAI_DB.ANALYTICS.V_DEMAND_FORECAST_TRAINING WHERE POLICY_TYPE = :v_policy_type;
                SELECT AVG_PREMIUM INTO :v_last_avg_premium FROM UNIFIEDAI_DB.ANALYTICS.V_DEMAND_FORECAST_TRAINING
                WHERE POLICY_TYPE = :v_policy_type QUALIFY ROW_NUMBER() OVER (ORDER BY MONTH_YEAR DESC) = 1;

                CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_WI_BASE AS
                SELECT :v_policy_type AS POLICY_TYPE, DATEADD(''MONTH'', seq.N, :v_max_date)::TIMESTAMP_NTZ AS MONTH_YEAR, :v_last_avg_premium AS AVG_PREMIUM
                FROM (SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) AS N FROM TABLE(GENERATOR(ROWCOUNT => 3))) seq;

                CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_WI_ADJ AS
                SELECT :v_policy_type AS POLICY_TYPE, DATEADD(''MONTH'', seq.N, :v_max_date)::TIMESTAMP_NTZ AS MONTH_YEAR, ROUND(:v_last_avg_premium * :v_change_multiplier, 2) AS AVG_PREMIUM
                FROM (SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) AS N FROM TABLE(GENERATOR(ROWCOUNT => 3))) seq;

                CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_FC_BASE AS
                SELECT * FROM TABLE(UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_MODEL!FORECAST(
                    INPUT_DATA => TABLE(UNIFIEDAI_DB.ANALYTICS._TMP_WI_BASE), SERIES_COLNAME => ''POLICY_TYPE'', TIMESTAMP_COLNAME => ''MONTH_YEAR''));

                CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_FC_ADJ AS
                SELECT * FROM TABLE(UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_MODEL!FORECAST(
                    INPUT_DATA => TABLE(UNIFIEDAI_DB.ANALYTICS._TMP_WI_ADJ), SERIES_COLNAME => ''POLICY_TYPE'', TIMESTAMP_COLNAME => ''MONTH_YEAR''));

                SELECT GREATEST(ROUND(SUM(FORECAST), 0), 0) INTO :v_baseline_new_3m FROM UNIFIEDAI_DB.ANALYTICS._TMP_FC_BASE;
                SELECT GREATEST(ROUND(SUM(FORECAST), 0), 0) INTO :v_projected_new_3m FROM UNIFIEDAI_DB.ANALYTICS._TMP_FC_ADJ;
                v_demand_delta := :v_projected_new_3m - :v_baseline_new_3m;
                v_demand_revenue_impact := :v_demand_delta * :v_projected_avg_premium;
                v_demand_available := TRUE;
            EXCEPTION WHEN OTHER THEN v_demand_available := FALSE;
            END;

            v_combined_net_impact := :v_net_revenue_impact + :v_demand_revenue_impact;

            INSERT INTO UNIFIEDAI_DB.ANALYTICS.WHATIF_SIMULATION_LOG (
                SIMULATION_ID, SIMULATION_TIMESTAMP, INPUT_POLICY_TYPE, INPUT_PLAN_TIER, INPUT_STATE, INPUT_PREMIUM_CHANGE_PCT,
                POLICIES_AFFECTED, CURRENT_AVG_PREMIUM, PROJECTED_AVG_PREMIUM,
                CURRENT_TOTAL_REVENUE, PROJECTED_TOTAL_REVENUE, REVENUE_DELTA, REVENUE_DELTA_PCT,
                CURRENT_AVG_CHURN_PROB, PROJECTED_AVG_CHURN_PROB, CHURN_DELTA,
                ESTIMATED_POLICIES_LOST, NET_REVENUE_IMPACT,
                BASELINE_NEW_POLICIES_3M, PROJECTED_NEW_POLICIES_3M, DEMAND_DELTA,
                DEMAND_REVENUE_IMPACT, COMBINED_NET_IMPACT, SIMULATION_USER, CREATED_AT
            )
            SELECT
                ''SIM-'' || LPAD((COALESCE(MAX(TRY_CAST(REPLACE(SIMULATION_ID, ''SIM-'', '''') AS INT)), 0) + 1)::VARCHAR, 5, ''0''),
                CURRENT_TIMESTAMP(), :v_policy_type, :v_plan_tier, :v_state, :v_premium_change_pct,
                :v_policies_affected, :v_current_avg_premium, :v_projected_avg_premium,
                :v_current_total_revenue, :v_projected_total_revenue, :v_revenue_delta, :v_revenue_delta_pct,
                :v_current_avg_churn, :v_projected_avg_churn, :v_churn_delta,
                :v_estimated_policies_lost, :v_net_revenue_impact,
                :v_baseline_new_3m, :v_projected_new_3m, :v_demand_delta,
                :v_demand_revenue_impact, :v_combined_net_impact, CURRENT_USER(), CURRENT_TIMESTAMP()
            FROM UNIFIEDAI_DB.ANALYTICS.WHATIF_SIMULATION_LOG;

            v_result := ''WHAT-IF SIMULATION: '' || CASE WHEN :v_premium_change_pct >= 0 THEN ''Increase'' ELSE ''Decrease'' END ||
                '' '' || :v_plan_tier || '' '' || :v_policy_type || '' premiums by '' || ABS(:v_premium_change_pct)::VARCHAR || ''% in '' || :v_state ||
                ''. Policies Affected: '' || :v_policies_affected::VARCHAR ||
                ''. Current Avg Premium: $'' || ROUND(:v_current_avg_premium, 2)::VARCHAR ||
                ''. Projected Avg Premium: $'' || ROUND(:v_projected_avg_premium, 2)::VARCHAR ||
                ''. Revenue Delta: '' || CASE WHEN :v_revenue_delta >= 0 THEN ''+$'' ELSE ''-$'' END || ROUND(ABS(:v_revenue_delta), 2)::VARCHAR ||
                '' ('' || ROUND(:v_revenue_delta_pct, 2)::VARCHAR || ''%)'' ||
                ''. Current Churn: '' || ROUND(:v_current_avg_churn * 100, 2)::VARCHAR || ''%'' ||
                ''. Projected Churn: '' || ROUND(:v_projected_avg_churn * 100, 2)::VARCHAR || ''%'' ||
                ''. Policies Lost: '' || :v_estimated_policies_lost::VARCHAR;

            IF (:v_demand_available) THEN
                v_result := :v_result ||
                    ''. DEMAND FORECAST 3M: Baseline='' || :v_baseline_new_3m::VARCHAR ||
                    '' Projected='' || :v_projected_new_3m::VARCHAR ||
                    '' Delta='' || :v_demand_delta::VARCHAR ||
                    '' Revenue Impact='' || CASE WHEN :v_demand_revenue_impact >= 0 THEN ''+$'' ELSE ''-$'' END || ROUND(ABS(:v_demand_revenue_impact), 2)::VARCHAR;
            END IF;

            v_result := :v_result ||
                ''. COMBINED NET IMPACT: '' || CASE WHEN :v_combined_net_impact >= 0 THEN ''+$'' ELSE ''-$'' END || ROUND(ABS(:v_combined_net_impact), 2)::VARCHAR ||
                ''. RECOMMENDATION: '' ||
                CASE
                    WHEN :v_combined_net_impact > 0 AND :v_churn_delta < 0.05 AND :v_demand_delta >= 0 THEN ''STRONGLY FAVORABLE''
                    WHEN :v_combined_net_impact > 0 AND :v_churn_delta < 0.05 THEN ''FAVORABLE''
                    WHEN :v_combined_net_impact > 0 AND :v_churn_delta >= 0.05 THEN ''CAUTION - High churn risk''
                    WHEN :v_combined_net_impact <= 0 AND :v_demand_delta < 0 THEN ''UNFAVORABLE - Losses exceed gains''
                    WHEN :v_combined_net_impact <= 0 THEN ''UNFAVORABLE - Churn losses exceed premium gains''
                    ELSE ''NEUTRAL''
                END;
        END IF;

    -- =====================================================
    -- INTENT: SHOW_RESULTS
    -- =====================================================
    ELSEIF (:v_intent = ''SHOW_RESULTS'') THEN
        CREATE OR REPLACE TEMPORARY TABLE UNIFIEDAI_DB.ANALYTICS._TMP_LATEST_FC AS
        SELECT * FROM UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_RESULTS
        WHERE FORECAST_RUN_TIMESTAMP = (SELECT MAX(FORECAST_RUN_TIMESTAMP) FROM UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_RESULTS);

        SELECT COUNT(*) INTO :v_count_results FROM UNIFIEDAI_DB.ANALYTICS._TMP_LATEST_FC;

        IF (:v_count_results = 0) THEN
            v_result := ''No forecast results found. Ask me to run a forecast first.'';
        ELSE
            SELECT
                ''LATEST FORECAST RESULTS: '' ||
                LISTAGG(
                    POLICY_TYPE || '' | '' || TO_CHAR(FORECAST_MONTH, ''YYYY-MM'') || '' | '' ||
                    FORECAST_NEW_POLICIES::VARCHAR || '' policies ('' || LOWER_BOUND::VARCHAR || ''-'' || UPPER_BOUND::VARCHAR ||
                    '') Premium: $'' || ROUND(ASSUMED_AVG_PREMIUM, 2)::VARCHAR,
                    '' || ''
                ) WITHIN GROUP (ORDER BY POLICY_TYPE, FORECAST_MONTH)
            INTO :v_result
            FROM UNIFIEDAI_DB.ANALYTICS._TMP_LATEST_FC;
        END IF;

    -- =====================================================
    -- INTENT: GENERAL
    -- =====================================================
    ELSE
        SELECT COUNT(*) INTO :v_count_trends FROM UNIFIEDAI_DB.ANALYTICS.POLICY_TRENDS;
        SELECT MAX(MONTH_YEAR)::VARCHAR INTO :v_max_month FROM UNIFIEDAI_DB.ANALYTICS.POLICY_TRENDS;
        SELECT COUNT(*) INTO :v_count_results FROM UNIFIEDAI_DB.ANALYTICS.DEMAND_FORECAST_RESULTS;
        SELECT COUNT(*) INTO :v_count_sims FROM UNIFIEDAI_DB.ANALYTICS.WHATIF_SIMULATION_LOG;

        v_result := ''Available Data: Policy Types=Auto,Health,Home,Life. Plan Tiers=Bronze,Silver,Gold,Platinum. States=AZ,CA,GA,IL,NY,PA,TX. '' ||
            ''Training rows='' || :v_count_trends::VARCHAR || ''. Latest month='' || :v_max_month ||
            ''. Forecast results='' || :v_count_results::VARCHAR || ''. Simulations run='' || :v_count_sims::VARCHAR ||
            ''. Capabilities: I can train the ML model, forecast demand, simulate what-if premium changes, or show past results.'';
    END IF;

    -- =====================================================
    -- STEP 2: CONVERSATIONAL AI RESPONSE
    -- =====================================================
    SELECT SNOWFLAKE.CORTEX.COMPLETE(
        ''llama3.1-70b'',
        ''You are an insurance analytics advisor. A user asked: "'' || :P_QUESTION || ''". '' ||
        ''Here are the results: '' || :v_result ||
        '' Provide a clear, professional, conversational summary with specific numbers. '' ||
        ''Use bullet points for clarity. Keep it professional but accessible. '' ||
        ''Always include the actual numbers from the results.''
    ) INTO :v_ai_response;

    RETURN ''--- INTENT: '' || :v_intent || '' ---'' ||
           CASE WHEN :v_intent = ''WHATIF'' THEN CHR(10) || ''Parameters: '' || COALESCE(:v_policy_type, ''N/A'') || ''/'' || COALESCE(:v_plan_tier, ''N/A'') || ''/'' || COALESCE(:v_state, ''N/A'') || ''/'' || COALESCE(:v_premium_change_pct::VARCHAR, ''N/A'') || ''%''
                WHEN :v_intent = ''FORECAST'' THEN CHR(10) || ''Parameters: Horizon='' || :v_horizon_months::VARCHAR || ''mo, Policy='' || COALESCE(:v_policy_type, ''All'')
                ELSE '''' END ||
           CHR(10) || CHR(10) || :v_result ||
           CHR(10) || CHR(10) || ''--- AI ANALYSIS ---'' || CHR(10) || :v_ai_response;
END;
';