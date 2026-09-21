# INSIGHT AI - UNIFIED ENTERPRISE AI AGENTS PLATFORM

**AI-Powered Self-Service Analytics, Document Intelligence & Data Trust**
Built on Snowflake Cortex Agents · Cross-Industry Enterprise Operations

> Ask a question in English. Get an answer drawn from the warehouse, from your
> documents, and with an explicit statement of how far the underlying data can be
> trusted. No SQL. No BI tool. No ticket to the data team.

---

## The problem

Business users cannot answer their own questions about enterprise data. Three
dependencies block them:

1. **Analytics requires SQL.** A regional manager asking *"why did premium fall this
   year?"* files a ticket and waits days for an analyst.
2. **Documents are opaque.** Policy wordings, contracts and rate filings are PDFs.
   Their contents cannot be queried alongside the warehouse.
3. **Nobody knows whether to trust the answer.** When a number looks wrong there is no
   way to ask *why* without a data engineer tracing lineage by hand.

Insight arrives too late to act on, and when it arrives its reliability is unknown.

## What this platform does

One conversational surface plus eight analytical views over a single Cortex Agent that
owns routing, tool selection and retrieval across five Snowflake schemas.

| Capability | How |
|---|---|
| **Self-service analytics** | 4 Cortex Analyst semantic views; the agent writes its own SQL and shows it |
| **Document intelligence** | Upload a PDF in chat, ask about it in the same turn |
| **Data trust** | Field completeness and row validity **measured** on live tables, not asserted |
| **Product matching** | Multi-strategy engine with AI reasoning, persisted per customer |
| **Price optimization** | 8-factor competitive engine with suggested price ranges |
| **Market intelligence** | Competitor benchmarking, entrant/exit pressure, trend detection |
| **Demand forecasting** | `SNOWFLAKE.ML.FORECAST` with what-if premium simulation |
| **Conversational RCA** | Root-cause analysis on data-quality violations |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION — Streamlit                                            │
│                                                                      │
│  streamlit_app.py (3,028)         pages/1_Enterprise_AI.py (549)      │
│   8 nav views · 14 cached          chat · SSE streaming · upload      │
│   fetchers · Vega-Lite · PyDeck    docked thinking indicator          │
│                                                                      │
│  lib/render.py (425)              pages/2_Chat_History.py (343)       │
│   response render · read-only      user-scoped session replay         │
│   SQL gate · chart dispatch                                          │
│  lib/toasts.py · lib/agent_client.py · styles/style.css (1,107)       │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ Python calls
┌─────────────────────────────▼────────────────────────────────────────┐
│  SERVICE — services/backend_service.py (2,971)                       │
│   51 functions: analytics · explore/rating · documents ·              │
│   agent SSE streaming · chat persistence · SQL safety gate            │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│  CONNECTION — config/snowflake_manager.py (328)                       │
│   singleton · MFA token cache · heartbeat · dual error contract       │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ connector + REST/SSE
┌─────────────────────────────▼────────────────────────────────────────┐
│  SNOWFLAKE — UNIFIEDAI_DB                                            │
│                                                                      │
│   UNIFIED_ENTERPRISE_AGENT ─ 13 tools                                │
│   4 semantic views │ INSURANCE_SEARCH_SVC │ 14 procedures            │
│   CORE · ANALYTICS · RISK · PREMIUM · UNIFIEDAI_SH                   │
└──────────────────────────────────────────────────────────────────────┘
```
## Getting started

### Prerequisites
- Python 3.12
- A Snowflake account with Cortex Agents, Cortex Analyst and Cortex Search enabled
- A warehouse (default `COMPUTE_WH`)

### 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill it in:

```ini
SNOWFLAKE_ACCOUNT=<org>-<account>
SNOWFLAKE_USERNAME=<user>
SNOWFLAKE_PASSWORD=<password>
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DB=UNIFIEDAI_DB
SNOWFLAKE_SH=UNIFIEDAI_SH
SNOWFLAKE_HOST_URL=<org>-<account>.snowflakecomputing.com

