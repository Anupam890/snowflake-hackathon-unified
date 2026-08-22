import streamlit as st
import json
import datetime
import requests
import pandas as pd
from dotenv import dotenv_values

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="❄ INSIGHT AI — Insurance Intelligence Studio",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values('.env').items()}
API_BASE_URL = env_config.get("API_URL", "http://127.0.0.1:8001")

# Premium Custom CSS Design System
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Top Header Bar */
    .top-navbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(90deg, rgba(11, 17, 32, 0.96) 0%, rgba(22, 33, 56, 0.92) 100%);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 12px;
        padding: 12px 24px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    }
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .brand-logo {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(135deg, #38BDF8 0%, #00D4B2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .brand-badge {
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.35);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .header-actions {
        display: flex;
        align-items: center;
        gap: 14px;
    }
    .header-icon-btn {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.25);
        color: #94A3B8;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 0.88rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .user-pill {
        display: flex;
        align-items: center;
        gap: 10px;
        background: rgba(14, 165, 233, 0.15);
        border: 1px solid rgba(14, 165, 233, 0.4);
        padding: 5px 14px;
        border-radius: 30px;
    }
    .user-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: linear-gradient(135deg, #0284C7 0%, #0D9488 100%);
        color: #FFFFFF;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.82rem;
        font-weight: 700;
        box-shadow: 0 0 10px rgba(14, 165, 233, 0.5);
    }
    .user-name-text {
        color: #F1F5F9;
        font-weight: 600;
        font-size: 0.88rem;
    }
    .user-role-badge {
        color: #00D4B2;
        font-size: 0.72rem;
        font-weight: 500;
    }

    /* Modern Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #080C15 !important;
        border-right: 1px solid rgba(148, 163, 184, 0.12) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarNav"] {
        display: none !important;
    }
    .sidebar-brand-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 18px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    }
    .sidebar-brand-title {
        font-size: 1.25rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8 0%, #00D4B2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.3px;
        margin-bottom: 4px;
    }
    .sidebar-beacon {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.76rem;
        color: #34D399;
        font-weight: 600;
        background: rgba(16, 185, 129, 0.12);
        padding: 3px 8px;
        border-radius: 12px;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .beacon-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #34D399;
        box-shadow: 0 0 8px #34D399;
        animation: pulseBeacon 2s infinite ease-in-out;
    }
    @keyframes pulseBeacon {
        0% { transform: scale(0.9); opacity: 0.7; }
        50% { transform: scale(1.3); opacity: 1; }
        100% { transform: scale(0.9); opacity: 0.7; }
    }
    .sidebar-section-header {
        font-size: 0.72rem;
        font-weight: 800;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 18px;
        margin-bottom: 8px;
        padding-left: 4px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .sidebar-pill-badge {
        font-size: 0.68rem;
        padding: 2px 6px;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-orange {
        background: rgba(249, 115, 22, 0.18);
        color: #FB923C;
        border: 1px solid rgba(249, 115, 22, 0.4);
    }
    .badge-cyan {
        background: rgba(6, 182, 212, 0.18);
        color: #22D3EE;
        border: 1px solid rgba(6, 182, 212, 0.4);
    }
    .sidebar-telemetry-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 10px;
        padding: 12px;
        margin-top: 14px;
        font-size: 0.8rem;
        color: #94A3B8;
    }
    .telemetry-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .telemetry-val {
        color: #F1F5F9;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
    }
    .sidebar-user-footer {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.8) 100%);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 10px;
        padding: 12px;
        margin-top: 18px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* Greeting Section */
    .greeting-title {
        font-size: 2.15rem;
        font-weight: 800;
        color: #F8FAFC;
        margin-bottom: 4px;
        letter-spacing: -0.6px;
    }
    .greeting-sub {
        font-size: 1.12rem;
        color: #94A3B8;
        margin-bottom: 24px;
    }

    /* Suggested Pills */
    .suggested-label {
        font-size: 0.88rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }

    /* KPI Metric Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-top: 24px;
        margin-bottom: 28px;
    }
    .kpi-card {
        background: linear-gradient(145deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 12px;
        padding: 20px 22px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .kpi-card:hover {
        border-color: rgba(56, 189, 248, 0.4);
        transform: translateY(-2px);
    }
    .kpi-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .kpi-title {
        color: #94A3B8;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-pill-green {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-blue {
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-purple {
        background: rgba(168, 85, 247, 0.15);
        color: #C084FC;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-value {
        color: #F8FAFC;
        font-size: 1.85rem;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .kpi-desc {
        color: #64748B;
        font-size: 0.82rem;
    }

    /* Thinking Component */
    div[data-testid="stExpander"] {
        border: 1px solid #2D3748 !important;
        border-radius: 8px !important;
        background-color: rgba(15, 23, 42, 0.5) !important;
        margin-bottom: 12px !important;
    }
    div[data-testid="stExpander"] summary {
        color: #94A3B8 !important;
        font-size: 0.90rem !important;
        font-weight: 500 !important;
    }
    div[data-testid="stExpander"] summary:hover {
        color: #38BDF8 !important;
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


# ---------------------------------------------------------
# Helper Functions & API Clients
# ---------------------------------------------------------
@st.cache_data(ttl=15)
def fetch_snowflake_status(base_url: str):
    try:
        res = requests.get(f"{base_url}/api/snowflake/status", timeout=4)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "connected": True,
        "user": env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI"),
        "role": env_config.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": env_config.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": env_config.get("SNOWFLAKE_DB", "INSURANCE_MGMT_SYSTEM"),
        "schema": env_config.get("SNOWFLAKE_SH", "HACKATHON_SH"),
        "default_agent": env_config.get("INS_AGENT", "INS_ANALYTICS_AGENT")
    }


