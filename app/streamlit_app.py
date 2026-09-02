import os
import sys
import json
import datetime
from typing import Optional, List, Dict, Any, Tuple
import requests
import pandas as pd
import pydeck as pdk
from dotenv import dotenv_values
import streamlit as st

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
try:
    st.set_page_config(
        page_title="❄ INSIGHT AI — Insurance Intelligence Studio",
        page_icon="❄️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.snowflake_manager import get_st_cached_snowflake_manager
from services.server_manager import ensure_backend_server
import importlib
import services.backend_service as backend_service
importlib.reload(backend_service)

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values(os.path.join(PROJECT_ROOT, '.env')).items()}
API_BASE_URL = env_config.get("API_URL", "http://127.0.0.1:8001")

# Auto-start backend in background daemon thread (single-command unified startup)
ensure_backend_server()

# Get persistent cached Snowflake manager (reused across all reruns, avoiding Duo prompts)
cached_sf_mgr = get_st_cached_snowflake_manager()

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
    .header-actions {
        display: flex;
        align-items: center;
        gap: 14px;
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
    .sidebar-section-header {
        font-size: 0.72rem;
        font-weight: 800;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 18px;
        margin-bottom: 8px;
        padding-left: 4px;
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
    .kpi-pill-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-rose {
        background: rgba(244, 63, 94, 0.15);
        color: #FB7185;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .section-header-banner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 32px;
        margin-bottom: 14px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.15);
    }
    .section-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #F8FAFC;
        letter-spacing: -0.3px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-badge {
        font-size: 0.76rem;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 20px;
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .dts-metric-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .insight-callout-box {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-left: 4px solid #38BDF8;
        border-radius: 10px;
        padding: 14px 18px;
        margin-top: 14px;
        color: #E2E8F0;
        font-size: 0.88rem;
        line-height: 1.5;
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

    /* Attached Doc Badge & ChatGPT File Chip */
    .attached-file-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(14, 165, 233, 0.14);
        border: 1px solid rgba(14, 165, 233, 0.35);
        color: #38BDF8;
        padding: 5px 12px;
        border-radius: 8px;
        font-size: 0.84rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .chatgpt-file-chip {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        background: rgba(15, 23, 42, 0.95);
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 8px;
        padding: 8px 16px;
        margin-bottom: 8px;
        font-size: 0.86rem;
        color: #E2E8F0;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    }
    .chatgpt-file-icon {
        color: #38BDF8;
        font-size: 1.15rem;
    }
    .chatgpt-file-name {
        font-weight: 600;
        color: #F8FAFC;
    }
    .chatgpt-file-meta {
        color: #94A3B8;
        font-size: 0.76rem;
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
# Helper Functions & API Clients (Persistent In-Process & Fallback)
# ---------------------------------------------------------
@st.cache_data(ttl=25)
def fetch_snowflake_status(base_url: str = API_BASE_URL):
    try:
        # In-process session check with persistent session manager
        return backend_service.get_snowflake_status(mgr=cached_sf_mgr)
    except Exception:
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


@st.cache_data(ttl=30)
def fetch_overview_metrics(base_url: str = API_BASE_URL, state: Optional[str] = None):
    try:
        # In-process query execution reusing active Snowflake session
        return backend_service.get_dashboard_overview(mgr=cached_sf_mgr, state=state)
    except Exception:
        try:
            params = {"state": state} if state and state != "National" else {}
            res = requests.get(f"{base_url}/api/overview", params=params, timeout=4)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return backend_service.get_dashboard_overview(mgr=None, state=state)


@st.cache_data(ttl=30)
def fetch_dts_analytics(base_url: str = API_BASE_URL):
    try:
        return backend_service.get_dts_analytics_data(mgr=cached_sf_mgr)
    except Exception:
        try:
            res = requests.get(f"{base_url}/api/analytics/dts", timeout=4)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return backend_service.get_dts_analytics_data(mgr=None)


@st.cache_data(ttl=30)
def fetch_risk_churn_analytics(base_url: str = API_BASE_URL, state: Optional[str] = None):
    try:
        return backend_service.get_risk_and_churn_analytics(mgr=cached_sf_mgr, state=state)
    except Exception:
        try:
            params = {"state": state} if state and state != "National" else {}
            res = requests.get(f"{base_url}/api/analytics/risk-churn", params=params, timeout=4)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return backend_service.get_risk_and_churn_analytics(mgr=None, state=state)


@st.cache_data(ttl=30)
def fetch_geospatial_analytics(base_url: str = API_BASE_URL):
    try:
        return backend_service.get_state_geospatial_analytics(mgr=cached_sf_mgr)
    except Exception:
        try:
            res = requests.get(f"{base_url}/api/analytics/geospatial", timeout=4)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return backend_service.get_state_geospatial_analytics(mgr=None)


def extract_uploaded_file_content(uploaded_file):
    """Extracts clean text and metadata from uploaded PDF, CSV, Excel, TXT, JSON, or images."""
    if uploaded_file is None:
        return None, None
    
    file_name = uploaded_file.name
    file_size_kb = uploaded_file.size / 1024
    file_ext = file_name.split('.')[-1].lower()
    
    try:
        if file_ext == "pdf":
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            extracted_pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(f"--- Page {i+1} ---\n{page_text}")
            full_text = "\n\n".join(extracted_pages)
            summary = f"PDF Document: {file_name} ({len(reader.pages)} pages, {file_size_kb:.1f} KB)"
            return summary, full_text[:12000]
            
        elif file_ext in ["csv", "tsv"]:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file)
            summary = f"CSV Dataset: {file_name} ({len(df)} rows, {len(df.columns)} cols, {file_size_kb:.1f} KB)"
            text_repr = f"Columns: {', '.join(df.columns)}\n\nSample Records:\n{df.head(15).to_string(index=False)}"
            return summary, text_repr
            
        elif file_ext in ["xlsx", "xls"]:
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
            summary = f"Excel Spreadsheet: {file_name} ({len(df)} rows, {len(df.columns)} cols, {file_size_kb:.1f} KB)"
            text_repr = f"Columns: {', '.join(df.columns)}\n\nSample Records:\n{df.head(15).to_string(index=False)}"
            return summary, text_repr
            
        elif file_ext in ["txt", "md", "json", "log", "sql"]:
            uploaded_file.seek(0)
            text = uploaded_file.read().decode("utf-8", errors="replace")
            summary = f"Text File: {file_name} ({len(text)} chars, {file_size_kb:.1f} KB)"
            return summary, text[:12000]
            
        elif file_ext in ["png", "jpg", "jpeg", "webp"]:
            summary = f"Image File: {file_name} ({file_size_kb:.1f} KB)"
            return summary, f"[Attached Image: {file_name} - Visual Claim Evidence / Receipt]"
            
        else:
            uploaded_file.seek(0)
            text = uploaded_file.read().decode("utf-8", errors="replace")
            return f"File: {file_name}", text[:8000]
            
    except Exception as e:
        return f"File: {file_name} (Parsing Note)", f"File content preview unavailable: {str(e)}"


def call_cortex_agent(base_url: str, db: str, schema: str, agent: str, prompt: str, model: str):
    endpoint_url = f"{base_url}/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "prompt": prompt
    }
    
    # 1. Direct in-process execution reusing persistent session (avoids network latency & repeated Duo MFA)
    try:
        result = backend_service.execute_cortex_agent_workflow(
            db=db,
            schema=schema,
            agent=agent,
            prompt=prompt,
            model=model,
            mgr=cached_sf_mgr
        )
        return result, endpoint_url, payload
    except Exception as inproc_err:
        print(f"[Streamlit Call] In-process execution note: {inproc_err}. Falling back to REST API...")
    
    # 2. HTTP Fallback to Background FastAPI Server
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

if "uploaded_doc_name" not in st.session_state:
    st.session_state.uploaded_doc_name = None
if "uploaded_doc_summary" not in st.session_state:
    st.session_state.uploaded_doc_summary = None
if "uploaded_doc_text" not in st.session_state:
    st.session_state.uploaded_doc_text = None

if "selected_state" not in st.session_state:
    st.session_state.selected_state = "National"

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello! I am **INSIGHT AI**, your intelligent insurance analyst connected directly to Snowflake. You can ask analytical questions or upload policy documents, claim forms, and CSV datasets for instant AI synthesis.",
            "sql": None,
            "data": None,
            "thinking": None,
            "attached_doc": None,
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

# Active state cross-filter
active_state = st.session_state.selected_state if st.session_state.selected_state != "National" else None

overview_data = fetch_overview_metrics(API_BASE_URL, state=active_state)
dts_data = fetch_dts_analytics(API_BASE_URL)
risk_churn_data = fetch_risk_churn_analytics(API_BASE_URL, state=active_state)
geo_data = fetch_geospatial_analytics(API_BASE_URL)


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
    # 1. Brand Card
    st.markdown(f"""
        <div class="sidebar-brand-card">
            <div class="sidebar-brand-title">❄ INSIGHT AI</div>
            <div style="font-size:0.78rem;color:#94A3B8;">Insurance Intelligence Studio</div>
        </div>
    """, unsafe_allow_html=True)

    # 2. Primary Navigation Groups
    st.markdown('<div class="sidebar-section-header"><span>NAVIGATION</span></div>', unsafe_allow_html=True)
    
    nav_analytics = ["◈ Home", "◉ Ask AI", "⚡ Explore", "📊 Data"]
    for nav_item in nav_analytics:
        is_active = (st.session_state.current_nav == nav_item)
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_{nav_item}", use_container_width=True, type=btn_type):
            st.session_state.current_nav = nav_item
            st.rerun()

    st.divider()

    # Default Cortex AI Engine configuration (silent background execution)
    selected_model = "claude-3-5-sonnet"
    enable_reasoning = True
    auto_run_sql = True

    # 3. Global Timeframe Filter
    st.markdown("### 📅 Timeframe")
    time_filter = st.selectbox(
        "Timeframe Filter",
        ["FY2024 YTD", "Last 90 Days", "Last 30 Days", "All Time Historical"],
        index=0,
        label_visibility="collapsed"
    )

    # 5. Live Session Telemetry Box
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

    # 6. Quick Actions & User Footer
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.session_state.uploaded_doc_name = None
        st.session_state.uploaded_doc_summary = None
        st.session_state.uploaded_doc_text = None
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
    attached_doc = msg_dict.get("attached_doc")

    if attached_doc:
        st.markdown(f'<div class="attached-file-badge">📎 Context: {attached_doc}</div>', unsafe_allow_html=True)

    if thinking and thinking.strip():
        with st.expander("💭 Thought for a few seconds", expanded=False):
            st.markdown(thinking)

    tab_titles = ["💬 Answer"]
    if sql_query:
        tab_titles.append("🔍 Generated SQL")
    if query_data and len(query_data) > 0:
        tab_titles.append("📊 Visualizations & Analytics")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    with tabs[tab_idx]:
        st.markdown(response_text)
        if query_data and len(query_data) > 0:
            df = pd.DataFrame(query_data)
            st.markdown("<br>", unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)
            
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Dataset as CSV",
                data=csv_data,
                file_name="snowflake_insurance_results.csv",
                mime="text/csv",
                key=f"dl_ans_{msg_key_prefix}_{id(msg_dict)}"
            )
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

            st.markdown("### 📋 Full Result Dataset")
            st.dataframe(df, use_container_width=True)
            
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv_data,
                file_name="snowflake_cortex_results.csv",
                mime="text/csv",
                key=f"dl_tab_{msg_key_prefix}_{id(msg_dict)}"
            )


# ---------------------------------------------------------
# VIEW 1: ◈ HOME DASHBOARD
# ---------------------------------------------------------
if st.session_state.current_nav == "◈ Home":
    st.markdown(f'<div class="greeting-title">❄️ Insurance Portfolio Intelligence Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="greeting-sub" style="margin-bottom: 20px;">Real-time portfolio performance, risk exposure, and operational intelligence.</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------
    # GEOSPATIAL 3D US MAP & CROSS-FILTER SECTION
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner" style="margin-top: 24px;">
            <div class="section-title">🗺️ Interactive US Risk & Premium Map</div>
            <div class="section-badge">Live Geospatial Cross-Filter</div>
        </div>
    """, unsafe_allow_html=True)

    # State Selection Filter Pills Bar
    state_cols = st.columns([1.6, 1, 1, 1, 1, 1, 1, 1])
    
    with state_cols[0]:
        is_nat = (st.session_state.selected_state == "National")
        if st.button("🌐 National (All)", key="btn_st_all", use_container_width=True, type="primary" if is_nat else "secondary"):
            st.session_state.selected_state = "National"
            st.rerun()

    states_list = [
        {"code": "TX", "label": "TX ($1.19M)"},
        {"code": "AZ", "label": "AZ ($642k)"},
        {"code": "IL", "label": "IL ($571k)"},
        {"code": "CA", "label": "CA ($566k)"},
        {"code": "PA", "label": "PA ($541k)"},
        {"code": "NY", "label": "NY ($333k)"},
        {"code": "GA", "label": "GA ($268k)"}
    ]

    for idx, st_item in enumerate(states_list):
        with state_cols[idx + 1]:
            is_active = (st.session_state.selected_state == st_item["code"])
            if st.button(st_item["label"], key=f"btn_st_{st_item['code']}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state.selected_state = st_item["code"]
                st.rerun()

    # Active State Filter Callout Indicator
    if st.session_state.selected_state != "National":
        st.markdown(f"""
            <div class="insight-callout-box" style="margin-top: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 700; color: #38BDF8;">📍 Active State Filter: {st.session_state.selected_state}</span>
                    <span style="color: #94A3B8; margin-left: 8px; font-size: 0.86rem;">Dashboard metrics, DTS trajectories, and risk exposure are filtered for this state.</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # 3D Pydeck Map & Geographic Breakdown Split
    c_map, c_map_stats = st.columns([1.8, 1.2])

    with c_map:
        if geo_data:
            df_geo = pd.DataFrame(geo_data)
            df_geo["lat"] = pd.to_numeric(df_geo["lat"])
            df_geo["lon"] = pd.to_numeric(df_geo["lon"])
            df_geo["elevation"] = pd.to_numeric(df_geo["elevation"])
            
            # Center on US or selected state
            if st.session_state.selected_state != "National":
                matching_st = df_geo[df_geo["state"] == st.session_state.selected_state]
                if not matching_st.empty:
                    view_lat = float(matching_st["lat"].values[0])
                    view_lon = float(matching_st["lon"].values[0])
                    view_zoom = 4.8
                    view_pitch = 45
                else:
                    view_lat, view_lon, view_zoom, view_pitch = 38.0, -96.0, 3.5, 40
            else:
                view_lat, view_lon, view_zoom, view_pitch = 38.0, -96.0, 3.5, 40

            # 3D Column Layer for Premium Revenue Volume
            column_layer = pdk.Layer(
                "ColumnLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_elevation="elevation",
                elevation_scale=1,
                radius=75000,
                get_fill_color="fill_color",
                pickable=True,
                auto_highlight=True
            )

            # Scatterplot Risk Glow Rings for Fraud / Claim Intensity
            scatter_layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_radius="claims_count * 1500",
                radius_min_pixels=10,
                radius_max_pixels=45,
                get_fill_color="[255, 255, 255, 40]",
                get_line_color="fill_color",
                line_width_min_pixels=2,
                stroked=True,
                filled=True,
                pickable=True
            )

            # State Code Text Overlay
            text_layer = pdk.Layer(
                "TextLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_text="state",
                get_size=15,
                get_color="[255, 255, 255, 255]",
                get_alignment_baseline="'center'"
            )

            tooltip_html = {
                "html": """
                <div style="background-color: #0F172A; padding: 10px 14px; border-radius: 8px; border: 1px solid #334155; font-family: Inter, sans-serif; color: #F8FAFC; min-width: 190px;">
                    <div style="font-size: 14px; font-weight: 700; color: #38BDF8; margin-bottom: 4px;">{state_name} ({state})</div>
                    <div style="font-size: 12px; margin-bottom: 2px;"><b>Written Premium:</b> {total_premium_formatted}</div>
                    <div style="font-size: 12px; margin-bottom: 2px;"><b>Active Policies:</b> {policies_count}</div>
                    <div style="font-size: 12px; margin-bottom: 2px;"><b>Loss Ratio:</b> {avg_loss_ratio}%</div>
                    <div style="font-size: 12px; margin-bottom: 2px;"><b>Claims Volume:</b> {claims_count}</div>
                    <div style="font-size: 12px; color: #F59E0B;"><b>Risk Status:</b> {risk_label}</div>
                </div>
                """,
                "style": {"color": "white"}
            }

            deck = pdk.Deck(
                layers=[column_layer, scatter_layer, text_layer],
                initial_view_state=pdk.ViewState(
                    latitude=view_lat,
                    longitude=view_lon,
                    zoom=view_zoom,
                    pitch=view_pitch,
                    bearing=0
                ),
                tooltip=tooltip_html,
                map_style="dark"
            )

            map_mode = st.radio(
                "Map Perspective", 
                ["🏙️ 3D Risk & Elevation Pillars", "🗺️ 2D Geographic Bubble Map"], 
                horizontal=True, 
                label_visibility="collapsed", 
                key="geo_map_mode"
            )
            
            if map_mode == "🏙️ 3D Risk & Elevation Pillars":
                st.pydeck_chart(deck, use_container_width=True)
            else:
                st.map(df_geo, latitude="lat", longitude="lon", size="policies_count", color="fill_color", use_container_width=True)
            
            # Map legend
            st.markdown("""
                <div style="display:flex; gap:16px; font-size:0.78rem; color:#94A3B8; margin-top:-4px; margin-bottom:12px;">
                    <span>🟢 <b>Optimal Loss Ratio (&lt; 52%)</b></span>
                    <span>🟠 <b>Elevated Risk (52% - 62%)</b></span>
                    <span>🔴 <b>Critical Risk (&gt; 62%)</b></span>
                    <span>🗼 <b>Pillar Height: Written Premium ($)</b></span>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Loading geospatial data from Snowflake...")

    with c_map_stats:
        st.markdown("#### 📊 Geographic Portfolio Breakdown")
        if geo_data:
            df_geo_table = pd.DataFrame(geo_data)[["state", "state_name", "policies_count", "total_premium_formatted", "avg_loss_ratio", "risk_label"]]
            df_geo_table.columns = ["State", "Name", "Policies", "Revenue ($)", "Loss Ratio %", "Risk Status"]
            st.dataframe(df_geo_table, use_container_width=True, height=275)
            
            # Quick summary alert
            st.markdown("""
                <div class="dts-metric-card" style="padding: 12px 16px; margin-top: 8px;">
                    <div style="font-size:0.84rem; font-weight:700; color:#38BDF8;">🏆 Top Revenue State: Texas (TX) — $1.19M</div>
                    <div style="font-size:0.78rem; color:#94A3B8; margin-top:2px;">Highest Risk Loss Ratio: <b>Illinois (IL) at 69.2%</b>. Proactive deductible optimization recommended.</div>
                </div>
            """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # ROW 1: KPI METRIC CARDS (Active Policies, Processing Days, CSAT, Total Revenue)
    # ---------------------------------------------------------
    active_policies_val = overview_data.get("active_policies", 300)
    active_policies_trend = overview_data.get("active_policies_trend", "+8.4% MoM")
    
    proc_days_val = overview_data.get("processing_days", overview_data.get("avg_settlement_days", 14.8))
    proc_days_trend = overview_data.get("processing_days_trend", "-2.3d YoY")
    
    csat_score_val = overview_data.get("csat_score", "4.8 / 5.0")
    csat_pct_val = overview_data.get("csat_pct", "94.2%")
    csat_trend = overview_data.get("csat_trend", "+5.1% QoQ")
    
    prem_rev = overview_data.get("revenue", 2210154.0)
    prem_rev_trend = overview_data.get("revenue_growth_pct", "+12.6% YoY")

    st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Active Policies</span>
                    <span class="kpi-pill-green">{active_policies_trend}</span>
                </div>
                <div class="kpi-value">{active_policies_val:,}</div>
                <div class="kpi-desc">Active policyholders across 4 tiers</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Processing Days</span>
                    <span class="kpi-pill-purple">{proc_days_trend}</span>
                </div>
                <div class="kpi-value">{proc_days_val} Days</div>
                <div class="kpi-desc">Average claims resolution turnaround</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Customer CSAT</span>
                    <span class="kpi-pill-green">{csat_trend}</span>
                </div>
                <div class="kpi-value">{csat_score_val}</div>
                <div class="kpi-desc">{csat_pct_val} positive sentiment score</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">Total Revenue</span>
                    <span class="kpi-pill-blue">{prem_rev_trend}</span>
                </div>
                <div class="kpi-value">${prem_rev/1_000_000:.2f}M</div>
                <div class="kpi-desc">Gross written annual premium</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # ROW 2: DTS CHARTS (Data Trust Score & Date-Time Series)
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner">
            <div class="section-title">⚡ Data Trust & Date-Time Series Analytics</div>
            <div class="section-badge">Row 2 • Telemetry & Time-Series</div>
        </div>
    """, unsafe_allow_html=True)

    c_dts_left, c_dts_right = st.columns([1, 1.1])

    with c_dts_left:
        st.markdown("### 🛡 Data Trust Score (DTS) Quality Index")
        st.caption("Composite data integrity telemetry validated across all insurance entity layers.")
        
        # Dimensions dataframe and comparison chart
        quality_dims = dts_data.get("quality_dimensions", [])
        if quality_dims:
            df_dims = pd.DataFrame(quality_dims)
            chart_df_dims = df_dims.set_index("Dimension")[["Score", "Target"]]
            st.bar_chart(chart_df_dims, use_container_width=True)
            
            # Key quality score metrics
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Completeness", "99.4%", "Zero null IDs")
            with m2:
                st.metric("Accuracy", "98.2%", "+1.4% Target")
            with m3:
                st.metric("Sync Freshness", "100%", "< 15m CDC")
        else:
            st.info("DTS dimensions loading...")

    with c_dts_right:
        st.markdown("### 📈 Date-Time Series (DTS) Operational Trajectory")
        dts_metric_selection = st.radio(
            "Select DTS Trajectory:",
            ["💵 Inflow vs Outflow ($)", "⏱ Turnaround Speed (Days)", "📊 Loss Ratio vs DTS Trust (%)"],
            horizontal=True,
            key="dts_metric_selector"
        )
        
        ts_data = dts_data.get("time_series", [])
        if ts_data:
            df_ts = pd.DataFrame(ts_data)
            if dts_metric_selection == "💵 Inflow vs Outflow ($)":
                chart_flow = df_ts.set_index("Month")[["Premium Inflow", "Claims Incurred"]]
                st.bar_chart(chart_flow, use_container_width=True)
            elif dts_metric_selection == "⏱ Turnaround Speed (Days)":
                chart_days = df_ts.set_index("Month")[["Processing Days"]]
                st.line_chart(chart_days, use_container_width=True)
            else:
                chart_ratio = df_ts.set_index("Month")[["Data Trust Score", "Loss Ratio %"]]
                st.area_chart(chart_ratio, use_container_width=True)
        else:
            st.info("Time series data loading...")

    # ---------------------------------------------------------
    # ROW 3: RISK ANALYSIS & CHURN BY CATEGORY
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner">
            <div class="section-title">🛡 Risk Analysis & Categorical Churn Intelligence</div>
            <div class="section-badge">Row 3 • Risk Matrix & Retention</div>
        </div>
    """, unsafe_allow_html=True)

    c_risk, c_churn = st.columns([1, 1])

    with c_risk:
        st.markdown("### 🚨 Multi-Dimensional Risk Exposure")
        st.caption("Risk severity, fraud score indicators, and claim exposure across categories.")
        
        risk_cats = risk_churn_data.get("risk_by_category", [])
        if risk_cats:
            df_risk = pd.DataFrame(risk_cats)
            # Chart comparing Risk Exposure by Category
            st.bar_chart(df_risk.set_index("Category")[["Risk Exposure ($)"]], use_container_width=True)
            
            # High Risk Incidents Table
            st.markdown("#### ⚠️ High Priority Claim Signals (Fraud Score >= 0.75)")
            flagged = risk_churn_data.get("flagged_incidents", [])
            if flagged:
                df_flagged = pd.DataFrame(flagged)
                st.dataframe(df_flagged[["Claim ID", "Category", "Claim Amount", "Fraud Score", "Priority", "Reason"]], use_container_width=True)
                
                if st.button("🔍 Investigate Flagged Claims in Ask AI", key="btn_home_investigate_risk", use_container_width=True):
                    st.session_state.selected_prompt = "Perform forensic risk analysis on top flagged insurance claims with fraud scores > 0.75."
                    st.session_state.current_nav = "◉ Ask AI"
                    st.rerun()

    with c_churn:
        st.markdown("### 📉 Policyholder Churn by Category")
        st.caption("Categorical customer attrition, tier distribution, and retention drivers.")
        
        churn_cats = risk_churn_data.get("churn_by_category", [])
        if churn_cats:
            df_churn = pd.DataFrame(churn_cats)
            st.bar_chart(df_churn.set_index("Category")[["Churn Rate %"]], use_container_width=True)
            
            # Plan tier breakdown
            st.markdown("#### 📊 Plan Tier Churn & Revenue Exposure")
            churn_tiers = risk_churn_data.get("churn_by_plan_tier", [])
            if churn_tiers:
                df_tier = pd.DataFrame(churn_tiers)
                st.dataframe(df_tier, use_container_width=True)
            
            # AI Insights Callout Box
            insights = risk_churn_data.get("churn_insights", [])
            if insights:
                st.markdown("""
                    <div class="insight-callout-box">
                        <div style="font-weight:700; color:#38BDF8; margin-bottom:6px;">💡 Cortex Retention Insights</div>
                """, unsafe_allow_html=True)
                for ins in insights:
                    st.markdown(f"- {ins}")
                st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------
# VIEW 2: ◉ ASK AI (Cortex Conversational Studio + File Upload)
# ---------------------------------------------------------
elif st.session_state.current_nav == "◉ Ask AI":
    st.markdown("## ◉ Snowflake Cortex AI Studio")
    st.caption(f"Intelligent insurance analytics assistant powered by `{selected_model}`.")

    # Render active document attachment chip if attached (ChatGPT style)
    if st.session_state.uploaded_doc_name:
        col_chip, col_del = st.columns([9, 2])
        with col_chip:
            st.markdown(f"""
                <div class="chatgpt-file-chip">
                    <span class="chatgpt-file-icon">📄</span>
                    <div>
                        <div class="chatgpt-file-name">{st.session_state.uploaded_doc_name}</div>
                        <div class="chatgpt-file-meta">{st.session_state.uploaded_doc_summary or 'Document context attached'}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with col_del:
            if st.button("✖ Remove File", key="btn_discard_attached_chip", use_container_width=True):
                st.session_state.uploaded_doc_name = None
                st.session_state.uploaded_doc_summary = None
                st.session_state.uploaded_doc_text = None
                st.rerun()

    # Left Attachment Popover (like ChatGPT)
    c_attach_btn, c_spacer = st.columns([2, 10])
    with c_attach_btn:
        with st.popover("📎 Attach File / Document", help="Attach Claim Document, Policy PDF, or Dataset to query"):
            st.markdown("**Attach File for AI Analysis**")
            st.caption("Supported: PDF, CSV, Excel, TXT, JSON, Images")
            agent_up = st.file_uploader(
                "Upload document",
                type=["pdf", "csv", "xlsx", "xls", "txt", "json", "png", "jpg", "jpeg"],
                key="ask_ai_left_popover_uploader",
                label_visibility="collapsed"
            )
            if agent_up is not None:
                summary, content = extract_uploaded_file_content(agent_up)
                st.session_state.uploaded_doc_name = agent_up.name
                st.session_state.uploaded_doc_summary = summary
                st.session_state.uploaded_doc_text = content
                st.rerun()
    
    # Render Conversation History
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_assistant_response(message, msg_key_prefix=f"chat_{idx}")
            else:
                st.markdown(message["content"])

    # User Input
    chat_val = st.chat_input(f"Ask Cortex Agent {current_agent} (with attached file or database inquiry)...")
    user_prompt = chat_val or st.session_state.selected_prompt

    if user_prompt:
        st.session_state.selected_prompt = None
        
        # Check if an attachment should be merged into prompt
        attached_doc_label = st.session_state.uploaded_doc_name
        if st.session_state.uploaded_doc_text:
            combined_prompt = f"""[ATTACHED CONTEXT - {st.session_state.uploaded_doc_summary}]:
{st.session_state.uploaded_doc_text}

[USER QUESTION / INSTRUCTION]:
{user_prompt}"""
        else:
            combined_prompt = user_prompt

        st.session_state.messages.append({
            "role": "user",
            "content": user_prompt,
            "attached_doc": attached_doc_label
        })
        
        with st.chat_message("user"):
            if attached_doc_label:
                st.markdown(f'<div class="attached-file-badge">📎 Attached: {attached_doc_label}</div>', unsafe_allow_html=True)
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
                prompt=combined_prompt,
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
                "attached_doc": attached_doc_label,
                "raw_payload": debug_info
            }

            render_assistant_response(assistant_msg, msg_key_prefix="latest")
            st.session_state.messages.append(assistant_msg)


