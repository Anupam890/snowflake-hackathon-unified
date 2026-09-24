"""
Enterprise AI Studio Page - INSIGHT AI Multi-Page Application.
Dedicated Snowflake Cortex AI conversational analyst, multimodal document synthesis,
and interactive data visualization studio.
"""
import os
import sys
import re
import json
import html
import time
import datetime
from typing import Optional, List, Dict, Any, Tuple
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

# Backend & Snowflake Session Management
from config.snowflake_manager import get_st_cached_snowflake_manager
import services.backend_service as backend_service
from app.lib.agent_client import call_cortex_agent, fetch_snowflake_status
from app.lib.render import extract_uploaded_file_content, render_assistant_response
from app.lib.toasts import flush_toasts, queue_toast, toast_now
from styles.style_loader import inject_custom_css

# Inject global enterprise stylesheet
inject_custom_css()

# Emit anything a previous run queued just before calling st.rerun().
flush_toasts()

# Grab cached Snowflake manager
cached_sf_mgr = get_st_cached_snowflake_manager()


# ---------------------------------------------------------
# Cached Session & Context Helpers
# ---------------------------------------------------------












# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------
if "messages" not in st.session_state or not st.session_state.messages:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! I am **INSIGHT AI**, your intelligent enterprise insurance analyst. "
                "You can ask analytical questions, explore claim patterns, or upload policy documents, "
                "claim forms, and datasets for instant AI synthesis.\n\n"
                "**💡 Suggested Inquiries:**\n"
                "- 📊 **State Premiums & Loss Ratios:** *\"What is the total written premium and average claim amount by state?\"*\n"
                "- 🚨 **High-Risk Policy Types:** *\"Which policy types have the highest loss ratios and claim payouts?\"*\n"
                "- 🔍 **Fraud Risk Analysis:** *\"Identify top claims flagged with high fraud risk scores.\"*\n"
                "- 📉 **Customer Churn Exposure:** *\"What is the churn probability and total revenue at risk across customers?\"*\n"
                "- 📄 **Document Intelligence:** *\"Attach a policy document, loan agreement, or claim PDF to extract clauses, deductibles, or terms.\"*\n"
                "- 📈 **Trend Forecast:** *\"Show monthly policy trends, retention rates, and acquisition growth over the last 12 months.\"*"
            ),
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
# Bumped whenever the attachment is cleared, so the file_uploader gets a fresh
# key and forgets its file. Without this the widget keeps returning the removed
# file on the next rerun and silently re-attaches it.
if "doc_uploader_seq" not in st.session_state:
    st.session_state.doc_uploader_seq = 0
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"

# Snowflake session context
sf_context = fetch_snowflake_status(_mgr=cached_sf_mgr, _env_config=env_config)
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
            </div>
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

    # 3. Model selection
    st.markdown('<div class="sidebar-section-header">INSIGHT AI ENGINE</div>', unsafe_allow_html=True)
    selected_model = st.selectbox(
        "Model",
        ["claude-3-5-sonnet", "mistral-large2", "snowflake-arctic", "llama3.1-70b"],
        index=0,
        label_visibility="collapsed"
    )

    st.divider()

    # Quick Actions
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.session_state.uploaded_doc_name = None
        st.session_state.uploaded_doc_summary = None
        st.session_state.uploaded_doc_text = None
        st.session_state.uploaded_doc_snowflake = None
        st.session_state.doc_uploader_seq += 1
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
            key=f"ask_ai_pg_popover_uploader_{st.session_state.doc_uploader_seq}",
            label_visibility="collapsed"
        )
        if agent_up is not None:
            if st.session_state.get("uploaded_doc_name") != agent_up.name:
                summary, content = extract_uploaded_file_content(agent_up)
                agent_up.seek(0)
                raw_bytes = agent_up.read()

                try:
                    with st.spinner("❄️ Uploading and indexing the document..."):
                        ingest_res = backend_service.upload_and_ingest_pipeline(
                            file_bytes=raw_bytes,
                            file_name=agent_up.name,
                            full_text=content or summary or agent_up.name,
                            mgr=cached_sf_mgr
                        )
                except Exception as up_err:
                    print(f"[Upload Pipeline Error]: {up_err}")
                    # Report the failure as a failure. Previously this fabricated a
                    # "warning" with chunks_count=1, which the chip rendered as a
                    # green success for a document that was never ingested.
                    ingest_res = {
                        "status": "error",
                        "message": str(up_err),
                        "chunks_count": 0,
                    }
                
                st.session_state.uploaded_doc_name = agent_up.name
                st.session_state.uploaded_doc_summary = summary
                st.session_state.uploaded_doc_text = ingest_res.get("extracted_text") or content
                st.session_state.uploaded_doc_snowflake = ingest_res
                st.rerun()