SEARCH_SERVICE=INSURANCE_SEARCH_SVC
MAX_DOC_CHUNKS=400
```

`.env` is never committed. Authentication uses `username_password_mfa` with
`client_store_temporary_credential=True`, so MFA is prompted **once** per app lifetime
rather than on every interaction.

### 3. Create the document pipeline

```bash
snowsql -f docs/setup_document_pipeline.sql
```

Creates `DOC_STAGE`, `DOCUMENT_CHUNKS` and `INSURANCE_SEARCH_SVC`.

### 4. Run

```bash
streamlit run app/streamlit_app.py
```
---

## The eight views

| View | What it does |
|---|---|
| **Insurance Portfolio** | KPIs with real period-over-period deltas, 3-D geospatial cross-filter, trend/risk/churn analysis, measured data-quality strip |
| **Enterprise AI** | Streaming chat, document upload, generated SQL with in-UI execution, auto-charting |
| **Explore** | 3 groups / 7 tabs: Operations · Customers & Ratings (Customer 360, plan rating) · Strategy & Market (recommendations, 8-factor pricing) |
| **Data** | Multi-schema catalog browser |
| **Docs** | Semantic layer and data dictionary |
| **Quality** | Data trust and integrity scorecard |
| **Incidents** | Fraud and high-risk claim alerts |
| **Settings** | Connection and configuration |

Plus **Chat History** — a user-scoped session replayer.

---

## Engineering principles

These are enforced in code, not aspirational.

### 1. No fabricated data
Every displayed figure traces to a query. Removed during development: five hardcoded
trend strings (`"+8.4% MoM"`, `"+12.6% YoY"`, …), a `data_trust_score: 88` with no
source, CSAT fallbacks, and time-series backfills. The real trends are **negative**
(premium −30.1% YoY) — the literals asserted growth while the data showed decline.

Deltas return `None` when a period is uncomputable, and the UI **omits the pill** rather
than implying a flat period.

### 2. Measured, not asserted, data quality
13 field checks and 9 validity rules run against `CORE`. Current: **95.1% field
completeness, 93.9% row validity**, surfacing **58 real violations** — 53 claims with
`APPROVED_AMOUNT > CLAIM_AMOUNT` and 5 resolved before they were filed.

### 3. Every value is a bound parameter
Filters, search terms and all of `save_chat_message`. Only integer row limits are
interpolated, after `int()` coercion.

### 4. Agent-generated SQL is gated
`assert_read_only_sql()` blocks 19 DML/DDL keywords after blanking string literals and
stripping comments. `REPLACE` and `GET` are deliberately **excluded** — they are real
Snowflake functions.

### 5. Failures surface
`execute_query()` returns `(None, None)` and records the error; `get_last_error()` lets
the UI say *why* nothing came back instead of rendering an empty table.

### 6. Filenames are sanitised, not escaped
`_safe_stage_filename()` strips drive letters and backslash segments (`basename` misses
these from browser uploads), whitelists `[A-Za-z0-9._-]`, and raises on an empty result.

### 7. Chat history is scoped per user
`USER_NAME` is a predicate on session list, message fetch **and** delete — knowing a
`SESSION_ID` is not enough to read or delete someone else's conversation.

---

## Rubric mapping

| Requirement | Implementation |
|---|---|
| **AI/SQL** | 4 Cortex Analyst semantic views; agent-authored SQL shown and executable in-UI |
| **Cortex Agents** | 1 agent, 13 tools, SSE streaming with live tool narration |
| **Product matching, multi-strategy** | `SP_PRODUCT_MATCH_AND_SAVE` + 27 `MATCHING_RULES`, ranked with AI reasoning |
| **Price optimization agent** | `SP_PRICE_OPTIMIZE` — 8 weighted factors, suggested range, net revenue impact |
| **Market intelligence / trend detection** | `V_PRICE_COMPARISON` + 60 competitor products; entrant/exit pressure; `SP_UNIFIED_DEMAND_ENGINE` |
| **Competitive pricing dashboard** | Explore → Strategy & Market: scatter vs market, 4 sub-tabs over 35 columns |
| **Market trend analysis** | Trend view, loss-ratio history, demand forecast with confidence bands |
| **Matching accuracy metrics** | Match scores, `V_MATCH_SUMMARY`, rating feedback loop via `SP_RATE_PLAN` |
| **Document intelligence** | Stage → chunk → embed → Cortex Search, with app-side retrieval injection |
| **Data trust / conversational RCA** | Measured completeness + `SP_DQ_ROOT_CAUSE_ANALYSIS` |
| **MCP Integration** | Designed and documented — see below |

### MCP integration

Evaluated all ten available connectors. **Adopted: Atlassian and Salesforce.**
Conditional: Google Drive.

- **Atlassian** — the only connector serving all three pillars. Confluence supplies KPI
  definitions that do not exist in the warehouse; Jira turns the 58 detected violations
  into filed remediation tickets, which matters because all three `DQ_*` tables are empty.
- **Salesforce** — closes the loop. `CUSTOMER_PRODUCT_MATCHES` becomes Opportunities;
  `AT_RISK_POLICIES` becomes Tasks assigned to each policy's `AGENT_ID`.

**Rejected, with reasons:** Linear (duplicates Jira) · Glean (competes with our own
Cortex Search) · Gmail (native email integrations already exist) · Calendar and Contacts
(**read-only scopes** — cannot create events) · Workday (no HCM data in scope).

Wiring is `CREATE API INTEGRATION (API_PROVIDER = external_mcp)` →
`CREATE EXTERNAL MCP SERVER` → `ALTER AGENT … SET SPECIFICATION` with `mcp_servers`.
Because this app uses `agent:run` rather than CoWork, per-user consent must be driven
through `SYSTEM$START_USER_OAUTH_FLOW` / `SYSTEM$FINISH_OAUTH_FLOW`.

**Write actions need a confirmation gate.** `assert_read_only_sql` does not see MCP tool
calls, and `SP_UNIFIED_DEMAND_ENGINE` already has side effects today — its WHATIF branch
writes to `WHATIF_SIMULATION_LOG` and TRAIN runs `CREATE OR REPLACE` on a live ML model.


## Repository layout

```
├── app/
│   ├── streamlit_app.py            3,028  8 nav views, cached fetchers, charts
│   ├── streamlit.py                   19  launcher (shadows `streamlit` — see Caveats)
│   ├── pages/
│   │   ├── 1_Enterprise_AI.py        549  chat, SSE, upload, thinking indicator
│   │   └── 2_Chat_History.py         343  user-scoped session replay
│   ├── lib/
│   │   ├── render.py                 425  response render, SQL gate, charts
│   │   ├── agent_client.py            58  agent façade
│   │   └── toasts.py                  41  rerun-safe toast queue
│   └── styles/
│       ├── style.css               1,107  theme, thinking animation, reduced-motion
│       └── style_loader.py            12
├── services/
│   └── backend_service.py          2,971  all data access, agent SSE, documents
├── config/
│   └── snowflake_manager.py           328  connection singleton, error contract
├── docs/
│   ├── PRD_TRD.md                    396  product + technical requirements
│   ├── setup_document_pipeline.sql   100  stage, chunk table, search service
│   ├── dashboard_details.sql         263
│   └── *_SP_UNIFIED_DEMAND_ENGINE.sql     forecast engine backup + deployed patch
├── requirements.txt
└── .env.example
```

**Stack:** Python 3.12 · Streamlit · snowflake-connector-python 4.7.2 ·
snowflake-snowpark-python 1.54.0 · snowflake-ml-python 1.51.0 · pandas 2.3.3 ·
numpy 2.5.2 · pypdf 6.15.0 · Vega-Lite via altair.
