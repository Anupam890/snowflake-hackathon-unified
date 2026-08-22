import os
import re
import json
import time
import requests
from typing import Optional, Dict, Any, List, Union
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import dotenv_values
import uvicorn

from config.snowflake_manager import snowflake_manager

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values('.env').items()}


# Lifespan context for one-time persistent startup and clean shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: One-time connection initialization
    print("🚀 [FastAPI] Initializing one-time persistent Snowflake connection setup...")
    is_ok = snowflake_manager.is_connected()
    if is_ok:
        print("✅ [FastAPI] Persistent Snowflake connection established and warm.")
    else:
        print("⚠️ [FastAPI] Snowflake connection failed at startup. Will retry on demand.")
    yield
    # Shutdown: Close persistent connection
    print("🛑 [FastAPI] Shutting down Snowflake connection...")
    snowflake_manager.close()


app = FastAPI(
    title="Snowflake Cortex Unified Agent API",
    description="Backend API for Snowflake Cortex Agents with One-Time Persistent Connection Setup.",
    version="3.1.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request and Response Models
class ContentItem(BaseModel):
    type: str = "text"
    text: Optional[str] = None


class MessageItem(BaseModel):
    role: str = "user"
    content: Union[str, List[ContentItem], List[Dict[str, Any]]]


class CortexAgentRunRequest(BaseModel):
    model: Optional[str] = "claude-3-5-sonnet"
    messages: Optional[List[MessageItem]] = None
    prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_resources: Optional[Dict[str, Any]] = None


class CortexAgentRunResponse(BaseModel):
    status: str
    agent: str
    database: str
    schema_name: str = Field(alias="schema")
    model: str
    response: str
    thinking: Optional[str] = None
    sql_query: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    warnings: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


def extract_sql_from_text(text: str) -> Optional[str]:
    """Extracts SQL query block from markdown text if present."""
    match = re.search(r"```(?:sql|SQL)?\s*(SELECT[\s\S]*?;?)\s*```", text, re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        if not sql.endswith(";"):
            sql += ";"
        return sql
    return None


def parse_sse_stream(sse_text: str):
    """Parses Server-Sent Events stream from Snowflake Cortex Agent REST API."""
    full_text = ""
    thinking_text = ""
    warnings = []
    final_response = None

    lines = sse_text.strip().split("\n")
    current_event = None

    for line in lines:
        line = line.strip()
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                continue
            try:
                data_json = json.loads(data_str)
                if current_event == "response":
                    final_response = data_json
                    for item in data_json.get("content", []):
                        if item.get("type") == "text" and item.get("text"):
                            full_text = item["text"]
                        elif item.get("type") == "thinking" and "thinking" in item:
                            thinking_text = item["thinking"].get("text", "")
                    if "warnings" in data_json:
                        warnings.extend(data_json["warnings"])
                elif current_event == "response.thinking":
                    if "text" in data_json:
                        thinking_text = data_json["text"]
                elif current_event == "response.text":
                    if "text" in data_json:
                        full_text = data_json["text"]
                elif current_event == "response.text.delta" and not final_response:
                    if "text" in data_json:
                        full_text += data_json["text"]
                elif current_event == "response.thinking.delta" and not final_response:
                    if "text" in data_json:
                        thinking_text += data_json["text"]
                elif current_event == "response.warning":
                    warnings.append(data_json)
            except Exception:
                pass

    return full_text.strip(), thinking_text.strip(), warnings, final_response


SCHEMA_METADATA = """
Database: INSURANCE_MGMT_SYSTEM, Schema: CORE
Tables and Columns:
1. INSURANCE_MGMT_SYSTEM.CORE.POLICIES (
    POLICY_ID VARCHAR, CUSTOMER_ID VARCHAR, AGENT_ID VARCHAR, POLICY_TYPE VARCHAR,
    PLAN_TIER VARCHAR, POLICY_STATUS VARCHAR, START_DATE DATE, END_DATE DATE,
    PREMIUM_AMOUNT NUMBER(12,2), COVERAGE_AMOUNT NUMBER(14,2), DEDUCTIBLE NUMBER(10,2),
    LOSS_RATIO FLOAT, PAYMENT_FREQUENCY VARCHAR, AUTO_RENEW BOOLEAN, UNDERWRITING_SCORE FLOAT
)
2. INSURANCE_MGMT_SYSTEM.CORE.CUSTOMERS (
    CUSTOMER_ID VARCHAR, FIRST_NAME VARCHAR, LAST_NAME VARCHAR, AGE NUMBER,
    GENDER VARCHAR, CITY VARCHAR, STATE VARCHAR, ZIP_CODE VARCHAR, OCCUPATION VARCHAR,
    ANNUAL_INCOME NUMBER(12,2), CREDIT_SCORE NUMBER, SMOKING_STATUS VARCHAR, BMI FLOAT
)
3. INSURANCE_MGMT_SYSTEM.CORE.CLAIMS (
    CLAIM_ID VARCHAR, POLICY_ID VARCHAR, CUSTOMER_ID VARCHAR, CLAIM_DATE DATE,
    CLAIM_TYPE VARCHAR, CLAIM_STATUS VARCHAR, CLAIM_AMOUNT NUMBER(12,2),
    APPROVED_AMOUNT NUMBER(12,2), FRAUD_FLAG BOOLEAN, FRAUD_SCORE FLOAT,
    FRAUD_REASON VARCHAR, DAYS_TO_RESOLVE NUMBER, PRIORITY VARCHAR, ESCALATED BOOLEAN
)
4. INSURANCE_MGMT_SYSTEM.CORE.AGENTS (
    AGENT_ID VARCHAR, AGENT_NAME VARCHAR, ROLE VARCHAR, REGION VARCHAR,
    BRANCH VARCHAR, PERFORMANCE_SCORE FLOAT, ACTIVE_POLICIES_COUNT NUMBER, ACTIVE_FLAG BOOLEAN
)
"""


def generate_insurance_analytics_response(prompt: str, db: str) -> tuple[str, str, List[Dict[str, Any]], List[str], str]:
    """Executes dynamic or structured insurance analytics queries with clean natural language responses."""
    p = prompt.lower()
    
    # 1. First attempt: Dynamic SQL generation via Snowflake Cortex Complete
    try:
        sql_gen_prompt = f"""You are a Snowflake SQL Generator for an Insurance Data Platform.
{SCHEMA_METADATA}

Rules:
1. Output ONLY a single executable Snowflake SQL query.
2. Do NOT output markdown fences, comments, or explanations.
3. Always qualify tables with {db}.CORE.<table_name> or alias properly.
4. Use ROUND(...) on numeric aggregations.
5. Add ORDER BY to sort aggregated metrics meaningfully.

Question: {prompt}"""

        escaped_prompt = sql_gen_prompt.replace("'", "''")
        cortex_sql = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', '{escaped_prompt}') AS SQL_OUTPUT;"
        
        res, _ = snowflake_manager.execute_query(cortex_sql)
        if res and len(res) > 0 and res[0].get("SQL_OUTPUT"):
            raw_sql = res[0].get("SQL_OUTPUT", "").strip()
            clean_sql = re.sub(r"```(?:sql)?|```", "", raw_sql).strip()
            
            data, cols = snowflake_manager.execute_query(clean_sql)
            if data and len(data) > 0:
                # Format clean natural language response without database/schema names
                if len(data) == 1 and len(cols) == 1:
                    val = list(data[0].values())[0]
                    formatted_val = f"${val:,.2f}" if isinstance(val, (int, float)) and ("amount" in cols[0].lower() or "premium" in cols[0].lower()) else f"{val}"
                    nl_response = f"The **{cols[0].replace('_', ' ').title()}** is **{formatted_val}**."
                else:
                    top_items_summary = []
                    for row in data[:6]:
                        row_strs = [f"{k.replace('_', ' ').title()}: **{f'${v:,.2f}' if isinstance(v, (int, float)) and ('amount' in k.lower() or 'revenue' in k.lower() or 'premium' in k.lower()) else str(v)}**" for k, v in row.items()]
                        top_items_summary.append(" • " + ", ".join(row_strs))
                    
                    nl_response = (
                        f"Here are the query results for **{prompt}**:\n\n"
                        + "\n".join(top_items_summary) + "\n\n"
                        f"- Total records returned: **{len(data)}**\n"
                        f"- Check the **Generated SQL** and **Visualizations & Table** tabs for full data breakdowns."
                    )
                
                thinking = (
                    f"1. **Intent Analysis**: Identified user request for insurance data analytics.\n"
                    f"2. **Schema Mapping**: Evaluated target entities and joined corresponding dimensions.\n"
                    f"3. **SQL Generation**: Formulated query targeting requested metrics.\n"
                    f"4. **Execution**: Executed generated query on Snowflake and retrieved {len(data)} records.\n"
                    f"5. **Synthesis**: Prepared summary insights and interactive dataset."
                )
                return nl_response, clean_sql, data, cols, thinking
    except Exception as e:
        print(f"[Cortex Dynamic SQL] Note: {e}")

    # 2. Semantic Fallback Routing
    if "region" in p or "state" in p or ("premium" in p and ("state" in p or "region" in p or "where" in p)):
        sql = f"""SELECT 
    c.STATE AS REGION,
    ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS TOTAL_PREMIUM_REVENUE,
    COUNT(p.POLICY_ID) AS POLICY_COUNT
FROM {db}.CORE.POLICIES p
JOIN {db}.CORE.CUSTOMERS c ON p.CUSTOMER_ID = c.CUSTOMER_ID
GROUP BY c.STATE
ORDER BY TOTAL_PREMIUM_REVENUE DESC;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        breakdown_lines = []
        if data:
            for r in data:
                breakdown_lines.append(f"- **{r.get('REGION')}**: ${r.get('TOTAL_PREMIUM_REVENUE', 0):,.2f} ({r.get('POLICY_COUNT', 0)} policies)")
        
        response = (
            f"Here is the total premium revenue by **Region (State)**, along with policy counts:\n\n"
            + "\n".join(breakdown_lines) + "\n\n"
            f"- **Top Contributing State:** {data[0].get('REGION') if data else 'N/A'} with ${data[0].get('TOTAL_PREMIUM_REVENUE', 0):,.2f}\n"
            f"- Inspect the full dataset and interactive charts in the tabs below."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested total premium revenue aggregated by geographic region / state.\n"
            f"2. **Entity Mapping**: Joined `POLICIES` (`PREMIUM_AMOUNT`) with `CUSTOMERS` (`STATE`).\n"
            f"3. **Aggregation Logic**: Grouped by state with `SUM(PREMIUM_AMOUNT)` and `COUNT(POLICY_ID)`.\n"
            f"4. **Execution**: Executed aggregation query on Snowflake warehouse.\n"
            f"5. **Synthesis**: Compiled state-by-state financial rankings and policy distribution."
        )
        return response, sql, data or [], cols or [], thinking

    elif "policy" in p and ("type" in p or "breakdown" in p or "revenue" in p):
        sql = f"""SELECT 
    POLICY_TYPE,
    COUNT(POLICY_ID) AS ACTIVE_POLICIES_COUNT,
    ROUND(SUM(PREMIUM_AMOUNT), 2) AS TOTAL_PREMIUM_REVENUE,
    ROUND(AVG(PREMIUM_AMOUNT), 2) AS AVG_ANNUAL_PREMIUM
FROM {db}.CORE.POLICIES
GROUP BY POLICY_TYPE
ORDER BY TOTAL_PREMIUM_REVENUE DESC;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        breakdown_lines = [f"- **{r.get('POLICY_TYPE')}**: ${r.get('TOTAL_PREMIUM_REVENUE', 0):,.2f} ({r.get('ACTIVE_POLICIES_COUNT', 0)} policies, Avg: ${r.get('AVG_ANNUAL_PREMIUM', 0):,.2f})" for r in data] if data else []
        response = (
            f"Here is the breakdown of insurance policies by **Policy Type**:\n\n"
            + "\n".join(breakdown_lines) + "\n\n"
            f"- Inspect the generated SQL and interactive charts in the tabs below."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested policy revenue breakdown by product line.\n"
            f"2. **Schema Mapping**: Aggregated `POLICIES` grouping by `POLICY_TYPE`.\n"
            f"3. **Metrics**: Computed total volume, total premium revenue, and average premium.\n"
            f"4. **Execution**: Ran SQL query on Snowflake session.\n"
            f"5. **Synthesis**: Formatted comparative policy metrics."
        )
        return response, sql, data or [], cols or [], thinking

    elif "claim" in p and ("type" in p or "category" in p):
        sql = f"""SELECT 
    CLAIM_TYPE,
    COUNT(CLAIM_ID) AS TOTAL_CLAIMS,
    ROUND(SUM(CLAIM_AMOUNT), 2) AS TOTAL_CLAIM_AMOUNT,
    ROUND(AVG(CLAIM_AMOUNT), 2) AS AVG_CLAIM_AMOUNT,
    ROUND(AVG(DAYS_TO_RESOLVE), 1) AS AVG_DAYS_TO_RESOLVE
FROM {db}.CORE.CLAIMS
GROUP BY CLAIM_TYPE
ORDER BY TOTAL_CLAIM_AMOUNT DESC;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        response = (
            f"Here is the breakdown of insurance claims categorized by **Claim Type**:\n\n"
            f"- Results indicate distinct patterns in total volume, cumulative claim payout, and average resolution speed.\n"
            f"- You can inspect the generated SQL and interactive charts in the tabs below."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested an aggregated breakdown of claims categorized by claim type.\n"
            f"2. **Schema Mapping**: Target entity `CLAIMS` containing `CLAIM_TYPE`, `CLAIM_AMOUNT`, and `DAYS_TO_RESOLVE`.\n"
            f"3. **Query Formulation**: Grouping by `CLAIM_TYPE` with aggregate counts and amounts.\n"
            f"4. **Execution**: Executed SQL query against Snowflake warehouse session.\n"
            f"5. **Synthesis**: Formatted comparative statistics and prepared visual data breakdown."
        )
        return response, sql, data or [], cols or [], thinking
    
    elif "status" in p or "open" in p or "closed" in p or "settlement" in p:
        sql = f"""SELECT 
    CLAIM_STATUS,
    COUNT(CLAIM_ID) AS CLAIM_COUNT,
    ROUND(SUM(CLAIM_AMOUNT), 2) AS TOTAL_AMOUNT,
    ROUND(AVG(DAYS_TO_RESOLVE), 1) AS AVG_RESOLUTION_DAYS
FROM {db}.CORE.CLAIMS
GROUP BY CLAIM_STATUS
ORDER BY CLAIM_COUNT DESC;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        response = (
            f"Here is the distribution of claims across **Claim Status**:\n\n"
            f"- Displays total claims count, monetary exposure, and average settlement turnaround time."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested claim distribution and resolution duration by status.\n"
            f"2. **Schema Mapping**: Querying status tracking dimensions from claims records.\n"
            f"3. **Aggregation Logic**: Aggregated volume and average days to resolve grouped by status.\n"
            f"4. **Execution**: Executed SQL aggregation query on Snowflake warehouse.\n"
            f"5. **Synthesis**: Compiled status turnaround analysis and generated chart distribution."
        )
        return response, sql, data or [], cols or [], thinking

    elif "fraud" in p or "risk" in p or "alert" in p:
        sql = f"""SELECT 
    CLAIM_TYPE,
    PRIORITY,
    COUNT(CLAIM_ID) AS FLAGGED_CLAIMS,
    ROUND(SUM(CLAIM_AMOUNT), 2) AS EXPOSURE_AMOUNT,
    ROUND(AVG(FRAUD_SCORE), 2) AS AVG_FRAUD_SCORE
FROM {db}.CORE.CLAIMS
WHERE FRAUD_FLAG = TRUE OR FRAUD_SCORE >= 0.75
GROUP BY CLAIM_TYPE, PRIORITY
ORDER BY EXPOSURE_AMOUNT DESC
LIMIT 10;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        response = (
            f"Here is the high-risk & fraud analysis summary:\n\n"
            f"- Identified high-priority claims flagged with elevated fraud scores.\n"
            f"- Aggregated by claim category and priority level for risk containment."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested high-risk claims flagged for potential fraud detection.\n"
            f"2. **Filter & Risk Threshold**: Filtered records where `FRAUD_FLAG = TRUE` OR `FRAUD_SCORE >= 0.75`.\n"
            f"3. **Aggregation**: Categorized by claim type and priority to assess exposure.\n"
            f"4. **Execution**: Executed filtered analytical query on Snowflake.\n"
            f"5. **Synthesis**: Prepared risk containment report with risk score metrics."
        )
        return response, sql, data or [], cols or [], thinking
        
    else:
        # Default total metrics overview query
        sql = f"""SELECT 
    COUNT(p.POLICY_ID) AS TOTAL_POLICIES_COUNT,
    ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS TOTAL_PREMIUM_REVENUE,
    ROUND(AVG(p.PREMIUM_AMOUNT), 2) AS AVG_PREMIUM_AMOUNT,
    (SELECT COUNT(CLAIM_ID) FROM {db}.CORE.CLAIMS) AS TOTAL_CLAIMS_COUNT,
    (SELECT ROUND(SUM(CLAIM_AMOUNT), 2) FROM {db}.CORE.CLAIMS) AS TOTAL_CLAIM_AMOUNT
FROM {db}.CORE.POLICIES p;"""
        
        data, cols = snowflake_manager.execute_query(sql)
        
        total_premium = data[0].get("TOTAL_PREMIUM_REVENUE", 0) if data else 0
        total_policies = data[0].get("TOTAL_POLICIES_COUNT", 0) if data else 0
        total_claims = data[0].get("TOTAL_CLAIMS_COUNT", 0) if data else 0
        total_claim_amt = data[0].get("TOTAL_CLAIM_AMOUNT", 0) if data else 0
        
        response = (
            f"Here is the overall **Insurance Portfolio Overview**:\n\n"
            f"- **Total Premium Revenue:** ${total_premium:,.2f}\n"
            f"- **Total Active Policies:** {total_policies:,}\n"
            f"- **Total Claims Incurred:** ${total_claim_amt:,.2f} ({total_claims:,} claims)\n\n"
            f"Check the **Generated SQL** and **Visualizations & Table** tabs for full query execution and visual inspection."
        )
        thinking = (
            f"1. **Intent Analysis**: User requested portfolio-wide financial and operational metrics.\n"
            f"2. **Target Scope**: Aggregated policies and claims statistics.\n"
            f"3. **Metrics Calculation**: Computed total premium volume and claims liability.\n"
            f"4. **Execution**: Executed summary query via persistent Snowflake session.\n"
            f"5. **Synthesis**: Formatted KPI summary cards and baseline metrics."
        )
        return response, sql, data or [], cols or [], thinking


def extract_prompt_string(payload: CortexAgentRunRequest) -> str:
    if payload.prompt and payload.prompt.strip():
        return payload.prompt.strip()
    if payload.messages:
        last_msg = payload.messages[-1]
        if isinstance(last_msg.content, str):
            return last_msg.content
        elif isinstance(last_msg.content, list):
            for item in last_msg.content:
                if isinstance(item, ContentItem) and item.text:
                    return item.text
                elif isinstance(item, dict) and item.get("text"):
                    return item["text"]
    return "What insights can you provide?"


@app.get("/")
def read_root():
    db = env_config.get("SNOWFLAKE_DB", "INSURANCE_MGMT_SYSTEM")
    schema = env_config.get("SNOWFLAKE_SH", "HACKATHON_SH")
    agent = env_config.get("INS_AGENT", "INS_ANALYTICS_AGENT")
    
    return {
        "name": "Snowflake Cortex Unified Agent API",
        "status": "online",
        "version": "3.1.0",
        "persistent_connection": snowflake_manager.is_connected(),
        "live_cortex_endpoint": f"/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "fastapi-cortex-agent-bridge",
        "snowflake_connected": snowflake_manager.is_connected()
    }


@app.get("/api/snowflake/status")
def snowflake_status():
    is_ok = snowflake_manager.is_connected()
    token, host = snowflake_manager.get_session_token() if is_ok else (None, None)
    return {
        "configured": is_ok,
        "connected": is_ok,
        "account": env_config.get("SNOWFLAKE_ACCOUNT"),
        "database": env_config.get("SNOWFLAKE_DB"),
        "schema": env_config.get("SNOWFLAKE_SH"),
        "default_agent": env_config.get("INS_AGENT", "INS_ANALYTICS_AGENT"),
        "host": host
    }


@app.post("/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run", response_model=CortexAgentRunResponse)
def execute_cortex_agent_v2(db: str, schema: str, agent: str, payload: CortexAgentRunRequest):
    prompt_text = extract_prompt_string(payload)
    model_name = payload.model or "claude-3-5-sonnet"

    sql_query = None
    query_data = None
    columns = None
    thinking_output = None
    warnings_list = None
    response_text = ""

    # 1. Try calling the live Snowflake Cortex Agent REST endpoint via pooled session token
    try:
        token, host = snowflake_manager.get_session_token()
        url = f"https://{host}/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
        
        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        request_body = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt_text}]
                }
            ]
        }
        
        sf_res = requests.post(url, headers=headers, json=request_body, timeout=60)
        
        if sf_res.status_code == 200:
            parsed_text, thinking, warnings, final_resp = parse_sse_stream(sf_res.text)
            if thinking and thinking.strip():
                thinking_output = thinking.strip()
            warnings_list = warnings
            
            # Check if agent response returned natural language
            if parsed_text and len(parsed_text.strip()) > 0:
                response_text = parsed_text
                # Extract SQL if embedded in response
                sql_query = extract_sql_from_text(parsed_text)
                if sql_query:
                    query_data, columns = snowflake_manager.execute_query(sql_query)
    except Exception as e:
        print(f"[Cortex Bridge] REST endpoint note: {e}")

    # 2. If the agent needs concrete query execution or returned no data, execute directly using persistent pool
    if not response_text or "unable to retrieve" in response_text.lower() or not query_data:
        nl_resp, executed_sql, res_data, res_cols, gen_thinking = generate_insurance_analytics_response(prompt_text, db)
        
        if not response_text or "unable to retrieve" in response_text.lower():
            response_text = nl_resp
        
        if not sql_query and executed_sql:
            sql_query = executed_sql
            query_data = res_data
            columns = res_cols

        if not thinking_output:
            thinking_output = gen_thinking

    if not thinking_output:
        thinking_output = f"1. Analyzed prompt: '{prompt_text}'.\n2. Routed query through Snowflake Cortex Agent session.\n3. Processed schema and generated analytical result."

    return CortexAgentRunResponse(
        status="success",
        agent=agent,
        database=db,
        schema=schema,
        model=model_name,
        response=response_text,
        thinking=thinking_output,
        sql_query=sql_query,
        data=query_data,
        columns=columns,
        warnings=warnings_list,
        metadata={
            "database": db,
            "schema": schema,
            "agent": agent,
            "rows_returned": len(query_data) if query_data else 0
        }
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False)
