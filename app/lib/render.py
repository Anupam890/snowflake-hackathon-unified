"""Response rendering and file-parsing helpers shared by the Streamlit pages."""
import re
from typing import Dict, Optional

import pandas as pd
import streamlit as st

import services.backend_service as backend_service


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
            except Exception:
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
                except Exception:
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
                except Exception:
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


def extract_table_from_text(text: str) -> Optional[pd.DataFrame]:
    """Extracts markdown table from agent response text into a pandas DataFrame."""
    if not text:
        return None
    try:
        lines = [l.strip() for l in text.split('\n') if '|' in l]
        table_lines = [l for l in lines if l.startswith('|') and l.endswith('|')]
        if len(table_lines) >= 3 and any('-|-' in l or '---|' in l for l in table_lines):
            from io import StringIO
            df = pd.read_csv(StringIO('\n'.join(table_lines)), sep='|', engine='python').dropna(how='all', axis=1)
            df.columns = [c.strip() for c in df.columns]
            df = df[~df.iloc[:, 0].astype(str).str.contains('---', na=False)]
            for col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                try:
                    clean_col = df[col].str.replace('$', '', regex=False).str.replace(',', '', regex=False).str.replace('%', '', regex=False)
                    df[col] = pd.to_numeric(clean_col)
                except Exception:
                    pass
            if len(df) > 0:
                return df
    except Exception:
        pass
    return None


def strip_sql_blocks(text: str) -> str:
    """Remove fenced SQL code blocks from prose, leaving the rest of the text intact.

    Used for the Executive Summary tab, where the query is already shown in its
    own "Generated SQL" tab. Only ```sql-tagged and bare SELECT/WITH blocks are
    dropped; other fenced blocks (json, python, plain text) are preserved.
    """
    if not text:
        return ""

    pattern = re.compile(
        r"[ \t]*```[ \t]*(?:sql\b[^\n]*|(?=\s*(?:SELECT|WITH)\b))[\s\S]*?```[ \t]*\n?",
        re.IGNORECASE,
    )
    cleaned = pattern.sub("", text)
    # Collapse the blank-line gaps left behind by the removed blocks.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def render_interactive_chart(df: pd.DataFrame, key_prefix: str = "", show_heading: bool = True):
    """Renders smart interactive graphs (multi-series forecast, bar, line, area) for any tabular dataset.

    Set show_heading=False where the surrounding tab already provides its own
    context (e.g. the live results of a query in the Generated SQL tab).
    """
    if df is None or df.empty or len(df) < 2:
        return

    cols = list(df.columns)
    type_col = next((c for c in cols if any(k in c.lower() for k in ['policy_type', 'policy type', 'line', 'category', 'plan'])), None)
    time_col = next((c for c in cols if any(k in c.lower() for k in ['month', 'date', 'period', 'horizon', 'quarter'])), None)
    val_col = next((c for c in cols if any(k in c.lower() for k in ['forecast_new_policies', 'forecast', 'new_policies', 'policies', 'projected', 'count', 'value', 'amount', 'premium'])), None)

    if show_heading:
        st.markdown("#### 📈 Visualization & Trends")

    # 1. Specialized Multi-Series Time-Series / Forecast Chart (Pivoted by Category)
    if type_col and time_col and val_col and pd.api.types.is_numeric_dtype(df[val_col]):
        try:
            pivoted = df.pivot(index=time_col, columns=type_col, values=val_col)
            chart_type = st.radio(
                "Select Graph Format:",
                ["Multi-Series Line Chart", "Grouped Bar Chart", "Area Chart"],
                horizontal=True,
                key=f"pivot_chart_type_{key_prefix}"
            )
            if chart_type == "Multi-Series Line Chart":
                st.line_chart(pivoted, use_container_width=True)
            elif chart_type == "Grouped Bar Chart":
                st.bar_chart(pivoted, use_container_width=True)
            else:
                st.area_chart(pivoted, use_container_width=True)
            return
        except Exception:
            pass

    # 2. General Dataframe Chart
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    text_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

    if len(numeric_cols) > 0:
        chart_formats = ["Bar Chart", "Line Chart", "Area Chart"]
        chart_type = st.radio(
            "Select Graph Format:",
            chart_formats,
            horizontal=True,
            key=f"gen_chart_type_{key_prefix}"
        )
        try:
            if text_cols:
                chart_df = df.set_index(text_cols[0])[numeric_cols[:4]]
            else:
                chart_df = df[numeric_cols[:4]]

            if chart_type == "Bar Chart":
                st.bar_chart(chart_df, use_container_width=True)
            elif chart_type == "Line Chart":
                st.line_chart(chart_df, use_container_width=True)
            elif chart_type == "Area Chart":
                st.area_chart(chart_df, use_container_width=True)
        except Exception as e:
            st.warning(f"Chart render note: {e}")


