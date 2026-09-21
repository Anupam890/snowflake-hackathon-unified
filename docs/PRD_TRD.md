# Insight AI — PRD & TRD

> **Purpose of this document.** Input material for authoring a 2-page architecture
> document. Every number, object name and file path below was verified against the
> live codebase and the Snowflake account on the date of writing. Nothing here is
> aspirational — where a capability is incomplete, it is marked as such.

**Product name:** Insight AI — Enterprise Intelligence Studio
**Use case:** AI-Powered Self-Service Analytics, Document Intelligence & Data Trust
**Industry:** Cross-industry enterprise operations (insurance reference implementation)
**Platform:** Snowflake Cortex Agents + Streamlit
**Repo:** `snowflake-hackathon-unified` (~7,100 lines application code)

---

# PART 1 — PRODUCT REQUIREMENTS (PRD)

## 1.1 Problem

Business users cannot answer their own questions about enterprise data. Three
dependencies block them:

1. **Analytics requires SQL.** A regional manager asking "why did premium fall this
   year?" files a ticket and waits days for an analyst.
2. **Documents are opaque.** Policy wordings, contracts and rate filings are PDFs.
   Their contents cannot be queried alongside the warehouse.
3. **Nobody knows whether to trust the answer.** When a number looks wrong there is
   no way to ask *why* without a data engineer tracing lineage by hand.

The consequence is that insight arrives too late to act on, and when it arrives its
reliability is unknown.

## 1.2 Product goal

One conversational surface where a non-technical user asks a question in English and
receives an answer drawn from structured warehouse data, unstructured documents, and
an explicit statement of how much the underlying data can be trusted — with no SQL,
no BI tool, and no analyst in the loop.

## 1.3 Target users

| Persona | Primary need | Entry point |
|---|---|---|
| Regional/portfolio manager | Portfolio health, territory comparison, trend explanation | Insurance Portfolio dashboard |
| Business analyst | Ad-hoc questions, drill-down, chart export | Enterprise AI chat |
| Claims / underwriting ops | Document lookup, fraud signals, high-risk claims | Enterprise AI + Incidents |
| Product / pricing manager | Competitive position, plan matching, recommendations | Explore → Strategy & Market |
| Data steward | Field completeness, rule violations, remediation | Quality + Explore |

## 1.4 Functional requirements

### FR-1 — Conversational analytics
- **FR-1.1** Natural-language questions answered over the warehouse; the agent selects
  its own tool and generates SQL. No question templates.
- **FR-1.2** Generated SQL is shown to the user, not hidden.
- **FR-1.3** Users may execute the generated SQL from the chat and see results inline.
- **FR-1.4** Responses stream token-by-token with live tool-activity narration
  ("Querying CoreOperations…") rather than a blocking spinner.
- **FR-1.5** Tabular results render as interactive charts when the agent emits a chart
  specification.

### FR-2 — Document intelligence
- **FR-2.1** Users upload a PDF/text document in-chat and immediately ask questions
  about it.
- **FR-2.2** Uploaded documents are chunked, embedded and indexed for semantic
  retrieval.
- **FR-2.3** The upload control reports honest state: indexed / partially indexed /
  failed — never a false success.
- **FR-2.4** Retrieval is scoped to the attached filename so answers cite the right
  document.

### FR-3 — Data trust
- **FR-3.1** Field completeness and row validity are **measured** on live tables, not
  asserted. *(Current: 13 field checks, 9 validity rules → 95.1% complete, 93.9% valid,
  58 real violations surfaced.)*
- **FR-3.2** Every violation names the table, the rule and the failing row count.
- **FR-3.3** No metric is displayed without a derivable source. Where data is
  insufficient the UI omits the figure rather than substituting a placeholder.

### FR-4 — Portfolio dashboard
- **FR-4.1** National and per-state KPIs with a geospatial cross-filter.
- **FR-4.2** Period-over-period deltas computed from source tables; direction and
  colour derived from the sign of the change.
- **FR-4.3** Trend, risk and churn analysis by category and plan tier.

### FR-5 — Product matching, pricing & recommendations
- **FR-5.1** Searchable customer directory filterable by name/ID/email, state, **plan
  held**, and **active-policy status**.
