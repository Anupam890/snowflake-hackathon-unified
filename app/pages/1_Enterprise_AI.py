"""
Enterprise AI Studio Page - INSIGHT AI Multi-Page Application.
Dedicated Snowflake Cortex AI conversational analyst, multimodal document synthesis,
and interactive data visualization studio.
"""
import os
import sys
import json
import datetime
from typing import Optional, List, Dict, Any, Tuple
import requests
import pandas as pd
from dotenv import dotenv_values
import streamlit as st

# ---------------------------------------------------------
# Page Configuration & Layout
# ---------------------------------------------------------
try:
    st.set_page_config(
        page_title="INSIGHT AI — Enterprise AI Studio",
        page_icon="❄️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# Ensure project root and app dir are in sys.path
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PROJECT_ROOT = os.path.abspath(os.path.join(APP_DIR, '..'))

for p in [PROJECT_ROOT, APP_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values(os.path.join(PROJECT_ROOT, '.env')).items()}
API_BASE_URL = env_config.get("API_URL", "http://127.0.0.1:8001")

# Backend & Snowflake Session Management
from config.snowflake_manager import get_st_cached_snowflake_manager
from services.server_manager import ensure_backend_server
import services.backend_service as backend_service
from styles.style_loader import inject_custom_css

# Inject global enterprise stylesheet
inject_custom_css()

# Auto-start backend if needed and grab cached Snowflake manager
ensure_backend_server()
cached_sf_mgr = get_st_cached_snowflake_manager()


# ---------------------------------------------------------
# Cached Session & Context Helpers
# ---------------------------------------------------------
@st.cache_data(ttl=25)
def fetch_snowflake_status(base_url: str = API_BASE_URL):
    try:
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
        print(f"[Enterprise AI Call] In-process execution note: {inproc_err}. Falling back to REST API...")
    
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
# State Initialization
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello! I am **INSIGHT AI**, your intelligent enterprise insurance analyst powered directly by Snowflake Cortex. You can ask complex analytical questions, explore claim patterns, or upload policy documents and claim forms for instant synthesis.",
            "sql": None,
            "data": None,
            "thinking": None,
            "attached_doc": None,
            "raw_payload": None
        }
    ]

if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None
if "uploaded_doc_name" not in st.session_state:
    st.session_state.uploaded_doc_name = None
if "uploaded_doc_summary" not in st.session_state:
    st.session_state.uploaded_doc_summary = None
if "uploaded_doc_text" not in st.session_state:
    st.session_state.uploaded_doc_text = None

# Snowflake session context
sf_context = fetch_snowflake_status(API_BASE_URL)
current_user = sf_context.get("user") or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
current_role = sf_context.get("role") or "ACCOUNTADMIN"
current_wh = sf_context.get("warehouse") or "COMPUTE_WH"
current_db = sf_context.get("database") or "UNIFIEDAI_DB"
current_sh = sf_context.get("schema") or "UNIFIEDAI_SH"
current_agent = sf_context.get("default_agent") or "INS_ANALYTICS_AGENT"
user_initial = current_user[0].upper() if current_user else "U"


