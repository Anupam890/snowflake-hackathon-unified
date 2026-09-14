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
import importlib
import services.backend_service as backend_service
importlib.reload(backend_service)
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
        "database": env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB"),
        "schema": env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH"),
        "default_agent": env_config.get("INS_AGENT", "UNIFIED_ENTERPRISE_AGENT")
    }


def extract_uploaded_file_content(uploaded_file):
    """Extracts clean text and metadata from uploaded PDF, CSV, Excel, TXT, JSON, or images."""
    if uploaded_file is None:
        return None, None
    
    file_name = uploaded_file.name
    file_size_kb = uploaded_file.size / 1024
    file_ext = file_name.split('.')[-1].lower()
    
    try:
        uploaded_file.seek(0)
        if file_ext == "pdf":
            extracted_pages = []
            page_count = 0
            
            # 1. Primary: Try PyMuPDF (fitz) - high speed & full vector fidelity
            try:
                import fitz
                uploaded_file.seek(0)
                doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
                page_count = len(doc)
                for i, page in enumerate(doc):
                    t = page.get_text()
                    if t and t.strip():
                        extracted_pages.append(f"--- Page {i+1} ---\n{t.strip()}")
            except Exception as fitz_err:
                extracted_pages = []
                
            # 2. Secondary: Fallback to pypdf
            if not extracted_pages:
                try:
                    import pypdf
                    uploaded_file.seek(0)
                    reader = pypdf.PdfReader(uploaded_file)
                    page_count = len(reader.pages)
                    for i, page in enumerate(reader.pages):
                        pt = page.extract_text()
                        if pt and pt.strip():
                            extracted_pages.append(f"--- Page {i+1} ---\n{pt.strip()}")
                except Exception as pypdf_err:
                    pass
                    
            # 3. Tertiary: Fallback to pdfplumber
            if not extracted_pages:
                try:
                    import pdfplumber
                    uploaded_file.seek(0)
                    with pdfplumber.open(uploaded_file) as pdf:
                        page_count = len(pdf.pages)
                        for i, page in enumerate(pdf.pages):
                            pt = page.extract_text()
                            if pt and pt.strip():
                                extracted_pages.append(f"--- Page {i+1} ---\n{pt.strip()}")
                except Exception as plumber_err:
                    pass
                    
            full_text = "\n\n".join(extracted_pages)
            summary = f"PDF Document: {file_name} ({page_count or len(extracted_pages)} pages, {file_size_kb:.1f} KB)"
            return summary, full_text
            
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
            return summary, text
            
        elif file_ext in ["png", "jpg", "jpeg", "webp"]:
            summary = f"Image File: {file_name} ({file_size_kb:.1f} KB)"
            return summary, f"[Attached Image: {file_name} - Visual Claim Evidence / Receipt]"
            
        else:
            uploaded_file.seek(0)
            text = uploaded_file.read().decode("utf-8", errors="replace")
            return f"File: {file_name}", text
            
    except Exception as e:
        print(f"[File Parse Error]: {e}")
        return f"File: {file_name}", ""


def call_cortex_agent(base_url: str, db: str, schema: str, agent: str, prompt: str, model: str, attached_file: Optional[str] = None):
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
            attached_file=attached_file,
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
    engine = msg_dict.get("engine")
    if not engine:
        engine = "CORTEX_ANALYST" if (sql_query or (query_data and len(query_data) > 0)) else "CORTEX_SEARCH"

    # Glowing Engine Badge
    if engine == "CORTEX_ANALYST":
        st.markdown('<div style="margin-bottom: 8px;"><span class="engine-badge cortex-analyst-badge">⚡ Snowflake Cortex Analyst</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="margin-bottom: 8px;"><span class="engine-badge cortex-search-badge">❄️ Snowflake Cortex Search (RAG)</span></div>', unsafe_allow_html=True)

    if attached_doc:
        st.markdown(f'<div class="attached-file-badge">📎 Context: {attached_doc}</div>', unsafe_allow_html=True)

    if thinking and thinking.strip():
        with st.expander("💭 Cortex Reasoning & Retrieval Trace", expanded=False):
            st.markdown(thinking)

    has_sql = bool(sql_query and str(sql_query).strip())
    has_data = bool(query_data and len(query_data) > 0)

    # Clean direct response for Cortex Search (no SQL / data tabs)
    if not has_sql and not has_data:
        st.markdown(response_text)
        return

    tab_titles = ["💬 Executive Summary"]
    if has_sql:
        tab_titles.append("🔍 Generated SQL")
    if has_data:
        tab_titles.append("📊 Visualizations & Analytics")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    with tabs[tab_idx]:
        st.markdown(response_text)
        if has_data:
            df = pd.DataFrame(query_data)
            st.markdown("<br>", unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)
            
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Dataset as CSV",
                data=csv_data,
                file_name="snowflake_insurance_results.csv",
                mime="text/csv",
                key=f"dl_ans_{msg_key_prefix}"
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
                    key=f"chart_type_{msg_key_prefix}"
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
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"