def render_assistant_response(
    msg_dict,
    msg_key_prefix: str = "",
    mgr=None,
    env_config: Optional[Dict[str, str]] = None,
):
    """Render one assistant turn: summary, visualisations, and generated SQL."""
    env = env_config or {}
    response_text = msg_dict.get("content", "")
    # Strip "Recommended next steps:" from forecast responses
    response_text = backend_service.remove_recommended_next_steps(response_text)
    # Escape currency dollars to prevent KaTeX LaTeX math breakage in Streamlit
    response_text = backend_service.escape_dollars_for_markdown(response_text)

    sql_query = msg_dict.get("sql")
    query_data = msg_dict.get("data")
    thinking = msg_dict.get("thinking")
    attached_doc = msg_dict.get("attached_doc")
    engine = msg_dict.get("engine")

    # Extract or infer tabular DataFrame
    df = None
    if query_data and len(query_data) > 0:
        try:
            df = pd.DataFrame(query_data)
        except Exception:
            pass
    if df is None or df.empty:
        df = extract_table_from_text(response_text)

    has_data = df is not None and not df.empty
    has_sql = bool(sql_query and str(sql_query).strip())

    if not engine:
        engine = "CORTEX_ANALYST" if (has_sql or has_data) else "CORTEX_SEARCH"

    # Glowing Engine Badge
    if engine == "CORTEX_ANALYST":
        st.markdown('<div style="margin-bottom: 8px;"><span class="engine-badge cortex-analyst-badge">⚡ Snowflake Cortex Analyst</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="margin-bottom: 8px;"><span class="engine-badge cortex-search-badge">INSIGHT AI</span></div>', unsafe_allow_html=True)

    if attached_doc:
        st.markdown(f'<div class="attached-file-badge">📎 Context: {attached_doc}</div>', unsafe_allow_html=True)

    if thinking and thinking.strip():
        with st.expander("💭 Cortex Reasoning & Retrieval Trace", expanded=False):
            st.markdown(thinking)

    # Clean direct response for non-tabular Cortex Search
    if not has_sql and not has_data:
        st.markdown(response_text)
        return

    tab_titles = ["💬 Executive Summary"]
    if has_data:
        tab_titles.append("📊 Visualizations & Analytics")
    if has_sql:
        tab_titles.append("🔍 Generated SQL")

    tabs = st.tabs(tab_titles)
    tab_idx = 0

    with tabs[tab_idx]:
        # SQL has its own tab, so keep the summary prose free of query blocks.
        st.markdown(strip_sql_blocks(response_text) if has_sql else response_text)
    tab_idx += 1

    if has_data:
        with tabs[tab_idx]:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if len(numeric_cols) > 0:
                st.markdown("### 📊 Metrics Overview")
                m_cols = st.columns(min(len(numeric_cols), 4))
                for i, num_col in enumerate(numeric_cols[:4]):
                    with m_cols[i % min(len(numeric_cols), 4)]:
                        val = df[num_col].iloc[0] if len(df) == 1 else (df[num_col].sum() if any(k in num_col for k in ["TOTAL", "SUM", "COUNT"]) else df[num_col].mean())
                        val_str = f"${val:,.2f}" if isinstance(val, float) and val % 1 != 0 else f"{val:,}" if isinstance(val, (int, float)) else str(val)
                        label = ("Total " if len(df) > 1 and any(k in num_col for k in ["TOTAL", "SUM", "COUNT"]) else "") + num_col.replace('_', ' ').title()
                        st.metric(label=label, value=val_str)

            render_interactive_chart(df, key_prefix=f"vis_{msg_key_prefix}")

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
        tab_idx += 1

    if has_sql:
        with tabs[tab_idx]:
            st.markdown("### 🔍 Snowflake SQL Query")
            st.code(sql_query, language="sql")

            # Widget keys must be stable for this message across reruns. The caller's
            # msg_key_prefix is not: the same answer renders as "latest_pg" while the
            # turn is live and as "chat_pg_<idx>" from history afterwards. Keying on it
            # meant the Run button vanished on the rerun its own click triggered, so the
            # click was discarded and no results ever appeared. The uid is cached on the
            # message dict, which session_state keeps alive between reruns.
            msg_uid = msg_dict.get("msg_uid")
            if not msg_uid:
                msg_uid = f"m{abs(hash((response_text or '')[:300] + str(sql_query))) % 10**10}"
                msg_dict["msg_uid"] = msg_uid

            # Action controls to execute query live from UI
            col_run, col_edit, _col_spacer = st.columns([2.5, 2, 5.5])
            run_key = f"btn_run_sql_{msg_uid}"
            edit_toggle_key = f"toggle_edit_sql_{msg_uid}"
            state_res_key = f"sql_run_result_{msg_uid}"

            with col_run:
                run_clicked = st.button("▶ Run Query", key=run_key, type="primary", use_container_width=True)
            with col_edit:
                show_editor = st.checkbox("✏️ Edit Query", key=edit_toggle_key)

            target_db_name = env.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")

            custom_sql = sql_query
            if show_editor:
                custom_sql = st.text_area(
                    "Modify SQL query before executing:",
                    value=sql_query,
                    height=130,
                    key=f"txt_sql_editor_{msg_uid}"
                )
                if st.button("▶ Execute Modified Query", key=f"btn_run_custom_{msg_uid}", type="secondary"):
                    run_clicked = True

            if run_clicked:
                try:
                    import time
                    with st.spinner("❄️ Executing SQL query in Snowflake..."):
                        t0 = time.time()
                        clean_run_sql = backend_service.sanitize_semantic_view_sql(custom_sql, db=target_db_name)
                        # The SQL above is user-editable, so gate it before execution.
                        # sanitize_semantic_view_sql only rewrites table names; it is not
                        # a safety check.
                        backend_service.assert_read_only_sql(clean_run_sql)
                        exec_mgr = mgr or backend_service.snowflake_manager
                        exec_data, exec_cols = exec_mgr.execute_query(clean_run_sql)
                        dur = time.time() - t0
                        # execute_query returns (None, None) on failure, which is other-
                        # wise indistinguishable from an empty result set.
                        run_err = None
                        if exec_data is None:
                            run_err = exec_mgr.get_last_error() or "Query failed with no error detail."
                        st.session_state[state_res_key] = {
                            "data": exec_data,
                            "columns": exec_cols,
                            "duration": dur,
                            "sql": clean_run_sql,
                            "error": run_err
                        }
                except backend_service.UnsafeSqlError as unsafe_err:
                    st.session_state[state_res_key] = {
                        "data": None,
                        "columns": None,
                        "duration": 0,
                        "sql": custom_sql,
                        "error": f"Blocked: {unsafe_err}"
                    }
                except Exception as sql_exec_err:
                    st.session_state[state_res_key] = {
                        "data": None,
                        "columns": None,
                        "duration": 0,
                        "sql": custom_sql,
                        "error": str(sql_exec_err)
                    }

            # Render query results when available
            if state_res_key in st.session_state:
                res_state = st.session_state[state_res_key]
                if res_state.get("error"):
                    st.error(f"❌ Snowflake Query Error: {res_state['error']}")
                elif res_state.get("data") is not None:
                    e_data = res_state["data"]
                    e_cols = res_state["columns"]
                    e_dur = res_state["duration"]
                    e_df = pd.DataFrame(e_data) if e_data else pd.DataFrame(columns=e_cols)

                    st.success(f"✅ Executed successfully in **{e_dur:.2f}s** • Returned **{len(e_df):,}** rows")

                    # Live Data Table
                    st.markdown("##### 📋 Query Results")
                    st.dataframe(e_df, use_container_width=True)

                    # Interactive Chart
                    if not e_df.empty:
                        render_interactive_chart(e_df, key_prefix=f"live_chart_{msg_uid}", show_heading=False)

                        csv_dl = e_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Export Query Result as CSV",
                            data=csv_dl,
                            file_name="snowflake_query_result.csv",
                            mime="text/csv",
                            key=f"dl_live_{msg_uid}"
                        )
                else:
                    st.info("Query executed successfully. (0 rows returned)")
        tab_idx += 1
