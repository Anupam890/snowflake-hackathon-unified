import streamlit as st
import json
import requests
import pandas as pd
from dotenv import dotenv_values

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values('.env').items()}

# Streamlit Page Configuration
st.set_page_config(
    page_title="Snowflake Cortex Unified Agent Studio",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Theme and UI Polish
st.markdown("""
    <style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        color: #29B5E8;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.2rem;
    }
    .endpoint-badge {
        background-color: #0E1117;
        color: #00D4B2;
        padding: 6px 14px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.92rem;
        border: 1px solid #1E293B;
        margin-bottom: 1rem;
        display: inline-block;
    }
    .metric-container {
        background-color: #1E293B;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        text-align: center;
    }
    .nl-answer-box {
        background-color: #111827;
        border-left: 4px solid #29B5E8;
        padding: 18px 20px;
        border-radius: 6px;
        font-size: 1.05rem;
        line-height: 1.6;
        margin-bottom: 15px;
    }
    /* ChatGPT-style Thinking Component Styles */
    div[data-testid="stExpander"] {
        border: 1px solid #2D3748 !important;
        border-radius: 8px !important;
        background-color: rgba(15, 23, 42, 0.45) !important;
        margin-bottom: 12px !important;
        transition: all 0.2s ease-in-out;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #4A5568 !important;
    }
    div[data-testid="stExpander"] summary {
        color: #94A3B8 !important;
        font-size: 0.90rem !important;
        font-weight: 500 !important;
        padding-top: 4px !important;
        padding-bottom: 4px !important;
    }
    div[data-testid="stExpander"] summary:hover {
        color: #38BDF8 !important;
    }
    div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
        color: #94A3B8 !important;
        font-size: 0.90rem !important;
        line-height: 1.6 !important;
        border-left: 2px solid #3B82F6;
        padding-left: 12px !important;
        margin-top: 4px !important;
        margin-bottom: 4px !important;
    }
    .thinking-live-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: #94A3B8;
        font-size: 0.92rem;
        background: rgba(30, 41, 59, 0.5);
        padding: 6px 14px;
        border-radius: 6px;
        border-left: 3px solid #29B5E8;
        margin-bottom: 12px;
        animation: pulseFade 1.6s infinite ease-in-out;
    }
    @keyframes pulseFade {
        0% { opacity: 0.5; }
        50% { opacity: 1; }
        100% { opacity: 0.5; }
    }
    </style>
""", unsafe_allow_html=True)


# Helper: Check Backend Status
def check_backend_health(base_url: str):
    try:
        res = requests.get(f"{base_url}/api/health", timeout=3)
        if res.status_code == 200:
            return True, res.json()
    except Exception as e:
        return False, str(e)
    return False, "Offline"


# Helper: Get Snowflake Status
def get_snowflake_status(base_url: str):
    try:
        res = requests.get(f"{base_url}/api/snowflake/status", timeout=4)
        if res.status_code == 200:
            return res.json()
    except Exception:
        return None
    return None


# Helper: Run Cortex Agent Request
def call_cortex_agent(base_url: str, db: str, schema: str, agent: str, prompt: str, model: str):
    endpoint_url = f"{base_url}/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "prompt": prompt
    }
    
    try:
        res = requests.post(endpoint_url, json=payload, timeout=65)
        if res.status_code == 200:
            return res.json(), endpoint_url, payload
        else:
            return {
                "status": "error",
                "response": f"Server error ({res.status_code}): {res.text}"
            }, endpoint_url, payload
    except Exception as e:
        return {
            "status": "error",
            "response": f"Connection Error: {str(e)}"
        }, endpoint_url, payload