- **FR-5.2** Customer 360: policies, claims, churn predictions, at-risk flags, ratings
  and matched plans on one screen.
- **FR-5.3** AI product matching runs on demand and persists ranked matches with
  reasoning.
- **FR-5.4** Matched plans display commercial substance — premium, coverage, benefits,
  eligibility — not internal scoring weights.
- **FR-5.5** Users submit plan ratings through the same procedure the agent's rating
  tool calls, so both paths write identically.
- **FR-5.6** Competitive pricing position per product against competitor averages.
- **FR-5.7** AI-generated strategic recommendations, regenerable on demand.

### FR-6 — Conversation history
- **FR-6.1** Conversations persist across sessions.
- **FR-6.2** **A user sees only their own conversations.** History is scoped by
  username on read, message-fetch and delete.
- **FR-6.3** Sessions are titled by their chronologically first question.

### FR-7 — Demand forecasting & what-if simulation
- **FR-7.1** Users forecast future new-policy demand by policy type in natural
  language, with no model or horizon parameters to configure.
- **FR-7.2** Forecasts return a point estimate **and** a lower/upper confidence band,
  never a bare number.
- **FR-7.3** Users simulate the effect of a premium change on revenue, churn and
  demand before committing to it ("what happens if we raise Health Gold by 10% in TX?").
- **FR-7.4** A simulation reports **net** impact — the revenue gained from repricing
  less the revenue lost to churn and suppressed new demand — not the gross figure.
- **FR-7.5** Users retrain the forecasting model conversationally when new months of
  history land.
- **FR-7.6** Every forecast run and every simulation is persisted with its inputs, its
  assumptions and the requesting user, so a past recommendation can be audited.
- **FR-7.7** All four operations are reachable through a single question; the user never
  selects an operation from a menu.

## 1.5 Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-1 | No fabricated data. Every displayed figure traces to a query. | **Enforced** |
| NFR-2 | All user/LLM-supplied values reach SQL as bound parameters. | **Enforced** |
| NFR-3 | Agent-generated SQL is validated read-only before execution. | **Enforced** |
| NFR-4 | Query failures surface to the user, never silently swallowed. | **Enforced** |
| NFR-5 | Uploaded filenames sanitised before reaching SQL, stage or parser. | **Enforced** |
| NFR-6 | One pooled Snowflake connection; MFA prompt once per app lifetime. | **Enforced** |
| NFR-7 | Dashboard reads cached 30–600s by volatility. | **Enforced** |
| NFR-8 | Write actions invalidate dependent caches. | **Enforced** |

## 1.6 Explicitly out of scope
Multi-tenancy and row-level security; agent write-back to external systems (see §2.9);
mobile layout; scheduled/emailed reporting; model fine-tuning.

## 1.7 Success criteria
1. A named business question is answered end-to-end with zero SQL typed by the user.
2. A freshly uploaded PDF is queryable within one turn.
3. A data-quality violation is traced from KPI to failing row count conversationally.
4. Every dashboard number reconciles to a hand-written query.
5. Two users of the same app cannot see each other's conversations.

---

# PART 2 — TECHNICAL REQUIREMENTS (TRD)

## 2.1 Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│ PRESENTATION — Streamlit 1.61.1                                    │
│                                                                    │
│  streamlit_app.py (2,767)      pages/1_Enterprise_AI.py (546)       │
│   8 nav views, 13 cached        chat, SSE stream, upload chip,      │
│   fetchers, Vega-Lite,          thinking animation                  │
│   PyDeck 3-D map                                                    │
│                                 pages/2_Chat_History.py (339)       │
│  lib/render.py (365)            user-scoped session browser         │
│   response render, read-only                                        │
│   SQL gate, chart dispatch      lib/agent_client.py (58)             │
│  styles/style.css (1,107)       thin agent façade                   │
└───────────────────────────┬────────────────────────────────────────┘
                            │ Python function calls