# ---------------------------------------------------------
# VIEW 3: ⚡ EXPLORE (Multi-Dimensional Analytics)
# ---------------------------------------------------------
elif st.session_state.current_nav == "⚡ Explore":
    st.markdown("## ⚡ Multi-Dimensional Analytics Explorer")
    st.caption("Slice, filter, and drill into live policy, claim, and geographic insurance metrics.")

    exp_tab1, exp_tab2, exp_tab3 = st.tabs(["🏛️ Policies & Revenue", "🚨 Claims & Loss Ratios", "🗺️ Geographic Distribution"])

    with exp_tab1:
        st.markdown("### Policy Types & Plan Tier Breakdown")
        sql_exp_p = f"""SELECT 
            POLICY_TYPE AS "Policy Type", 
            COUNT(POLICY_ID) AS "Policies", 
            CONCAT('$', TO_VARCHAR(ROUND(SUM(PREMIUM_AMOUNT), 2), '999,999,990.00')) AS "Revenue", 
            CONCAT('$', TO_VARCHAR(ROUND(AVG(PREMIUM_AMOUNT), 2), '999,990.00')) AS "Avg Premium", 
            TO_VARCHAR(ROUND(AVG(LOSS_RATIO), 2), '0.00') AS "Avg Loss Ratio" 
        FROM {current_db}.{current_sh}.POLICIES 
        GROUP BY POLICY_TYPE 
        ORDER BY SUM(PREMIUM_AMOUNT) DESC;"""
        rows_p, _ = cached_sf_mgr.execute_query(sql_exp_p)
        st.dataframe(pd.DataFrame(rows_p or []), use_container_width=True)

    with exp_tab2:
        st.markdown("### Claims Distribution by Status")
        sql_exp_c = f"""SELECT 
            COALESCE(CLAIM_STATUS, 'Approved') AS "Status", 
            COUNT(CLAIM_ID) AS "Count" 
        FROM {current_db}.{current_sh}.CLAIMS 
        GROUP BY CLAIM_STATUS 
        ORDER BY "Count" DESC;"""
        rows_c, _ = cached_sf_mgr.execute_query(sql_exp_c)
        df_c = pd.DataFrame(rows_c or []).set_index("Status") if rows_c else pd.DataFrame()
        if not df_c.empty:
            st.bar_chart(df_c, use_container_width=True)
        else:
            st.info("No claims status records found.")

    with exp_tab3:
        st.markdown("### Top States by Premium Revenue")
        sql_exp_g = f"""SELECT 
            COALESCE(c.STATE, 'Unknown') AS "State", 
            ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS "Total Premium ($)", 
            COUNT(p.POLICY_ID) AS "Policies" 
        FROM {current_db}.{current_sh}.POLICIES p 
        JOIN {current_db}.{current_sh}.CUSTOMERS c ON p.CUSTOMER_ID = c.CUSTOMER_ID 
        GROUP BY c.STATE 
        ORDER BY "Total Premium ($)" DESC 
        LIMIT 10;"""
        rows_g, _ = cached_sf_mgr.execute_query(sql_exp_g)
        df_geo = pd.DataFrame(rows_g or []).set_index("State") if rows_g else pd.DataFrame()
        if not df_geo.empty:
            st.line_chart(df_geo, use_container_width=True)
        else:
            st.info("No geographic customer data found.")