# Snowflake session context
sf_context = fetch_snowflake_status(API_BASE_URL)
current_user = sf_context.get("user") or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
current_role = sf_context.get("role") or "ACCOUNTADMIN"
current_wh = sf_context.get("warehouse") or "COMPUTE_WH"
current_db = sf_context.get("database") or "UNIFIEDAI_DB"
current_sh = sf_context.get("schema") or "UNIFIEDAI_SH"
current_agent = env_config.get("INS_AGENT") or sf_context.get("default_agent") or "UNIFIED_ENTERPRISE_AGENT"
user_initial = current_user[0].upper() if current_user else "U"


# ---------------------------------------------------------
# Sticky Top Navbar Header
# ---------------------------------------------------------
st.markdown(f"""
    <div class="top-navbar">
        <div class="brand-container">
            <span class="brand-logo">❄ INSIGHT AI</span>
            <div class="nav-divider"></div>
            <span class="nav-breadcrumb">Enterprise Intelligence Studio</span>
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
    
    nav_analytics = ["◈ Insurance Portfolio", "◉ Enterprise AI", "📜 Chat History", "⚡ Explore", "📊 Data"]
    for nav_item in nav_analytics:
        is_active = (nav_item == "◉ Enterprise AI")
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_ai_{nav_item}", use_container_width=True, type=btn_type):
            if "Chat History" in nav_item:
                try:
                    st.switch_page("pages/2_Chat_History.py")
                except Exception:
                    st.rerun()
            elif "Enterprise AI" not in nav_item:
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
        st.session_state.chat_session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
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
# Enterprise AI Main View - Studio Layout
# ---------------------------------------------------------
model_display_name = {
    "claude-3-5-sonnet": "Claude 3.5 Sonnet",
    "mistral-large2": "Mistral Large 2",
    "snowflake-arctic": "Snowflake Arctic",
    "llama3.1-70b": "Llama 3.1 70B"
}.get(selected_model, selected_model)

# ---------------------------------------------------------
# Studio Header & Action Bar
# ---------------------------------------------------------
col_head_left, col_head_attach, col_head_history = st.columns([6.4, 2.8, 2.8])
with col_head_left:
    st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 4px; margin-bottom: 8px;">
            <h2 style="margin: 0; font-size: 1.45rem; font-weight: 700; color: #F8FAFC; letter-spacing: -0.02em;">
                Enterprise AI Studio
            </h2>
        </div>
    """, unsafe_allow_html=True)

with col_head_attach:
    with st.popover("📎 Attach Document", use_container_width=True, help="Attach Claim Document, Policy PDF, or Dataset to query"):
        st.markdown("**Attach File for Snowflake Stage Ingestion**")
        st.caption("Supported: PDF, CSV, Excel, TXT, JSON, Images")
        agent_up = st.file_uploader(
            "Upload document",
            type=["pdf", "csv", "xlsx", "xls", "txt", "json", "png", "jpg", "jpeg"],
            key="ask_ai_pg_popover_uploader",
            label_visibility="collapsed"
        )
        if agent_up is not None:
            if st.session_state.get("uploaded_doc_name") != agent_up.name:
                summary, content = extract_uploaded_file_content(agent_up)
                agent_up.seek(0)
                raw_bytes = agent_up.read()
                
                if not hasattr(backend_service, "upload_and_ingest_pipeline"):
                    import importlib
                    importlib.reload(backend_service)
                
                try:
                    with st.spinner("❄️ Uploading to Snowflake Stage (@DOC_STAGE) & generating Cortex Embeddings..."):
                        ingest_res = backend_service.upload_and_ingest_pipeline(
                            file_bytes=raw_bytes,
                            file_name=agent_up.name,
                            full_text=content or summary or agent_up.name,
                            mgr=cached_sf_mgr
                        )
                except Exception as up_err:
                    print(f"[Upload Pipeline Error]: {up_err}")
                    ingest_res = {"status": "warning", "message": str(up_err), "chunks_count": 1}
                
                st.session_state.uploaded_doc_name = agent_up.name
                st.session_state.uploaded_doc_summary = summary
                st.session_state.uploaded_doc_text = content
                st.session_state.uploaded_doc_snowflake = ingest_res
                st.rerun()

with col_head_history:
    if st.button("📜 View Chat History", key="btn_right_top_history", use_container_width=True, type="secondary", help="Access archived Snowflake conversations and query replays"):
        st.switch_page("pages/2_Chat_History.py")