┌───────────────────────────▼────────────────────────────────────────┐
│ SERVICE — services/backend_service.py (2,805)                      │
│  49 functions in 7 groups:                                         │
│   analytics · explore/rating · documents · agent SSE ·             │
│   chat persistence · security gate · text hygiene                  │
└───────────────────────────┬────────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────────┐
│ CONNECTION — config/snowflake_manager.py (328)                     │
│  singleton · MFA token cache · heartbeat · dual error contract     │
└───────────────────────────┬────────────────────────────────────────┘
                            │ snowflake-connector-python 4.7.2  +  REST/SSE
┌───────────────────────────▼────────────────────────────────────────┐
│ SNOWFLAKE — UNIFIEDAI_DB                                           │
│                                                                    │
│  UNIFIED_ENTERPRISE_AGENT ── 13 tools                              │
│    4 × cortex_analyst_text_to_sql │ 1 × cortex_search              │
│    6 × generic (stored proc)      │ data_to_chart, code_execution  │
│                                                                    │
│  4 semantic views │ INSURANCE_SEARCH_SVC │ 14 procedures           │
│  5 schemas: CORE · ANALYTICS · RISK · PREMIUM · UNIFIEDAI_SH       │
└────────────────────────────────────────────────────────────────────┘
```

## 2.2 Snowflake object inventory (verified live)

**Agent** `UNIFIEDAI_DB.UNIFIEDAI_SH.UNIFIED_ENTERPRISE_AGENT`, orchestration `auto`:

| Tool | Type | Backing resource |
|---|---|---|
| `CoreOperations` | cortex_analyst_text_to_sql | semantic view `CORE_OPERATIONS` |
| `AnalyticsKPI` | cortex_analyst_text_to_sql | semantic view `ANALYTICS_KPI` |
| `RiskChurn` | cortex_analyst_text_to_sql | semantic view `RISK_CHURN` |
| `PremiumPricing` | cortex_analyst_text_to_sql | semantic view `PREMIUM_PRICING` |
| `InsuranceDocs` | cortex_search | `INSURANCE_SEARCH_SVC` |
| `ProductMatch` | generic | `SP_PRODUCT_MATCH_AND_SAVE` |
| `PriceOptimize` | generic | `SP_PRICE_OPTIMIZE` |
| `RatePlan` | generic | `SP_RATE_PLAN` |
| `StrategicAdvisor` | generic | `SP_GENERATE_RECOMMENDATIONS` |
| `DQRootCause` | generic | `SP_DQ_ROOT_CAUSE_ANALYSIS` |
| `DemandEngine` | generic | `SP_UNIFIED_DEMAND_ENGINE` — forecast / what-if / retrain (§2.6) |
| `DataToChart` | data_to_chart | — |
| `CodeExecution` | code_execution | — |

**Data:**

| Schema | Contents | Volume |
|---|---|---|
| `CORE` | POLICIES 300 · CUSTOMERS 250 · CLAIMS 400 · AGENTS 25 | source of truth |
| `ANALYTICS` | CLAIMS_KPI 24 · POLICY_TRENDS 36 · LOSS_RATIO_HISTORY 48 · FRAUD_ALERTS 50 · DEMAND_FORECAST_RESULTS 180 · WHATIF_SIMULATION_LOG 1 | pre-aggregated + forecast output |
| `RISK` | CHURN_PREDICTIONS 300 · AT_RISK_POLICIES 165 · RISK_FACTORS 40 | + `V_RISK_CHURN` |
| `PREMIUM` | PREMIUM_CALCULATIONS 500 · PREMIUM_FACTORS 80 · PLAN_TIERS 16 | pricing inputs |
| `UNIFIEDAI_SH` | PRODUCT_CATALOG 20 · COMPETITOR_PRICING 60 · CUSTOMER_PRODUCT_MATCHES 50 · MATCHING_RULES 27 · STRATEGIC_RECOMMENDATIONS 8 · PLAN_RATINGS 3 · DOCUMENT_CHUNKS 61 · CHAT_HISTORY 53 | app + AI |

**Known data hazards — must be designed around, not discovered:**

| Object | Hazard | Required handling |
|---|---|---|
| `RISK.CHURN_PREDICTIONS` | 300 rows / **182 distinct** POLICY_ID | dedupe via `QUALIFY ROW_NUMBER()` before any join |
| `RISK.V_RISK_CHURN` | 511 rows / 300 policies; premium inflates to $4,182,013 vs true $2,411,620 | **do not use for aggregates** |
| `ANALYTICS.POLICY_TRENDS` | does not reconcile with CORE (373 vs 300 policies; $11.3M vs $2.4M) | never pair its deltas with a CORE headline |
| `CORE.CLAIMS` → geo | naive `LEFT JOIN` inflated premium to $3.89M | separate aggregate CTEs per fact table |
| `DQ_RULES`, `DQ_VALIDATION_RESULTS`, `DQ_RUN_LOGS`, `DOCUMENT_ENTITIES`, `ENTITY_RELATIONSHIPS`, `DQ_COLUMN_LINEAGE` | **0 rows** | measure quality directly on CORE; never present a rule-based score |

## 2.3 Connection layer

`SnowflakeManager` — singleton on a class attribute, so the instance survives
Streamlit reruns.

- `authenticator="username_password_mfa"` + `client_store_temporary_credential=True`
  → **one** Duo prompt per app lifetime. A fresh class object resets `_instance` and
  re-prompts, which is why module hot-reload hacks were removed.
- Background heartbeat keeps the session warm.
- **Dual error contract, deliberately:**
  - `execute_query(sql, params)` → `(rows, cols)` or `(None, None)`; records
    `_last_error`. Preserves 26 existing call sites.
  - `execute_query_checked(sql, params)` → raises `SnowflakeQueryError(message, sql)`.
  - `get_last_error()` → lets the UI surface why a query returned nothing.

## 2.4 Agent invocation and streaming

`POST /api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run`, session-token auth,
`stream=True`, timeouts `(10, 90)`.

Verified SSE event contract for one representative turn:

| Event | Count | Consumed as |
|---|---|---|
| `response.text.delta` | 47 | streaming answer text |
| `response.thinking.delta` | 23 | thinking animation |
| `response.status` | 23 | tool-activity label |
| `response.tool_use` | 4 | tool name + SQL extraction |
| `response.text` | 3 | final text block |
| `response.table` / `response.chart` | 1 each | dataframe / Vega-Lite spec |
| `response` | 1 | terminal payload |

Design points:
- `_SseAccumulator.handle()` folds events; `finalise()` returns the complete payload.
- `iter_sse_events()` is a generator over `iter_lines()` — no full-body buffering.
- `on_event` callback drives the live UI.
- `_balance_markdown()` closes unterminated `**`, backticks and fences on every
  partial frame; without it the stream renders literal asterisks mid-flight.
- Response closed before any no-model retry to avoid a leaked connection.

## 2.5 Document pipeline

```
upload → _safe_stage_filename() → PUT @DOC_STAGE
       → pypdf extract → ~1000-char chunks, 150 overlap
       → CORTEX.EMBED_TEXT_768, batches of 10, cap MAX_DOC_CHUNKS (400)
       → DOCUMENT_CHUNKS → ALTER CORTEX SEARCH SERVICE … REFRESH
       → retrieve_document_context(): SEARCH_PREVIEW filtered
         {"@eq": {"FILE_NAME": stored_name}}
       → build_attached_document_prompt() injects passages