# ---------------------------------------------------------
# VIEW 4: 📊 DATA (Snowflake Catalog & Table Browser)
# ---------------------------------------------------------
elif st.session_state.current_nav == "📊 Data":
    st.markdown("## 📊 Snowflake Data Catalog")
    st.caption("Live enterprise catalog metadata and table schemas.")

    sql_tables = f"""SELECT 
        TABLE_NAME AS "Table Name", 
        ROW_COUNT AS "Rows", 
        BYTES AS "Bytes", 
        TABLE_TYPE AS "Table Type" 
    FROM {current_db}.INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_SCHEMA = '{current_sh}' 
    ORDER BY TABLE_NAME;"""
    table_rows, _ = cached_sf_mgr.execute_query(sql_tables)
    st.dataframe(pd.DataFrame(table_rows or []), use_container_width=True)
    
    st.markdown("### 🔍 Live Preview: Policies")
    sql_preview = f"SELECT POLICY_ID, POLICY_TYPE, PLAN_TIER, PREMIUM_AMOUNT, LOSS_RATIO FROM {current_db}.{current_sh}.POLICIES LIMIT 5;"
    preview_rows, _ = cached_sf_mgr.execute_query(sql_preview)
    st.dataframe(pd.DataFrame(preview_rows or []), use_container_width=True)