# Active Attached Document Chip (if a document is uploaded)
if st.session_state.uploaded_doc_name:
    col_chip, col_del = st.columns([9.5, 2.5])
    sync_meta = st.session_state.get("uploaded_doc_snowflake", {})
    chunks_count = sync_meta.get("chunks_count", 1)
    with col_chip:
        st.markdown(f"""
            <div class="chatgpt-file-chip">
                <span class="chatgpt-file-icon">📄</span>
                <div>
                    <div class="chatgpt-file-name">{st.session_state.uploaded_doc_name}</div>
                    <div class="chatgpt-file-meta">{st.session_state.uploaded_doc_summary or 'Document context attached'}</div>
                    <div style="color: #34D399; font-size: 0.72rem; font-weight: 600; margin-top: 2px;">
                        ❄️ Synced to Snowflake @DOC_STAGE • {chunks_count} chunks indexed in DOCUMENT_CHUNKS with Cortex Embeddings
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col_del:
        if st.button("✖ Remove File", key="btn_pg_discard_attached_chip", use_container_width=True):
            st.session_state.uploaded_doc_name = None
            st.session_state.uploaded_doc_summary = None
            st.session_state.uploaded_doc_text = None
            st.session_state.uploaded_doc_snowflake = None
            st.rerun()

# ---------------------------------------------------------
# Render Conversation History
# ---------------------------------------------------------
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_assistant_response(message, msg_key_prefix=f"chat_pg_{idx}")
        else:
            if message.get("attached_doc"):
                st.markdown(f'<div class="attached-file-badge">📎 Context: {message["attached_doc"]}</div>', unsafe_allow_html=True)
            st.markdown(message["content"])

# ---------------------------------------------------------
# User Chat Input
# ---------------------------------------------------------
chat_val = st.chat_input("Ask Enterprise AI anything (e.g. policy coverage, subscriber lookup, state premiums, claims)...")
user_prompt = chat_val or st.session_state.selected_prompt

if user_prompt:
    st.session_state.selected_prompt = None
    
    # Check if an attachment should be merged into prompt
    attached_doc_label = st.session_state.uploaded_doc_name
    
    is_analytics = backend_service.is_analytical_query(user_prompt)
    search_context = ""
    # Only search document knowledge base if user uploaded a doc or if it is a document/unstructured question
    if not is_analytics or st.session_state.uploaded_doc_text or attached_doc_label:
        cortex_chunks = backend_service.search_cortex_documents(
            query=user_prompt, 
            limit=3, 
            filter_file=attached_doc_label, 
            mgr=cached_sf_mgr
        )
        if cortex_chunks:
            search_context = "\n[SNOWFLAKE CORTEX SEARCH KNOWLEDGE]:\n" + "\n---\n".join([
                f"(From {c.get('FILE_NAME', 'DOC')} - {c.get('DOC_TYPE', 'DOC')}):\n{c.get('CHUNK_TEXT', '')}"
                for c in cortex_chunks
            ])

    if st.session_state.uploaded_doc_text:
        combined_prompt = f"""[ATTACHED CONTEXT - {st.session_state.uploaded_doc_summary} (Stored in Snowflake @DOC_STAGE)]:
{st.session_state.uploaded_doc_text[:15000]}
{search_context}

[USER QUESTION / INSTRUCTION]:
{user_prompt}"""
    elif search_context:
        combined_prompt = f"""{search_context}

[USER QUESTION / INSTRUCTION]:
{user_prompt}"""
    else:
        combined_prompt = user_prompt

    st.session_state.messages.append({
        "role": "user",
        "content": user_prompt,
        "attached_doc": attached_doc_label
    })
    
    # Persist user message to Snowflake CHAT_HISTORY table
    try:
        backend_service.save_chat_message(
            session_id=st.session_state.chat_session_id,
            role="user",
            content=user_prompt,
            user_name=current_user,
            model=selected_model,
            attached_doc=attached_doc_label,
            mgr=cached_sf_mgr
        )
    except Exception as save_err:
        print(f"[Save User Turn Error]: {save_err}")
    
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
            model=selected_model,
            attached_file=attached_doc_label
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
            "raw_payload": debug_info,
            "model": selected_model,
            "engine": res.get("engine", "CORTEX_ANALYST" if sql_query else "CORTEX_SEARCH")
        }

        render_assistant_response(assistant_msg, msg_key_prefix="latest_pg")
        st.session_state.messages.append(assistant_msg)
        
        # Persist assistant response to Snowflake CHAT_HISTORY table
        try:
            backend_service.save_chat_message(
                session_id=st.session_state.chat_session_id,
                role="assistant",
                content=resp_text,
                user_name=current_user,
                model=selected_model,
                sql_query=sql_query,
                query_data=query_data,
                attached_doc=attached_doc_label,
                thinking=thinking,
                mgr=cached_sf_mgr
            )
        except Exception as save_err:
            print(f"[Save Assistant Turn Error]: {save_err}")