```

Two non-obvious constraints:
- **The agent REST API has no attachment channel.** "Answer using the attached
  document" fails. Retrieval must happen app-side and passages must be injected into
  the prompt.
- `DOC_STAGE` uses client-side encryption, so `PARSE_DOCUMENT` fails against it.
  `ALTER STAGE … SET ENCRYPTION` is rejected for internal stages — only
  `CREATE OR REPLACE STAGE` can change it.

## 2.6 Demand forecasting engine

The only forecasting object in the codebase is a single intent-routing procedure. There
is no separate train / forecast / simulate procedure and no Python forecasting code —
the model is a native `SNOWFLAKE.ML.FORECAST` object.

| Object | Type | Detail |
|---|---|---|
| `ANALYTICS.SP_UNIFIED_DEMAND_ENGINE(P_QUESTION VARCHAR)` | SQL procedure, `EXECUTE AS CALLER` | The entire engine. Returns VARCHAR. |
| `ANALYTICS.DEMAND_FORECAST_MODEL` | `SNOWFLAKE.ML.FORECAST` | Multi-series model, one series per policy type |
| `ANALYTICS.V_DEMAND_FORECAST_TRAINING` | view | Training input: 36 rows, 4 series, 2026-01 → 2026-09 |
| `ANALYTICS.DEMAND_FORECAST_RESULTS` | table | 180 rows across 9 runs, horizon 2026-10 → 2027-09 |
| `ANALYTICS.WHATIF_SIMULATION_LOG` | table | 25 columns; 1 simulation logged |
| `DemandEngine` | agent tool (`generic`) | Bound to the procedure, warehouse `COMPUTE_WH` |

### Intent routing

The procedure is a natural-language front end, not a parameterised API. Step 1 calls
`SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', …)` with a strict extraction prompt and
`PARSE_JSON`s the reply into one of five intents plus seven optional parameters:

```
intent ∈ {TRAIN, FORECAST, WHATIF, SHOW_RESULTS, GENERAL}
horizon_months (1-12, default 3) · policy_type · avg_premium
plan_tier · state · premium_change_pct
```

This is why the agent tool description says *"Pass the user question as-is"* — the
agent must **not** pre-parse. Parameter extraction is the procedure's own first step, so
a caller that helpfully normalises the question would defeat it.

### The four branches

**`TRAIN`** issues `CREATE OR REPLACE SNOWFLAKE.ML.FORECAST` over
`V_DEMAND_FORECAST_TRAINING` with `SERIES_COLNAME => 'POLICY_TYPE'`,
`TIMESTAMP_COLNAME => 'MONTH_YEAR'`, `TARGET_COLNAME => 'NEW_POLICIES'` and
`CONFIG_OBJECT => {'ON_ERROR': 'SKIP'}`. `AVG_PREMIUM` rides along as an exogenous
feature, which is what allows the what-if branch to move demand by changing price.

**`FORECAST`** builds a future-frame temp table by cross-joining each series against a
`GENERATOR(ROWCOUNT => 12)` sequence clipped to `horizon_months`, carrying last known
premium forward per series via `QUALIFY ROW_NUMBER() … ORDER BY MONTH_YEAR DESC = 1`
(or the user's override premium where supplied). It then calls
`DEMAND_FORECAST_MODEL!FORECAST(...)`, clamps every output with
`GREATEST(ROUND(x, 0), 0)` so no negative policy counts are ever emitted, and appends
to `DEMAND_FORECAST_RESULTS` with `CURRENT_USER()` and a run timestamp.

**`WHATIF`** is the commercially interesting branch. It defaults `plan_tier` to `Gold`
and applies a **0.15 elasticity weight** to convert a premium change into a churn
change, then composes three effects into one net number:

```
revenue_delta          = projected_total_revenue − current_total_revenue
estimated_policies_lost ← churn_delta × policies_affected
demand_revenue_impact  ← (projected_new_3m − baseline_new_3m) × premium
combined_net_impact    = revenue_delta + demand_revenue_impact − churn loss
```

The logged example is instructive: a −10% premium change on Auto/Silver/CA over 7
policies gives `revenue_delta = −$5,870`, but demand rises by 1 policy worth `+$7,548`,
so `combined_net_impact` is **+$1,677** — the opposite sign to the headline revenue
figure. A UI that showed only `revenue_delta` would invert the recommendation.

**`SHOW_RESULTS`** reads `DEMAND_FORECAST_RESULTS` back without re-running the model.

### Constraints and hazards

| Constraint | Consequence |
|---|---|
| Training data is **9 months × 4 series** (36 rows) | Short series for a seasonal model; intervals are wide (Auto Oct-2026: forecast 18, band 5–32) |
| `V_DEMAND_FORECAST_TRAINING` starts 2026-01 while `CORE.POLICIES` starts 2024-09 | The model sees only 2026; the view is the contract, not the raw table |
| `TRAIN` runs `CREATE OR REPLACE` on a live model | A retrain is destructive and non-transactional; concurrent forecasts can fail mid-swap |
| Branch selection depends on an LLM classification | A misread question silently routes to `GENERAL`; the intent should be echoed back to the user |
| `DEMAND_FORECAST_RESULTS` is append-only with no run key exposed to the UI | 9 runs are interleaved; always filter to `MAX(FORECAST_RUN_TIMESTAMP)` |
| `0.15` elasticity is a hardcoded constant inside the procedure | Not derived from the data; must be presented as an assumption, not a measurement |
| `WHATIF` writes to `WHATIF_SIMULATION_LOG` | An agent turn has a **side effect** — relevant to the write-gating point in §2.9 |

### Not yet surfaced in the UI

Forecasting is reachable only conversationally through the `DemandEngine` agent tool.
No view in `streamlit_app.py` reads `DEMAND_FORECAST_RESULTS`, `WHATIF_SIMULATION_LOG`
or `V_DEMAND_FORECAST_TRAINING`. A dashboard panel plotting actuals against the latest
forecast band, and a table of logged simulations ranked by `COMBINED_NET_IMPACT`, are
the obvious additions and require no new backend logic beyond two read functions.

## 2.7 Security controls

| Control | Implementation | Threat closed |
|---|---|---|
| Read-only SQL gate | `assert_read_only_sql()` → `UnsafeSqlError`; blocklist of 19 keywords after `_strip_sql_noise()` blanks literals and strips comments. `REPLACE`/`GET` deliberately **excluded** — real Snowflake functions. | LLM-generated DML/DDL executing on click |
| Filename sanitisation | `_safe_stage_filename()` — strips drive letters and `\` segments (`basename` misses these from browser uploads), whitelists `[A-Za-z0-9._-]`, caps 180 chars preserving extension, raises on empty result | SQL/stage injection via upload name |
| Bound parameters | All filters and all of `save_chat_message`. Only integer row limits are interpolated, after `int()` coercion. | injection via search box, plan filter, chat content |
| Per-user history scoping | `USER_NAME` predicate on session list, message fetch **and** delete | cross-user disclosure; delete by guessed session ID |
| Error propagation | `get_last_error()` surfaced in UI | silent empty results read as "no data" |

## 2.8 Honest-metrics policy

The single most load-bearing design rule: **no number is displayed unless it is
derived.** Concretely removed during development:

- Five hardcoded trend strings (`"+8.4% MoM"`, `"+12.6% YoY"`, `"-1.8d YoY"`,
  `"+4.2% QoQ"`, `"+14.2%"`). Real values are **negative** — premium −30.1% YoY,
  −46.8% MoM. The literals asserted growth while the data showed decline.
- `data_trust_score: 88` and `"Enterprise Verified (Tier 1)"` — unsourceable, since
  all three `DQ_*` tables are empty. Replaced by measured completeness/validity.
- CSAT fallbacks `"4.05 / 5.0"` / `"81.0%"`, and time-series backfills `80.0` / `65.0`.
- A time series labelled "Data Trust Score" that was actually CSAT × 20 → renamed.

Implementation: `_pct_change()` returns `None` (not `0`) when a period is
uncomputable; `kpi_pill()` renders nothing for `None` and derives colour from the sign,
with `invert=True` where down is good.

## 2.9 MCP integration (design, not yet built)

Mechanism: `CREATE API INTEGRATION … API_PROVIDER = external_mcp` →
`CREATE EXTERNAL MCP SERVER` → `ALTER AGENT … SET SPECIFICATION` with `mcp_servers`.
Agent discovers tools via `tools/list` at invoke time.

| Connector | Decision | Rationale |
|---|---|---|
| **Atlassian** | adopt | Confluence supplies KPI definitions absent from the warehouse; Jira turns the 58 detected violations into filed remediation. Native auth. |
| **Salesforce** | adopt | Writes `CUSTOMER_PRODUCT_MATCHES` as Opportunities and `AT_RISK_POLICIES` as Tasks — closes the churn loop. Native auth. |
| **Google Drive** | conditional | Bulk document intake vs. one-at-a-time upload. Requires customer-owned Google OAuth client. |
| Linear / Gmail / Calendar / Contacts / Workday | reject | Duplicate Atlassian; native email integrations exist; Calendar and Contacts are read-only scopes; no HCM data in scope. |
| Glean | reject | Competes with `INSURANCE_SEARCH_SVC`. |

Two implementation constraints: the app uses `agent:run`, so per-user OAuth must be
driven via `SYSTEM$START_USER_OAUTH_FLOW` / `SYSTEM$FINISH_OAUTH_FLOW` (CoWork's
"Connect" button is unavailable); and MCP write tools bypass `assert_read_only_sql`
entirely, so they require an explicit UI confirmation gate.

Observability is native — MCP tool spans land in
`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` with tool names and latency.

## 2.10 Verification baseline

Regression anchors — any change must preserve these:

| Metric | Value |
|---|---|
| National policies / revenue / avg premium | 300 / $2,411,620 / $8,038.73 |
| Claims / claim amount / processing days | 400 / $15,094,802 / 21.7 |
| High-risk claims | 228 |
| Texas policies / revenue / claims | 103 / $825,708 / 138 |
| Geo states summing to national revenue | 7 → exactly $2,411,620 |
| Plan tiers | 4 × 75 = 300 |
| Completeness / validity | 95.1% / 93.9% |
| Violations found | 58 (53 approved-above-claimed, 5 resolved-before-claimed) |

Verification is by standalone scripts run outside Streamlit, asserting backend output
against independently hand-written SQL. Cumulative this session: **209 assertions,
0 failures.**

## 2.11 Known gaps

1. Six tables are empty (`DQ_*`, `DOCUMENT_ENTITIES`, `ENTITY_RELATIONSHIPS`); four
   procedures (`SP_BUILD_KNOWLEDGE_GRAPH`, `SP_ASK_WITH_CITATIONS`,
   `SP_SUMMARIZE_DOCUMENTS`, `SP_TRANSLATE_DOCUMENT`) are not surfaced in the UI.
2. `DOC_STAGE` encryption blocks `PARSE_DOCUMENT`; requires `CREATE OR REPLACE`.
3. `get_dts_analytics_data()` is fetched every rerun but its time series is unrendered.
4. Only 10 of 250 customers ship with product matches; the rest require an on-demand
   Cortex call.
5. `st.tabs` is not lazy — every tab body executes on every rerun.
6. Demand forecasting has **no UI surface** — reachable only via the agent (§2.6).
   `TRAIN` is a destructive `CREATE OR REPLACE` on a live model, and the 0.15 churn
   elasticity is a hardcoded constant rather than a fitted parameter.
7. No automated test suite; verification is script-based and manual to invoke.
8. `.env.example` still points at a decommissioned account.

---

## Appendix — file map

| File | Lines | Responsibility |
|---|---|---|
| `services/backend_service.py` | 2,805 | all data access, agent SSE, documents, security gate |
| `app/streamlit_app.py` | 2,767 | 8 nav views, 13 cached fetchers, charts, map |
| `app/styles/style.css` | 1,107 | glassmorphic theme, thinking animation, reduced-motion |
| `app/pages/1_Enterprise_AI.py` | 546 | chat, streaming, upload chip |
| `app/lib/render.py` | 365 | response rendering, read-only gate, chart dispatch |
| `app/pages/2_Chat_History.py` | 339 | user-scoped session browser |
| `config/snowflake_manager.py` | 328 | connection singleton, error contract |
| `docs/setup_document_pipeline.sql` | 100 | stage, chunk table, search service DDL |
| `app/lib/agent_client.py` | 58 | agent façade |
| `app/styles/style_loader.py` | 12 | CSS injection |

**Stack:** Python 3.12 · Streamlit 1.61.1 · snowflake-connector-python 4.7.2 ·
snowflake-snowpark-python 1.54.0 · snowflake-ml-python 1.51.0 · pandas 2.3.3 ·
numpy 2.5.2 · pypdf 6.15.0 · fastmcp 3.4.7 · Vega-Lite via altair (bundled)

**Charting note:** plotly is *not* installed. All charts are `st.vega_lite_chart`,
`st.pydeck_chart` or native Streamlit chart elements.