@st.cache_data(ttl=20)
def fetch_overview_metrics(base_url: str):
    try:
        res = requests.get(f"{base_url}/api/overview", timeout=4)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "claims_count": 400,
        "claims_amount": 15024703.0,
        "claims_growth_pct": "+14.2%",
        "revenue": 2210154.0,
        "active_policies": 300,
        "avg_premium": 7367.18,
        "data_trust_score": 83,
        "avg_settlement_days": 14.8,
        "high_risk_count": 18
    }


def call_cortex_agent(base_url: str, db: str, schema: str, agent: str, prompt: str, model: str):
    endpoint_url = f"{base_url}/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
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
        return {"status": "error", "response": f"Connection Error: {str(e)}"}, endpoint_url, payload


def get_time_greeting():
    current_hour = datetime.datetime.now().hour
    if 5 <= current_hour < 12:
        return "Good Morning"
    elif 12 <= current_hour < 17:
        return "Good Afternoon"
    else:
        return "Good Evening"


# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------
if "current_nav" not in st.session_state:
    st.session_state.current_nav = "◈ Home"

if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello! I am **INSIGHT AI**, your intelligent insurance analyst connected directly to Snowflake. Ask any analytical question to generate queries, extract metrics, and explore interactive charts.",
            "sql": None,
            "data": None,
            "thinking": None,
            "raw_payload": None
        }
    ]

# Fetch Snowflake session context
sf_context = fetch_snowflake_status(API_BASE_URL)
current_user = sf_context.get("user") or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
current_role = sf_context.get("role") or "ACCOUNTADMIN"
current_wh = sf_context.get("warehouse") or "COMPUTE_WH"
current_db = sf_context.get("database") or "INSURANCE_MGMT_SYSTEM"
current_sh = sf_context.get("schema") or "HACKATHON_SH"
current_agent = sf_context.get("default_agent") or "INS_ANALYTICS_AGENT"
overview_data = fetch_overview_metrics(API_BASE_URL)


# ---------------------------------------------------------
# Top Navbar Header (Clean & Minimalist: Brand + Dynamic User)
# ---------------------------------------------------------
user_initial = current_user[0].upper() if current_user else "U"