# ---------------------------------------------------------
# Sticky Top Navbar Header
# ---------------------------------------------------------
st.markdown(f"""
    <div class="top-navbar">
        <div class="brand-container">
            <span class="brand-logo">❄ INSIGHT AI</span>
            <div class="nav-divider"></div>
            <span class="nav-breadcrumb">Enterprise Intelligence Studio • Cortex AI</span>
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
# Sidebar Navigation & Settings
# ---------------------------------------------------------
with st.sidebar:
    # 1. Brand Card
    st.markdown("""
        <div class="sidebar-brand-card">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div class="sidebar-brand-title">❄ INSIGHT AI</div>
                <span class="sidebar-live-pill">● LIVE</span>
            </div>
            <div class="sidebar-brand-sub">Snowflake Intelligence Suite</div>
        </div>
    """, unsafe_allow_html=True)

    # 2. Workspace Navigation (Seamless Multi-Page Dispatcher)
    st.markdown('<div class="sidebar-section-header">WORKSPACE NAVIGATION</div>', unsafe_allow_html=True)
    
    nav_analytics = ["◈ Insurance Portfolio", "◉ Enterprise AI", "⚡ Explore", "📊 Data"]
    for nav_item in nav_analytics:
        is_active = (nav_item == "◉ Enterprise AI")
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_ai_{nav_item}", use_container_width=True, type=btn_type):
            if "Enterprise AI" not in nav_item:
                st.session_state.current_nav = nav_item
                try:
                    st.switch_page("streamlit.py")
                except Exception:
                    try:
                        st.switch_page("streamlit_app.py")
                    except Exception:
                        st.rerun()

    st.divider()

    # 3. Cortex Model Configuration
    st.markdown('<div class="sidebar-section-header">CORTEX LLM ENGINE</div>', unsafe_allow_html=True)
    selected_model = st.selectbox(
        "Cortex Foundation Model",
        ["claude-3-5-sonnet", "mistral-large2", "snowflake-arctic", "llama3.1-70b"],
        index=0,
        label_visibility="collapsed"
    )

    enable_reasoning = st.toggle("Enable Extended Reasoning", value=True)
    auto_run_sql = st.toggle("Auto-Execute Generated SQL", value=True)

    st.divider()

    # Quick Actions
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
            <div style="flex:1; min-width: 0;">
                <div class="user-name-text" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{current_user}</div>
                <div class="user-role-badge">● {current_role}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# Enterprise AI Main View
# ---------------------------------------------------------
st.markdown("""
    <div class="greeting-title" style="margin-bottom: 4px;">◉ Enterprise AI Studio</div>
    <div class="greeting-sub" style="margin-bottom: 18px;">Conversational analytics powered by Snowflake Cortex LLM, semantic insurance models, and multimodal context.</div>
""", unsafe_allow_html=True)

# Suggested Quick Query Pills
st.markdown('<div class="suggested-label">SUGGESTED ANALYTICS PROMPTS</div>', unsafe_allow_html=True)
pill_col1, pill_col2, pill_col3, pill_col4 = st.columns(4)

with pill_col1:
    if st.button("🚨 Investigate Flagged Claims", use_container_width=True):
        st.session_state.selected_prompt = "Perform forensic risk analysis on top flagged insurance claims with fraud scores > 0.75."
        st.rerun()

with pill_col2:
    if st.button("💰 Premium Revenue by Type", use_container_width=True):
        st.session_state.selected_prompt = "Calculate total gross written premium, average policy size, and loss ratio grouped by policy type."
        st.rerun()

with pill_col3:
    if st.button("📉 Loss Ratio Trajectory", use_container_width=True):
        st.session_state.selected_prompt = "Show the monthly historical loss ratio trajectory and premium inflow trends for the past 12 months."
        st.rerun()

with pill_col4:
    if st.button("🗺️ Top Risk Territories", use_container_width=True):
        st.session_state.selected_prompt = "List the top 5 states by total written premium along with their average claims severity."
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# Active Attached Document Chip (ChatGPT Style)
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
        if st.button("✖ Remove File", key="btn_pg_discard_attached_chip", use_container_width=True):
            st.session_state.uploaded_doc_name = None
            st.session_state.uploaded_doc_summary = None
            st.session_state.uploaded_doc_text = None
            st.rerun()

# Attachment Popover Bar
c_attach_btn, c_spacer = st.columns([2.8, 9.2])
with c_attach_btn:
    with st.popover("📎 Attach Document", use_container_width=True, help="Attach Claim Document, Policy PDF, or Dataset to query"):
        st.markdown("**Attach File for AI Analysis**")
        st.caption("Supported: PDF, CSV, Excel, TXT, JSON, Images")
        agent_up = st.file_uploader(
            "Upload document",
            type=["pdf", "csv", "xlsx", "xls", "txt", "json", "png", "jpg", "jpeg"],
            key="ask_ai_pg_popover_uploader",
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
            render_assistant_response(message, msg_key_prefix=f"chat_pg_{idx}")
        else:
            if message.get("attached_doc"):
                st.markdown(f'<div class="attached-file-badge">📎 Context: {message["attached_doc"]}</div>', unsafe_allow_html=True)
            st.markdown(message["content"])

# User Chat Input
chat_val = st.chat_input(f"Ask Cortex Agent {current_agent} (e.g., query database, synthesize document, explain trends)...")
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

        render_assistant_response(assistant_msg, msg_key_prefix="latest_pg")
        st.session_state.messages.append(assistant_msg)