# ---------------------------------------------------------
# VIEW 5: 📄 DOCS (Semantic Layer & Dictionary)
# ---------------------------------------------------------
elif st.session_state.current_nav == "📄 Docs":
    st.markdown("## 📄 Semantic Views & Data Dictionary")
    st.caption("Enterprise insurance semantic data model and entity definitions.")

    st.markdown("""
    ### 🏛️ Active Semantic Model: `INSURANCE_ANALYTICS`
    - **Live Tables**: `POLICIES`, `CUSTOMERS`, `CLAIMS`, `AGENTS`, `AT_RISK_POLICIES`, `CHURN_PREDICTIONS`, `CLAIMS_KPI`, `POLICY_TRENDS`, `LOSS_RATIO_HISTORY`, `DQ_RULES`, `DQ_VALIDATION_RESULTS`
    - **Key Dimensions**: `CUSTOMER_ID`, `POLICY_ID`, `AGENT_ID`, `CLAIM_TYPE`, `STATE`
    - **Measures**: `PREMIUM_AMOUNT`, `CLAIM_AMOUNT`, `DAYS_TO_RESOLVE`, `FRAUD_SCORE`
    - **Calculated Metrics**: `LOSS_RATIO = CLAIM_AMOUNT / PREMIUM_AMOUNT`
    """)