with col_head_history:
    if st.button("📜 View Chat History", key="btn_right_top_history", use_container_width=True, type="secondary", help="Access archived Snowflake conversations and query replays"):
        st.switch_page("pages/2_Chat_History.py")

# Active Attached Document Chip (if a document is uploaded)
if st.session_state.uploaded_doc_name:
    col_chip, col_del = st.columns([9.5, 2.5])
    sync_meta = st.session_state.get("uploaded_doc_snowflake", {}) or {}
    chunks_count = sync_meta.get("chunks_count", 0)
    sync_status = sync_meta.get("status", "error")
    sync_message = sync_meta.get("message")
    refresh_status = sync_meta.get("search_refresh_status")

    # The status line reflects what actually happened in Snowflake rather than
    # asserting success unconditionally.
    if sync_status == "success":
        sync_colour = "#34D399"
        sync_line = (
            f"❄️ Synced to Snowflake @DOC_STAGE • {chunks_count} "
            f"chunk{'s' if chunks_count != 1 else ''} indexed in DOCUMENT_CHUNKS"
        )
        # Chunks exist but are not yet retrievable by the agent's search tool.
        if refresh_status and refresh_status != "success":
            sync_colour = "#FBBF24"
            sync_line += " • search index refresh failed, retrieval may lag up to 1 hour"
    elif sync_status == "warning":
        sync_colour = "#FBBF24"
        if chunks_count:
            # Partially indexed: content is searchable, but not all of it.
            sync_line = f"⚠️ Partially indexed • {sync_message or 'document was truncated'}"
        else:
            sync_line = f"⚠️ Uploaded to @DOC_STAGE but not indexed • {sync_message or 'no extractable text found'}"
    else:
        sync_colour = "#F87171"
        sync_line = f"❌ Snowflake ingestion failed • {sync_message or 'see application logs'}"

    safe_doc_name = html.escape(str(st.session_state.uploaded_doc_name))
    safe_doc_summary = html.escape(str(st.session_state.uploaded_doc_summary or 'Document context attached'))
    safe_sync_line = html.escape(sync_line)

    with col_chip:
        st.markdown(f"""
            <div class="chatgpt-file-chip">
                <span class="chatgpt-file-icon">📄</span>
                <div>
                    <div class="chatgpt-file-name">{safe_doc_name}</div>
                    <div class="chatgpt-file-meta">{safe_doc_summary}</div>
                    <div style="color: {sync_colour}; font-size: 0.72rem; font-weight: 600; margin-top: 2px;">
                        {safe_sync_line}
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
            st.session_state.doc_uploader_seq += 1
            st.rerun()

# ---------------------------------------------------------
# Render Conversation History
# ---------------------------------------------------------
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_assistant_response(message, msg_key_prefix=f"chat_pg_{idx}", mgr=cached_sf_mgr, env_config=env_config)
        else:
            if message.get("attached_doc"):
                st.markdown(f'<div class="attached-file-badge">📎 Context: {message["attached_doc"]}</div>', unsafe_allow_html=True)
            st.markdown(message["content"])

# Interactive Quick Suggestions (visible when chat starts)
if len(st.session_state.messages) <= 1:
    st.markdown('<div style="font-size:0.84rem; font-weight:600; color:#94A3B8; margin-top:14px; margin-bottom:8px;">💡 Suggested Inquiries to Explore:</div>', unsafe_allow_html=True)
    sug_cols1 = st.columns(3)
    sug_cols2 = st.columns(3)
    suggestions = [
        ("📊 State Premiums & Claims", "What is the total written premium and average claim amount by state?"),
        ("🚨 High-Risk Policy Types", "Which policy types have the highest loss ratios and total claims paid?"),
        ("🔍 Forensic Fraud Analysis", "Show top claims flagged with high fraud risk scores."),
        ("📉 Churn & Revenue at Risk", "What is the churn probability and total revenue at risk across customers?"),
        ("📈 12-Month Trend Analytics", "Show monthly policy trends, retention rates, and acquisition growth."),
        ("📋 Data Quality Audit", "Perform a data quality check on active policies and claim records.")
    ]
    for i, (label, prompt_text) in enumerate(suggestions):
        target_col = sug_cols1[i] if i < 3 else sug_cols2[i - 3]
        with target_col:
            if st.button(label, key=f"pg_sug_{i}", use_container_width=True, help=prompt_text):
                st.session_state.selected_prompt = prompt_text
                st.rerun()

# ---------------------------------------------------------
# User Chat Input
# ---------------------------------------------------------


# Tool identifiers the agent reports are internal names; map the ones we recognise to
# something readable and fall back to the raw name rather than inventing a label.
# Names below were observed from live response.tool_use events on this agent.
_TOOL_LABELS = {
    "system_execute_sql": "Running SQL on Snowflake",
    "system_agentic_semantic_context": "Reading the semantic model",
    "cortex_search": "Searching the document corpus",
    "cortex_analyst_text_to_sql": "Translating the question to SQL",
    "data_to_chart": "Building the visualisation",
    "server_skill": "Applying an agent skill",
}


def _balance_markdown(text: str):
    """Close markdown constructs the token stream has opened but not yet finished.

    A partially streamed answer routinely ends mid-construct, e.g. "**Texas lead" or an
    opened ``` fence. Rendering that as-is makes the stray markers visible and can flip
    the rest of the preview into bold or code until the closing marker arrives, so the
    open constructs are closed for display only.

    Returns (text_for_display, inside_code_fence).
    """
    if not text:
        return "", False

    # An odd number of fences means we are currently inside a code block.
    if text.count("```") % 2 == 1:
        return text + "\n```", True

    # Count inline markers only in prose, ignoring completed fenced blocks.
    prose = re.sub(r"```[\s\S]*?```", "", text)
    out = text
    if prose.count("**") % 2 == 1:
        out += "**"
    if prose.replace("**", "").count("`") % 2 == 1:
        out += "`"
    return out, False


class _ThinkingIndicator:
    """Live progress indicator for an in-flight Cortex Agent turn.

    Phase text comes from the agent's own `response.status` events (Snowflake sends
    messages like "Planning the next steps" and "Forming the answer"), so the label
    reflects what is actually happening instead of a generic spinner caption.

    Once text starts arriving, the indicator switches to previewing the streamed
    tokens with a trailing caret. That preview is deliberately provisional: the
    authoritative answer is assembled from the final `response` event by
    backend_service, which strips scratchpad preamble that the raw token stream
    still contains.
    """

    # Cap repaints. Deltas arrive far faster than Streamlit can re-render, and every
    # update is a full DOM replacement.
    _MIN_REDRAW_INTERVAL = 0.1

    def __init__(self, placeholder):
        self._placeholder = placeholder
        self._phase = "Connecting to Cortex Agent"
        self._buffer = ""
        self._streaming = False
        self._last_paint = 0.0
        self._render(force=True)

    def handle_event(self, event_name, payload):
        payload = payload or {}

        if event_name == "response.status":
            # Snowflake's own human-readable progress message.
            message = payload.get("message")
            if message and not self._streaming:
                self._phase = str(message)
                self._render(force=True)

        elif event_name in ("response.tool_use", "response.tool_call"):
            tool = payload.get("tool_use") or payload
            raw_name = tool.get("name") or tool.get("type")
            if raw_name and not self._streaming:
                label = _TOOL_LABELS.get(str(raw_name).lower()) or _TOOL_LABELS.get(str(raw_name))
                self._phase = label or f"Using {raw_name}"
                self._render(force=True)

        elif event_name == "response.text.delta":
            # Only deltas feed the preview. `response.text` events repeat the same
            # content in whole-paragraph form, so consuming both would double the text.
            chunk = payload.get("text")
            if chunk:
                self._streaming = True
                self._buffer += chunk
                self._render()

    def clear(self):
        self._placeholder.empty()

    def _render(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_paint) < self._MIN_REDRAW_INTERVAL:
            return
        self._last_paint = now

        if self._streaming:
            # Render the preview as markdown, matching how the final answer is rendered.
            # Escaping it into raw HTML instead showed the markdown source (literal ** and
            # a <br/> per newline, which doubled blank lines into large gaps) and then
            # visibly reflowed once the real answer replaced it.
            try:
                preview = backend_service.clean_text_encoding(self._buffer)
                # Currency is everywhere in these answers; without this, Streamlit's KaTeX
                # parser treats "$825 ... $363" as a math span and mangles the text.
                preview = backend_service.escape_dollars_for_markdown(preview)
            except Exception:
                preview = self._buffer

            display, inside_fence = _balance_markdown(preview)
            # A steady block caret, as ChatGPT uses while streaming. It is a plain
            # character rather than an animated span because st.markdown is called
            # without unsafe_allow_html here, so agent text cannot inject markup.
            if inside_fence:
                # Keep the caret inside the code block so it does not appear after it.
                display = preview + "\n▌\n```"
            else:
                display = display + " ▌"
            self._placeholder.markdown(display)
        else:
            self._placeholder.markdown(
                f'<div class="coco-thinking">'
                f'<span class="coco-thinking-shimmer">{html.escape(self._phase)}</span>'
                f'<span class="coco-thinking-dots"><span></span><span></span><span></span></span>'
                f'</div>',
                unsafe_allow_html=True,
            )


chat_val = st.chat_input("Ask INSIGHT AI anything (e.g. policy coverage, subscriber lookup, state premiums, claims)...")
user_prompt = chat_val or st.session_state.selected_prompt

if user_prompt:
    st.session_state.selected_prompt = None
    
    # Retrieval is the agent's job: its InsuranceDocs tool searches the corpus
    # itself, so the question is forwarded untouched. Any attached-document
    # scoping is applied by backend_service, which owns the attached_file arg.
    attached_doc_label = st.session_state.uploaded_doc_name
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
            engine="USER",
            status="submitted",
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
        indicator = _ThinkingIndicator(live_holder)

        # Measured wall-clock latency for the turn, persisted with the message so the
        # telemetry tab reports real response times instead of an estimate.
        turn_started = time.perf_counter()

        res = call_cortex_agent(
            db=current_db,
            schema=current_sh,
            agent=current_agent,
            prompt=combined_prompt,
            model=selected_model,
            attached_file=attached_doc_label,
            mgr=cached_sf_mgr,
            on_event=indicator.handle_event,
        )

        indicator.clear()
        turn_latency_ms = int((time.perf_counter() - turn_started) * 1000)

        resp_text = res.get("response", "No response returned.")
        sql_query = res.get("sql_query")
        query_data = res.get("data")
        thinking = res.get("thinking")
        turn_status = res.get("status") or "unknown"
        turn_tools = (res.get("metadata") or {}).get("tools_used") or []
        turn_engine = res.get("engine", "CORTEX_ANALYST" if sql_query else "CORTEX_SEARCH")
        debug_info = {"prompt": combined_prompt, "response": res, "metadata": res.get("metadata")}

        assistant_msg = {
            "role": "assistant",
            "content": resp_text,
            "sql": sql_query,
            "data": query_data,
            "thinking": thinking,
            "attached_doc": attached_doc_label,
            "raw_payload": debug_info,
            "model": selected_model,
            "engine": turn_engine,
            "latency_ms": turn_latency_ms,
            "tools_used": turn_tools,
        }

        render_assistant_response(assistant_msg, msg_key_prefix="latest_pg", mgr=cached_sf_mgr, env_config=env_config)
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
                latency_ms=turn_latency_ms,
                tools_used=turn_tools,
                engine=turn_engine,
                status=turn_status,
                mgr=cached_sf_mgr
            )
        except Exception as save_err:
            print(f"[Save Assistant Turn Error]: {save_err}")