# Sidebar Settings
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Inc._logo.svg", width=170)
    st.markdown("### ⚙️ Cortex REST API")
    
    api_url = st.text_input("FastAPI Backend URL", value="http://127.0.0.1:8001")
    is_healthy, _ = check_backend_health(api_url)
    
    if is_healthy:
        st.success("🟢 Backend API Connected")
    else:
        st.error("🔴 Backend API Offline")
        st.caption("Ensure `uvicorn main:app --port 8001` is running.")
        
    sf_status = get_snowflake_status(api_url) if is_healthy else None
    if sf_status and sf_status.get("connected"):
        st.info(f"❄️ Snowflake: `{sf_status.get('account')}`")
    
    st.divider()
    st.markdown("### 🏛️ Target Snowflake Scope")
    
    default_db = env_config.get("SNOWFLAKE_DB", "INSURANCE_MGMT_SYSTEM")
    default_sh = env_config.get("SNOWFLAKE_SH", "HACKATHON_SH")
    default_agent = env_config.get("INS_AGENT", "INS_ANALYTICS_AGENT")
    
    db_name = st.text_input("Database (`{db}`)", value=default_db)
    schema_name = st.text_input("Schema (`{schema}`)", value=default_sh)
    agent_name = st.text_input("Agent Name (`{agent}`)", value=default_agent)
    
    model_name = st.selectbox(
        "Model",
        ["claude-3-5-sonnet", "snowflake-arctic", "mistral-large2", "llama3.1-70b"],
        index=0
    )
    
    st.divider()
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.rerun()


# Main Application Interface
st.markdown('<div class="main-title">❄️ Snowflake Cortex Unified Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Natural Language Analytics • Automated SQL Generation • Interactive Charts & Data Tables</div>', unsafe_allow_html=True)

active_endpoint = f"/api/v2/databases/{db_name}/schemas/{schema_name}/agents/{agent_name}:run"
st.markdown(f'<div class="endpoint-badge">POST {active_endpoint}</div>', unsafe_allow_html=True)

# Quick Prompts / Demo Questions
st.markdown("**Suggested Quick Prompts:**")
c1, c2, c3, c4 = st.columns(4)

if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None

with c1:
    if st.button("📊 Total Claim Amount", use_container_width=True):
        st.session_state.selected_prompt = "What is the total claim amount across all records?"
with c2:
    if st.button("📈 Claims by Policy Type", use_container_width=True):
        st.session_state.selected_prompt = "Show me the claims breakdown and total amount categorized by claim type."
with c3:
    if st.button("⏱️ Settlement Days by Status", use_container_width=True):
        st.session_state.selected_prompt = "What is the claims distribution and average resolution days by claim status?"
with c4:
    if st.button("🚨 High Risk & Fraud Alerts", use_container_width=True):
        st.session_state.selected_prompt = "Show high priority claims flagged with fraud scores."

st.divider()

# Session State for Conversation History
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"Hello! I am your **Snowflake Cortex Agent** connected to `{db_name}.{schema_name}`. Ask any question to get natural language insights, generated SQL, and interactive charts.",
            "sql": None,
            "data": None,
            "thinking": None,
            "raw_payload": None
        }
    ]