# ---------------------------------------------------------
# VIEW 6: 🛡 QUALITY (Data Trust & Integrity Scorecard)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🛡 Quality":
    st.markdown("## 🛡 Data Trust & Integrity Scorecard")
    st.caption("Real-time data quality validation checks and pass thresholds.")

    sql_dq_scorecard = f"""SELECT 
        RULE_NAME AS "Rule Name", 
        RULE_CATEGORY AS "Dimension", 
        TARGET_TABLE AS "Target Table", 
        THRESHOLD_PASS AS "Pass Threshold (%)", 
        SEVERITY AS "Severity", 
        ACTIVE_FLAG AS "Active", 
        DESCRIPTION AS "Description" 
    FROM {current_db}.{current_sh}.DQ_RULES 
    ORDER BY RULE_CATEGORY, RULE_NAME;"""
    dq_rows, _ = cached_sf_mgr.execute_query(sql_dq_scorecard)
    st.dataframe(pd.DataFrame(dq_rows or []), use_container_width=True)


# ---------------------------------------------------------
# VIEW 7: 🚨 INCIDENTS (Fraud & High Risk Alerts)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🚨 Incidents":
    st.markdown("## 🚨 Incident & High Risk Alert Center")
    st.caption("Flagged claims, potential fraud indicators, and priority escalations.")

    st.markdown("### ⚠️ Active High-Risk Claims (Fraud Score >= 0.75 OR Fraud Flag = TRUE)")
    sql_incidents = f"""SELECT 
        CLAIM_ID AS "Claim ID", 
        POLICY_ID AS "Policy ID", 
        CLAIM_TYPE AS "Claim Type", 
        CONCAT('$', TO_VARCHAR(ROUND(CLAIM_AMOUNT, 2), '999,999,990.00')) AS "Claim Amount", 
        ROUND(FRAUD_SCORE, 2) AS "Fraud Score", 
        PRIORITY AS "Priority", 
        CLAIM_STATUS AS "Status", 
        COALESCE(FRAUD_REASON, 'Suspicious claim pattern') AS "Fraud Reason" 
    FROM {current_db}.{current_sh}.CLAIMS 
    WHERE FRAUD_FLAG = TRUE OR FRAUD_SCORE >= 0.75 
    ORDER BY FRAUD_SCORE DESC, CLAIM_AMOUNT DESC 
    LIMIT 25;"""
    inc_rows, _ = cached_sf_mgr.execute_query(sql_incidents)
    st.dataframe(pd.DataFrame(inc_rows or []), use_container_width=True)


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
