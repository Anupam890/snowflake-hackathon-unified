"""
Chat History Archive Page - INSIGHT AI Multi-Page Application.
Audit archive, session viewer, and conversation replayer powered by
Snowflake UNIFIEDAI_DB.UNIFIEDAI_SH.CHAT_HISTORY.
"""
import os
import sys
import json
import datetime
from typing import Optional, List, Dict, Any
import pandas as pd
from dotenv import dotenv_values
import streamlit as st

# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
try:
    st.set_page_config(
        page_title="INSIGHT AI — Chat History Archive",
        page_icon="📜",
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
import services.backend_service as backend_service
import importlib
importlib.reload(backend_service)
from styles.style_loader import inject_custom_css

# Inject global enterprise stylesheet
inject_custom_css()
cached_sf_mgr = get_st_cached_snowflake_manager()

# Snowflake session context
try:
    sf_context = backend_service.get_snowflake_status(mgr=cached_sf_mgr)
except Exception:
    sf_context = {}

current_user = sf_context.get("user") or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
current_role = sf_context.get("role") or "ACCOUNTADMIN"
current_wh = sf_context.get("warehouse") or "COMPUTE_WH"
current_db = sf_context.get("database") or "UNIFIEDAI_DB"
current_sh = sf_context.get("schema") or "UNIFIEDAI_SH"
user_initial = current_user[0].upper() if current_user else "U"


# ---------------------------------------------------------
# Sticky Top Navbar Header
# ---------------------------------------------------------
st.markdown(f"""
    <div class="top-navbar">
        <div class="brand-container">
            <span class="brand-logo">❄ INSIGHT AI</span>
            <div class="nav-divider"></div>
            <span class="nav-breadcrumb">Enterprise Intelligence Studio • Chat History Archive</span>
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
# Sidebar Navigation
# ---------------------------------------------------------
with st.sidebar:
    # 1. Brand Card
    st.markdown("""
        <div class="sidebar-brand-card">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div class="sidebar-brand-title">❄ INSIGHT AI</div>
                <span class="sidebar-live-pill">● ARCHIVE</span>
            </div>
            <div class="sidebar-brand-sub">Snowflake Intelligence Suite</div>
        </div>
    """, unsafe_allow_html=True)

    # 2. Workspace Navigation
    st.markdown('<div class="sidebar-section-header">WORKSPACE NAVIGATION</div>', unsafe_allow_html=True)
    nav_items = ["◈ Insurance Portfolio", "◉ Enterprise AI", "📜 Chat History", "⚡ Explore", "📊 Data"]
    for item in nav_items:
        is_active = (item == "📜 Chat History")
        btn_type = "primary" if is_active else "secondary"
        if st.button(item, key=f"hist_nav_{item}", use_container_width=True, type=btn_type):
            if "Enterprise AI" in item:
                st.switch_page("pages/1_Enterprise_AI.py")
            elif "Chat History" not in item:
                st.session_state.current_nav = item
                try:
                    st.switch_page("streamlit.py")
                except Exception:
                    try:
                        st.switch_page("streamlit_app.py")
                    except Exception:
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
# ---------------------------------------------------------
# Main Chat History Archive View
# ---------------------------------------------------------

# Top Header Row
col_head_left, col_head_ref = st.columns([9.2, 2.8])
with col_head_left:
    st.markdown("""<div style="display: flex; align-items: center; gap: 10px; margin-top: 4px; margin-bottom: 12px;">
<h2 style="margin: 0; font-size: 1.45rem; font-weight: 700; color: #F8FAFC; letter-spacing: -0.02em;">
Archived Chat History
</h2>
</div>""", unsafe_allow_html=True)

with col_head_ref:
    if st.button("🔄 Refresh History", key="btn_refresh_top", use_container_width=True, type="secondary"):
        st.rerun()

# Fetch sessions from Snowflake
sessions = backend_service.get_all_chat_sessions(mgr=cached_sf_mgr)

# If no sessions exist yet
if not sessions:
    st.info("No chat history recorded yet in Snowflake. Conversations in the Enterprise AI Studio will be automatically archived here!")
    st.stop()

# Initialize selected session state
if "selected_session_id" not in st.session_state or not any(s.get("SESSION_ID") == st.session_state.selected_session_id for s in sessions):
    st.session_state.selected_session_id = sessions[0]["SESSION_ID"]

# Two-Column Master-Detail Layout
col_list, col_detail = st.columns([4.2, 7.8], gap="medium")

with col_list:
    st.markdown("### 🗂️ Previous Conversations")
    search_query = st.text_input("🔍 Search Past Chats", placeholder="Search prompt, date, or model...", label_visibility="collapsed")
    
    # Filter sessions based on search
    filtered_sessions = sessions
    if search_query and search_query.strip():
        sq = search_query.lower().strip()
        filtered_sessions = [
            s for s in sessions
            if sq in str(s.get("FIRST_QUESTION", "")).lower()
            or sq in str(s.get("SESSION_ID", "")).lower()
            or sq in str(s.get("MODEL", "")).lower()
            or sq in str(s.get("STARTED_AT", "")).lower()
        ]

    st.caption(f"Showing {len(filtered_sessions)} of {len(sessions)} sessions")

    for s in filtered_sessions:
        sess_id = s.get("SESSION_ID", "")
        is_selected = (sess_id == st.session_state.selected_session_id)
        
        # Format date
        raw_time = s.get("LAST_ACTIVE_AT") or s.get("STARTED_AT")
        time_str = str(raw_time)[:16] if raw_time else "Recent"
        first_q = s.get("FIRST_QUESTION") or "Insurance Analysis Session"
        if len(first_q) > 65:
            first_q = first_q[:65] + "..."
        
        msg_count = s.get("MESSAGE_COUNT", 1)
        model_tag = s.get("MODEL", "claude-3-5-sonnet")
        if "claude" in model_tag.lower():
            model_disp = "Claude 3.5"
        elif "mistral" in model_tag.lower():
            model_disp = "Mistral Large"
        elif "arctic" in model_tag.lower():
            model_disp = "Arctic"
        else:
            model_disp = "Llama 3.1"

        has_sql = (s.get("SQL_QUERIES_COUNT", 0) > 0)
        has_doc = bool(s.get("ATTACHED_DOC"))

        with st.container(border=True):
            col_t1, col_t2 = st.columns([7, 3])
            with col_t1:
                st.caption(f"🕒 {time_str} • `{sess_id[:14]}...`")
            with col_t2:
                if is_selected:
                    st.markdown('<div style="text-align:right;"><span style="color:#38BDF8; font-size:0.72rem; font-weight:700; background:rgba(56,189,248,0.15); border:1px solid #38BDF8; padding:2px 6px; border-radius:6px;">● ACTIVE</span></div>', unsafe_allow_html=True)

            st.markdown(f"**{first_q}**")

            # Meta chips rendered on single lines without indent
            pills = [f'<span class="history-meta-pill">💬 {msg_count} turns</span>', f'<span class="history-meta-pill">🧠 {model_disp}</span>']
            if has_sql:
                pills.append('<span class="history-badge-sql">⚡ SQL</span>')
            if has_doc:
                doc_name = s.get("ATTACHED_DOC")
                pills.append(f'<span class="history-badge-doc">📎 {doc_name}</span>')
            
            st.markdown(f'<div class="history-meta-row" style="margin-bottom:8px;">{" ".join(pills)}</div>', unsafe_allow_html=True)

            if is_selected:
                st.button("✓ Currently Viewing", key=f"btn_sel_{sess_id}", use_container_width=True, type="primary", disabled=True)
            else:
                if st.button("View Conversation ➔", key=f"btn_sel_{sess_id}", use_container_width=True, type="secondary"):
                    st.session_state.selected_session_id = sess_id
                    st.rerun()

# Detail Pane: Full Conversation Replayer
with col_detail:
    current_sess_id = st.session_state.selected_session_id
    messages = backend_service.get_chat_session_messages(current_sess_id, mgr=cached_sf_mgr)
    
    # Session Action Bar
    with st.container(border=True):
        r_hdr_left, r_hdr_actions = st.columns([7.0, 5.0])
        with r_hdr_left:
            st.markdown(f"<div style='font-size:1.15rem; font-weight:700; color:#F8FAFC;'>💬 Session: <code>{current_sess_id}</code></div>", unsafe_allow_html=True)
            st.caption(f"Archived in Snowflake • Total Messages: {len(messages)}")
        with r_hdr_actions:
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                if st.button("💬 Resume in Studio", key="btn_resume_session", use_container_width=True, type="primary", help="Load this session into Enterprise AI Studio"):
                    restored_msgs = []
                    for m in messages:
                        is_sql = bool(m.get("SQL_QUERY"))
                        restored_msgs.append({
                            "role": m.get("ROLE", "user"),
                            "content": m.get("CONTENT", ""),
                            "sql": m.get("SQL_QUERY"),
                            "data": m.get("QUERY_DATA_PARSED"),
                            "thinking": m.get("THINKING"),
                            "attached_doc": m.get("ATTACHED_DOC"),
                            "model": m.get("MODEL"),
                            "engine": "CORTEX_ANALYST" if is_sql else "CORTEX_SEARCH"
                        })
                    st.session_state.messages = restored_msgs
                    st.session_state.chat_session_id = current_sess_id
                    st.switch_page("pages/1_Enterprise_AI.py")
            with b_col2:
                if st.button("🗑️ Delete", key="btn_del_session", use_container_width=True, type="secondary", help="Delete this session from Snowflake"):
                    backend_service.delete_chat_session(current_sess_id, mgr=cached_sf_mgr)
                    st.session_state.selected_session_id = None
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if not messages:
        st.warning("No messages recorded in this conversation.")
    else:
        # Replay Chronological Conversation
        for idx, msg in enumerate(messages):
            role = msg.get("ROLE", "user")
            content = msg.get("CONTENT", "")
            sql_query = msg.get("SQL_QUERY")
            query_data = msg.get("QUERY_DATA_PARSED")
            thinking = msg.get("THINKING")
            attached_doc = msg.get("ATTACHED_DOC")
            msg_time = str(msg.get("TIMESTAMP", ""))[:19]
            msg_model = msg.get("MODEL", "claude-3-5-sonnet")

            with st.chat_message(role):
                if role == "user":
                    if attached_doc:
                        st.markdown(f'<div class="attached-file-badge" style="margin-bottom:6px;">📎 Context: {attached_doc}</div>', unsafe_allow_html=True)
                    st.markdown(content)
                    st.caption(f"Sent at: {msg_time}")
                else:
                    # Determine engine
                    has_sql = bool(sql_query and str(sql_query).strip())
                    has_data = bool(query_data and len(query_data) > 0)
                    
                    if has_sql or has_data:
                        engine_badge = '<span class="engine-badge cortex-analyst-badge">⚡ Snowflake Cortex Analyst</span>'
                    else:
                        engine_badge = '<span class="engine-badge cortex-search-badge">❄️ Snowflake Cortex Search (RAG)</span>'

                    header_html = f'<div class="assistant-header-bar" style="margin-bottom:8px;"><div class="assistant-agent-tag"><span class="service-dot"></span>{engine_badge}</div><div class="assistant-model-pill">{msg_model} • {msg_time}</div></div>'
                    st.markdown(header_html, unsafe_allow_html=True)

                    if thinking and thinking.strip():
                        with st.expander("💭 Cortex Agent Reasoning & Retrieval Trace", expanded=False):
                            st.markdown(thinking)

                    if not has_sql and not has_data:
                        st.markdown(content)
                    else:
                        tab_titles = ["💬 Executive Summary"]
                        if has_sql:
                            tab_titles.append("⚡ Executed SQL")
                        if has_data:
                            tab_titles.append("📊 Visualizations & Dataset")

                        r_tabs = st.tabs(tab_titles)
                        t_idx = 0

                        with r_tabs[t_idx]:
                            st.markdown(content)
                        t_idx += 1

                        if has_sql:
                            with r_tabs[t_idx]:
                                st.markdown("**Executed Snowflake SQL Query:**")
                                st.code(sql_query, language="sql")
                            t_idx += 1

                        if has_data:
                            with r_tabs[t_idx]:
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
                                        key=f"hist_chart_{current_sess_id}_{idx}"
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
                                    label="📥 Export Dataset as CSV",
                                    data=csv_data,
                                    file_name=f"snowflake_history_{current_sess_id}_{idx}.csv",
                                    mime="text/csv",
                                    key=f"dl_hist_{current_sess_id}_{idx}"
                                )

        # If only 1 turn (user only), show prompt resume banner
        if len(messages) == 1:
            st.info("ℹ️ Only the initial user prompt was recorded for this session. Click **💬 Resume in Studio** above to generate the response and continue the conversation.")