def render_assistant_response(msg_dict, msg_key_prefix=""):
    """Renders the assistant message with ChatGPT-style Thinking expander, Natural Language, SQL, and Visualizations."""
    response_text = msg_dict.get("content", "")
    sql_query = msg_dict.get("sql")
    query_data = msg_dict.get("data")
    thinking = msg_dict.get("thinking")

    # 1. ChatGPT-style Collapsible Thinking Process (at top of response)
    if thinking and thinking.strip():
        with st.expander("💭 Thought for a few seconds", expanded=False):
            st.markdown(thinking)

    # 2. Main Response Tabs
    tab_titles = ["💬 Answer"]
    if sql_query:
        tab_titles.append("🔍 Generated SQL")
    if query_data and len(query_data) > 0:
        tab_titles.append("📊 Visualizations & Table")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    # 1. Natural Language Answer Tab
    with tabs[tab_idx]:
        st.markdown(response_text)
    tab_idx += 1

    # 2. SQL Tab (if present)
    if sql_query:
        with tabs[tab_idx]:
            st.markdown("**Generated Snowflake SQL Query:**")
            st.code(sql_query, language="sql")
        tab_idx += 1

    # 3. Visualizations & Data Table Tab (if data present)
    if query_data and len(query_data) > 0:
        with tabs[tab_idx]:
            df = pd.DataFrame(query_data)
            
            # Numeric & Categorical columns
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            text_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

            # Chart Controls
            st.markdown("### 📊 Interactive Visualizations")
            
            if len(numeric_cols) > 0:
                chart_formats = ["Summary Metrics", "Bar Chart", "Line Chart", "Area Chart"] if len(df) == 1 else ["Bar Chart", "Line Chart", "Area Chart", "Summary Metrics"]
                
                chart_type = st.radio(
                    "Select Chart Format:",
                    chart_formats,
                    horizontal=True,
                    key=f"chart_type_{msg_key_prefix}_{id(msg_dict)}"
                )

                if chart_type == "Summary Metrics":
                    m_cols = st.columns(min(len(numeric_cols), 4))
                    for i, num_col in enumerate(numeric_cols[:4]):
                        with m_cols[i % min(len(numeric_cols), 4)]:
                            if len(df) == 1:
                                val = df[num_col].iloc[0]
                                label = num_col.replace('_', ' ').title()
                            else:
                                is_sum = any(k in num_col for k in ["TOTAL", "SUM", "COUNT"])
                                val = df[num_col].sum() if is_sum else df[num_col].mean()
                                label = ("Total " if is_sum else "Avg ") + num_col.replace('_', ' ').title()
                            
                            if pd.isna(val):
                                val_str = "N/A"
                            elif isinstance(val, (int, float)):
                                val_str = f"{val:,.2f}" if (isinstance(val, float) and val % 1 != 0) else f"{int(val):,}"
                            else:
                                val_str = str(val)
                                
                            st.metric(label=label, value=val_str)

                else:
                    try:
                        if text_cols:
                            x_col = text_cols[0]
                            y_cols = [col for col in numeric_cols if col != x_col]
                            if y_cols:
                                chart_df = df.set_index(x_col)[y_cols[:3]]
                            else:
                                chart_df = df.set_index(x_col)
                        else:
                            if len(df) == 1:
                                # Transpose single row of metrics for bar/line visualization
                                chart_df = pd.DataFrame({
                                    "Metric": [c.replace('_', ' ').title() for c in numeric_cols],
                                    "Value": [df[c].iloc[0] for c in numeric_cols]
                                }).set_index("Metric")
                            else:
                                chart_df = df[numeric_cols]

                        if chart_type == "Bar Chart":
                            st.bar_chart(chart_df, use_container_width=True)
                        elif chart_type == "Line Chart":
                            st.line_chart(chart_df, use_container_width=True)
                        elif chart_type == "Area Chart":
                            st.area_chart(chart_df, use_container_width=True)
                    except Exception as chart_err:
                        st.warning(f"Chart display note: {chart_err}")

            st.markdown("### 📋 Result Dataset")
            st.dataframe(df, use_container_width=True)
            
            # CSV Download
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv_data,
                file_name="snowflake_cortex_results.csv",
                mime="text/csv",
                key=f"download_{msg_key_prefix}_{id(msg_dict)}"
            )

        tab_idx += 1


# Render Past Conversation History
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_assistant_response(message, msg_key_prefix=f"hist_{idx}")
        else:
            st.markdown(message["content"])


# Evaluate User Input
chat_input_val = st.chat_input(f"Ask Cortex Agent {agent_name}...")
user_input = chat_input_val or st.session_state.selected_prompt

if user_input:
    st.session_state.selected_prompt = None
    
    # Add User Message to History
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Process Assistant Response
    with st.chat_message("assistant"):
        live_placeholder = st.empty()
        live_placeholder.markdown("""
            <div class="thinking-live-badge">
                💭 <em>Thinking & analyzing Snowflake data...</em>
            </div>
        """, unsafe_allow_html=True)

        res, endpoint_used, req_payload = call_cortex_agent(
            base_url=api_url,
            db=db_name,
            schema=schema_name,
            agent=agent_name,
            prompt=user_input,
            model=model_name
        )

        live_placeholder.empty()

        response_text = res.get("response", "No response returned.")
        sql_query = res.get("sql_query")
        query_data = res.get("data")
        thinking = res.get("thinking")
        debug_info = {"request": req_payload, "response": res, "endpoint": endpoint_used}

        assistant_msg_dict = {
            "role": "assistant",
            "content": response_text,
            "sql": sql_query,
            "data": query_data,
            "thinking": thinking,
            "raw_payload": debug_info
        }

        render_assistant_response(assistant_msg_dict, msg_key_prefix="latest")
        st.session_state.messages.append(assistant_msg_dict)