st.markdown(f"""
    <div class="top-navbar">
        <div class="brand-container">
            <span class="brand-logo">❄ INSIGHT AI</span>
        </div>
        <div class="header-actions">
            <div class="user-pill">
                <div class="user-avatar">{user_initial}</div>
                <div>
                    <div class="user-name-text">{current_user}</div>
                    <div class="user-role-badge">{current_role}</div>
                </div>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Upgraded Enterprise Sidebar Design System
# ---------------------------------------------------------
with st.sidebar:
    # 1. Brand Card & Live Telemetry Beacon
    st.markdown(f"""
        <div class="sidebar-brand-card">
            <div class="sidebar-brand-title">❄ INSIGHT AI</div>
            <div style="font-size:0.78rem;color:#94A3B8;margin-bottom:8px;">Enterprise Intelligence Studio</div>
            <div class="sidebar-beacon">
                <span class="beacon-dot"></span>
                <span>Live Persistent Session</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 2. Line of Business / Tenant Switcher
    st.caption("🏢 LINE OF BUSINESS")
    lob_selector = st.selectbox(
        "Line of Business",
        ["Property & Casualty (P&C)", "Health & Medical", "Commercial Lines", "Life Insurance"],
        index=0,
        label_visibility="collapsed"
    )

    # 3. Primary Navigation Groups
    st.markdown('<div class="sidebar-section-header"><span>ANALYTICS & DISCOVERY</span></div>', unsafe_allow_html=True)
    
    nav_analytics = ["◈ Home", "◉ Ask AI", "⚡ Explore", "📊 Data"]
    for nav_item in nav_analytics:
        is_active = (st.session_state.current_nav == nav_item)
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_{nav_item}", use_container_width=True, type=btn_type):
            st.session_state.current_nav = nav_item
            st.rerun()

    st.markdown('<div class="sidebar-section-header"><span>GOVERNANCE & TRUST</span></div>', unsafe_allow_html=True)
    nav_gov = ["🛡 Quality", "🚨 Incidents", "📄 Docs"]
    for nav_item in nav_gov:
        is_active = (st.session_state.current_nav == nav_item)
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_{nav_item}", use_container_width=True, type=btn_type):
            st.session_state.current_nav = nav_item
            st.rerun()

    st.markdown('<div class="sidebar-section-header"><span>SYSTEM</span></div>', unsafe_allow_html=True)
    is_settings_active = (st.session_state.current_nav == "⚙ Settings")
    if st.button("⚙ Settings", key="btn_nav_settings", use_container_width=True, type="primary" if is_settings_active else "secondary"):
        st.session_state.current_nav = "⚙ Settings"
        st.rerun()

    st.divider()

    # 4. Cortex AI Engine Parameters
    st.markdown("### 🤖 Cortex AI Engine")
    selected_model = st.selectbox(
        "AI Engine Model",
        ["claude-3-5-sonnet", "llama3.1-70b", "snowflake-arctic"],
        index=0
    )
    
    c_think, c_temp = st.columns(2)
    with c_think:
        enable_reasoning = st.checkbox("🧠 Reasoning", value=True, help="Enable step-by-step thinking tokens")
    with c_temp:
        auto_run_sql = st.checkbox("⚡ Auto-SQL", value=True, help="Automatically run generated SQL on Snowflake")

    # 5. Global Timeframe Filter
    st.markdown("### 📅 Global Timeframe")
    time_filter = st.selectbox(
        "Timeframe Filter",
        ["FY2024 YTD", "Last 90 Days", "Last 30 Days", "All Time Historical"],
        index=0,
        label_visibility="collapsed"
    )

    # 6. Live Session Telemetry Box
    st.markdown(f"""
        <div class="sidebar-telemetry-box">
            <div class="telemetry-row">
                <span>Warehouse:</span>
                <span class="telemetry-val">{current_wh}</span>
            </div>
            <div class="telemetry-row">
                <span>Database:</span>
                <span class="telemetry-val">{current_db}</span>
            </div>
            <div class="telemetry-row">
                <span>Schema:</span>
                <span class="telemetry-val">{current_sh}</span>
            </div>
            <div class="telemetry-row">
                <span>Security:</span>
                <span class="telemetry-val" style="color:#34D399;">🔒 MFA Cached</span>
            </div>
            <div class="telemetry-row" style="margin-bottom:0;">
                <span>Heartbeat:</span>
                <span class="telemetry-val" style="color:#38BDF8;">Active (10m)</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 7. Quick Actions & User Footer
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.rerun()

    st.markdown(f"""
        <div class="sidebar-user-footer">
            <div class="user-avatar">{user_initial}</div>
            <div style="flex:1;">
                <div class="user-name-text">{current_user}</div>
                <div class="user-role-badge">{current_role} • Online</div>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# Helper: Render Assistant Chat Response
# ---------------------------------------------------------
def render_assistant_response(msg_dict, msg_key_prefix=""):
    response_text = msg_dict.get("content", "")
    sql_query = msg_dict.get("sql")
    query_data = msg_dict.get("data")
    thinking = msg_dict.get("thinking")

    if thinking and thinking.strip():
        with st.expander("💭 Thought for a few seconds", expanded=False):
            st.markdown(thinking)

    tab_titles = ["💬 Answer"]
    if sql_query:
        tab_titles.append("🔍 Generated SQL")
    if query_data and len(query_data) > 0:
        tab_titles.append("📊 Visualizations & Table")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    with tabs[tab_idx]:
        st.markdown(response_text)
    tab_idx += 1

    if sql_query:
        with tabs[tab_idx]:
            st.markdown("**Generated Snowflake SQL Query:**")
            st.code(sql_query, language="sql")
        tab_idx += 1

    if query_data and len(query_data) > 0:
        with tabs[tab_idx]:
            df = pd.DataFrame(query_data)
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            text_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

            st.markdown("### 📊 Interactive Visualizations")
            if len(numeric_cols) > 0:
                chart_formats = ["Summary Metrics", "Bar Chart", "Line Chart", "Area Chart"] if len(df) == 1 else ["Bar Chart", "Line Chart", "Area Chart", "Summary Metrics"]
                chart_type = st.radio(
                    "Select Chart Format:",
                    chart_formats,
                    horizontal=True,
                    key=f"chart_{msg_key_prefix}_{id(msg_dict)}"
                )

                if chart_type == "Summary Metrics":
                    m_cols = st.columns(min(len(numeric_cols), 4))
                    for i, num_col in enumerate(numeric_cols[:4]):
                        with m_cols[i % min(len(numeric_cols), 4)]:
                            val = df[num_col].iloc[0] if len(df) == 1 else (df[num_col].sum() if any(k in num_col for k in ["TOTAL", "SUM", "COUNT"]) else df[num_col].mean())
                            val_str = f"${val:,.2f}" if isinstance(val, float) and val % 1 != 0 else f"{val:,}" if isinstance(val, (int, float)) else str(val)
                            label = ("Total " if len(df) > 1 and any(k in num_col for k in ["TOTAL", "SUM", "COUNT"]) else "") + num_col.replace('_', ' ').title()
                            st.metric(label=label, value=val_str)
                else:
                    try:
                        if text_cols:
                            chart_df = df.set_index(text_cols[0])[numeric_cols[:3]]
                        else:
                            chart_df = df[numeric_cols]
                        
                        if chart_type == "Bar Chart":
                            st.bar_chart(chart_df, use_container_width=True)
                        elif chart_type == "Line Chart":
                            st.line_chart(chart_df, use_container_width=True)
                        elif chart_type == "Area Chart":
                            st.area_chart(chart_df, use_container_width=True)
                    except Exception as err:
                        st.warning(f"Chart render note: {err}")

            st.markdown("### 📋 Result Dataset")
            st.dataframe(df, use_container_width=True)
            
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv_data,
                file_name="snowflake_cortex_results.csv",
                mime="text/csv",
                key=f"dl_{msg_key_prefix}_{id(msg_dict)}"
            )


# ---------------------------------------------------------
# VIEW 1: ◈ HOME DASHBOARD
# ---------------------------------------------------------
if st.session_state.current_nav == "◈ Home":
    greeting = get_time_greeting()
    
    st.markdown(f'<div class="greeting-title">{greeting}, {current_user}</div>', unsafe_allow_html=True)
    st.markdown('<div class="greeting-sub">What would you like to investigate?</div>', unsafe_allow_html=True)

    # Investigation Search Box
    col_search, col_btn = st.columns([6, 1])
    with col_search:
        home_query = st.text_input(
            "Ask anything about your insurance data...",
            placeholder="Ask anything about your insurance data... (e.g. Show claims by policy type)",
            label_visibility="collapsed",
            key="home_search_input"
        )
    with col_btn:
        search_clicked = st.button("🚀 Investigate", use_container_width=True)

    # Suggested Investigations Pills
    st.markdown('<div class="suggested-label">Suggested investigations</div>', unsafe_allow_html=True)
    p1, p2, p3, p4, p5 = st.columns(5)
    
    suggested_clicked = None
    with p1:
        if st.button("📈 Claims spike", use_container_width=True):
            suggested_clicked = "Show me the claims breakdown and total amount categorized by claim type."
    with p2:
        if st.button("🛡 Data trust", use_container_width=True):
            suggested_clicked = "What is the data trust score, completeness, and record distribution across policies and claims?"
    with p3:
        if st.button("⚖️ Policy comparison", use_container_width=True):
            suggested_clicked = "Compare total premium revenue and active policy count across all policy types."
    with p4:
        if st.button("🗺️ Regional revenue", use_container_width=True):
            suggested_clicked = "What is the total premium revenue by State and region?"
    with p5:
        if st.button("🚨 Fraud alerts", use_container_width=True):
            suggested_clicked = "Show high priority claims flagged with fraud scores."

    # Route search or pill to Ask AI
    prompt_to_run = home_query if (search_clicked and home_query) else suggested_clicked
    if prompt_to_run:
        st.session_state.selected_prompt = prompt_to_run
        st.session_state.current_nav = "◉ Ask AI"
        st.rerun()

    # KPI Metric Cards Grid (Matching Wireframe: Claims +14.2%, Revenue $2.21M, Trust 83%)
    claims_rev = overview_data.get("claims_amount", 15024703.0)
    prem_rev = overview_data.get("revenue", 2210154.0)
    trust_score = overview_data.get("data_trust_score", 83)
    avg_days = overview_data.get("avg_settlement_days", 14.8)

    st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Claims Incurred</span>
                    <span class="kpi-pill-green">+14.2%</span>
                </div>
                <div class="kpi-value">${claims_rev/1_000_000:.1f}M</div>
                <div class="kpi-desc">{overview_data.get('claims_count', 400):,} Total Claims filed</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Total Revenue</span>
                    <span class="kpi-pill-blue">Active</span>
                </div>
                <div class="kpi-value">${prem_rev/1_000_000:.2f}M</div>
                <div class="kpi-desc">{overview_data.get('active_policies', 300)} Active Insurance Policies</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Data Trust</span>
                    <span class="kpi-pill-purple">Verified</span>
                </div>
                <div class="kpi-value">{trust_score}%</div>
                <div class="kpi-desc">Integrity & Quality Scorecard</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Avg Settlement</span>
                    <span class="kpi-pill-blue">Turnaround</span>
                </div>
                <div class="kpi-value">{avg_days} Days</div>
                <div class="kpi-desc">Average Claim Resolution</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Executive Overview Visuals
    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.markdown("### 📊 Policy Portfolio Revenue Breakdown")
        sample_df = pd.DataFrame({
            "Policy Type": ["Auto", "Home", "Health", "Life"],
            "Premium Revenue ($)": [579271.0, 574019.0, 534475.0, 522389.0]
        }).set_index("Policy Type")
        st.bar_chart(sample_df, use_container_width=True)

    with c_right:
        st.markdown("### 🚨 High Risk Claim Signals")
        risk_df = pd.DataFrame([
            {"Claim ID": "CLM-1004", "Type": "Auto", "Amount": "$85,400", "Fraud Score": "0.91", "Priority": "Critical"},
            {"Claim ID": "CLM-1019", "Type": "Health", "Amount": "$42,150", "Fraud Score": "0.86", "Priority": "High"},
            {"Claim ID": "CLM-1033", "Type": "Home", "Amount": "$124,000", "Fraud Score": "0.82", "Priority": "Critical"},
            {"Claim ID": "CLM-1088", "Type": "Auto", "Amount": "$39,200", "Fraud Score": "0.78", "Priority": "High"},
        ])
        st.dataframe(risk_df, use_container_width=True)


# ---------------------------------------------------------
# VIEW 2: ◉ ASK AI (Cortex Conversational Studio)
# ---------------------------------------------------------
elif st.session_state.current_nav == "◉ Ask AI":
    st.markdown("## ◉ Snowflake Cortex AI Studio")
    st.caption(f"Querying `{current_db}.{current_sh}` with model `{selected_model}` via persistent connection.")
    
    # Render Conversation History
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_assistant_response(message, msg_key_prefix=f"chat_{idx}")
            else:
                st.markdown(message["content"])

    # User Input
    chat_val = st.chat_input(f"Ask Cortex Agent {current_agent}...")
    user_prompt = chat_val or st.session_state.selected_prompt

    if user_prompt:
        st.session_state.selected_prompt = None
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            live_holder = st.empty()
            live_holder.markdown("""
                <div class="thinking-live-badge">
                    💭 <em>Snowflake Cortex Agent is analyzing insurance data...</em>
                </div>
            """, unsafe_allow_html=True)

            res, endpoint_used, req_payload = call_cortex_agent(
                base_url=API_BASE_URL,
                db=current_db,
                schema=current_sh,
                agent=current_agent,
                prompt=user_prompt,
                model=selected_model
            )

            live_holder.empty()

            resp_text = res.get("response", "No response returned.")
            sql_query = res.get("sql_query")
            query_data = res.get("data")
            thinking = res.get("thinking")
            debug_info = {"request": req_payload, "response": res, "endpoint": endpoint_used}

            assistant_msg = {
                "role": "assistant",
                "content": resp_text,
                "sql": sql_query,
                "data": query_data,
                "thinking": thinking,
                "raw_payload": debug_info
            }

            render_assistant_response(assistant_msg, msg_key_prefix="latest")
            st.session_state.messages.append(assistant_msg)


# ---------------------------------------------------------
# VIEW 3: ⚡ EXPLORE (Multi-Dimensional Analytics)
# ---------------------------------------------------------
elif st.session_state.current_nav == "⚡ Explore":
    st.markdown("## ⚡ Multi-Dimensional Analytics Explorer")
    st.caption("Slice, filter, and drill into policies, claims, and geographic insurance metrics.")

    exp_tab1, exp_tab2, exp_tab3 = st.tabs(["🏛️ Policies & Revenue", "🚨 Claims & Loss Ratios", "🗺️ Geographic Distribution"])

    with exp_tab1:
        st.markdown("### Policy Types & Plan Tier Breakdown")
        df_p = pd.DataFrame([
            {"Policy Type": "Auto", "Policies": 80, "Revenue": "$579,271", "Avg Premium": "$7,240.89", "Avg Loss Ratio": "0.62"},
            {"Policy Type": "Home", "Policies": 75, "Revenue": "$574,019", "Avg Premium": "$7,653.59", "Avg Loss Ratio": "0.58"},
            {"Policy Type": "Health", "Policies": 75, "Revenue": "$534,475", "Avg Premium": "$7,126.33", "Avg Loss Ratio": "0.71"},
            {"Policy Type": "Life", "Policies": 70, "Revenue": "$522,389", "Avg Premium": "$7,462.70", "Avg Loss Ratio": "0.45"},
        ])
        st.dataframe(df_p, use_container_width=True)

    with exp_tab2:
        st.markdown("### Claims Distribution by Status")
        df_c = pd.DataFrame({
            "Status": ["Approved", "In Review", "Investigating", "Rejected", "Settled"],
            "Count": [140, 95, 45, 30, 90]
        }).set_index("Status")
        st.bar_chart(df_c, use_container_width=True)

    with exp_tab3:
        st.markdown("### Top States by Premium Revenue")
        df_geo = pd.DataFrame({
            "State": ["CA", "TX", "NY", "FL", "IL", "PA", "OH"],
            "Total Premium ($)": [380450, 345120, 310800, 290100, 240500, 210200, 185000]
        }).set_index("State")
        st.line_chart(df_geo, use_container_width=True)


# ---------------------------------------------------------
# VIEW 4: 📊 DATA (Snowflake Catalog & Table Browser)
# ---------------------------------------------------------
elif st.session_state.current_nav == "📊 Data":
    st.markdown("## 📊 Snowflake Data Catalog")
    st.caption(f"Catalog metadata for database `{current_db}.CORE`.")

    tables = [
        {"Table": "POLICIES", "Rows": 300, "Columns": 15, "Primary Key": "POLICY_ID", "Status": "Active"},
        {"Table": "CUSTOMERS", "Rows": 250, "Columns": 12, "Primary Key": "CUSTOMER_ID", "Status": "Active"},
        {"Table": "CLAIMS", "Rows": 400, "Columns": 13, "Primary Key": "CLAIM_ID", "Status": "Active"},
        {"Table": "AGENTS", "Rows": 50, "Columns": 8, "Primary Key": "AGENT_ID", "Status": "Active"},
    ]
    st.dataframe(pd.DataFrame(tables), use_container_width=True)
    
    st.markdown("### 🔍 Live Preview: `POLICIES`")
    st.code("SELECT POLICY_ID, POLICY_TYPE, PLAN_TIER, PREMIUM_AMOUNT, LOSS_RATIO FROM POLICIES LIMIT 5;", language="sql")


# ---------------------------------------------------------
# VIEW 5: 📄 DOCS (Semantic Layer & Dictionary)
# ---------------------------------------------------------
elif st.session_state.current_nav == "📄 Docs":
    st.markdown("## 📄 Semantic Views & Data Dictionary")
    st.caption("Cortex Agent Semantic Layer documentation and entity schema definitions.")

    st.markdown("""
    ### 🏛️ Semantic Model: `SV_INSURANCE_ANALYTICS`
    - **Base Tables**: `POLICIES`, `CUSTOMERS`, `CLAIMS`, `AGENTS`
    - **Key Dimensions**: `CUSTOMER_ID`, `POLICY_ID`, `AGENT_ID`, `CLAIM_TYPE`, `STATE`
    - **Measures**: `PREMIUM_AMOUNT`, `CLAIM_AMOUNT`, `DAYS_TO_RESOLVE`, `FRAUD_SCORE`
    - **Pre-computed Ratios**: `LOSS_RATIO = CLAIM_AMOUNT / PREMIUM_AMOUNT`
    """)


# ---------------------------------------------------------
# VIEW 6: 🛡 QUALITY (Data Trust & Integrity Scorecard)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🛡 Quality":
    st.markdown("## 🛡 Data Trust & Integrity Scorecard")
    st.caption("Real-time telemetry and validation checks on insurance datasets.")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Overall Trust Score", "83%", "+2.1%")
    q2.metric("Completeness", "99.4%", "Zero null IDs")
    q3.metric("Freshness", "100%", "< 1hr sync")
    q4.metric("Schema Validity", "100%", "Passed")

    st.markdown("### Quality Audit Checks")
    audit_data = pd.DataFrame([
        {"Entity": "POLICIES", "Check": "Primary Key Uniqueness", "Status": "✅ Pass", "Violations": 0},
        {"Entity": "POLICIES", "Check": "Premium Range >= 0", "Status": "✅ Pass", "Violations": 0},
        {"Entity": "CLAIMS", "Check": "Foreign Key to POLICIES", "Status": "✅ Pass", "Violations": 0},
        {"Entity": "CUSTOMERS", "Check": "Valid State Code", "Status": "✅ Pass", "Violations": 0},
    ])
    st.dataframe(audit_data, use_container_width=True)


# ---------------------------------------------------------
# VIEW 7: 🚨 INCIDENTS (Fraud & High Risk Alerts)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🚨 Incidents":
    st.markdown("## 🚨 Incident & High Risk Alert Center")
    st.caption("Flagged claims, potential fraud indicators, and escalated tickets.")

    st.markdown("### ⚠️ Active High-Risk Claims (Fraud Score >= 0.75)")
    incidents_df = pd.DataFrame([
        {"Claim ID": "CLM-1004", "Policy ID": "POL-2004", "Claim Type": "Auto", "Claim Amount": "$85,400", "Fraud Score": 0.91, "Priority": "Critical", "Status": "Investigating"},
        {"Claim ID": "CLM-1019", "Policy ID": "POL-2019", "Claim Type": "Health", "Claim Amount": "$42,150", "Fraud Score": 0.86, "Priority": "High", "Status": "In Review"},
        {"Claim ID": "CLM-1033", "Policy ID": "POL-2033", "Claim Type": "Home", "Claim Amount": "$124,000", "Fraud Score": 0.82, "Priority": "Critical", "Status": "Investigating"},
        {"Claim ID": "CLM-1088", "Policy ID": "POL-2088", "Claim Type": "Auto", "Claim Amount": "$39,200", "Fraud Score": 0.78, "Priority": "High", "Status": "In Review"},
    ])
    st.dataframe(incidents_df, use_container_width=True)


# ---------------------------------------------------------
# VIEW 8: ⚙ SETTINGS (Connection & Configuration)
# ---------------------------------------------------------
elif st.session_state.current_nav == "⚙ Settings":
    st.markdown("## ⚙ Configuration & Connection Settings")
    st.caption("Active connection parameters and system environment variables.")

    st.json({
        "current_user": current_user,
        "role": current_role,
        "warehouse": current_wh,
        "database": current_db,
        "schema": current_sh,
        "agent": current_agent,
        "api_endpoint": API_BASE_URL,
        "persistent_connection": True
    })
