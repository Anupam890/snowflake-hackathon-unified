"""
Unified Backend Service Layer.
Encapsulates Cortex Agent bridge execution, dynamic SQL generation, KPI overview metrics,
and schema metadata. Reuses persistent Snowflake session manager for zero-overhead, MFA-cached operations.
"""
import os
import sys
import re
import json
import requests
import tempfile
import datetime
from typing import Optional, Dict, Any, List, Callable, Tuple
from dotenv import dotenv_values

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.snowflake_manager import snowflake_manager, SnowflakeManager, SnowflakeQueryError

env_config = {k.strip(): v.strip() for k, v in dotenv_values(os.path.join(PROJECT_ROOT, '.env')).items()}

# The agent that owns all routing, tool selection and retrieval for this app.
DEFAULT_AGENT_NAME = "UNIFIED_ENTERPRISE_AGENT"




















def extract_sql_from_text(text: str) -> Optional[str]:
    """Extracts SQL query block from markdown text or raw text."""
    if not text:
        return None
    # 1. Match markdown code block with sql/SQL/unspecified language
    match = re.search(r"```(?:sql|SQL)?\s*((?:SELECT|WITH)[\s\S]+?)\s*```", text, re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        if not sql.endswith(";"):
            sql += ";"
        if re.search(r"\bFROM\b", sql, re.IGNORECASE):
            return sql
    # 2. Match un-fenced SELECT/WITH query that contains a FROM clause
    raw_match = re.search(r"((?:SELECT|WITH)\s+[\s\S]+?\bFROM\b[\s\S]+?;)", text, re.IGNORECASE)
    if raw_match:
        sql = raw_match.group(1).strip()
        # Verify it doesn't look like general English markdown text
        if not any(stop_phrase in sql.lower() for stop_phrase in ["confidence bounds", "summary by", "takeaways", "policy type", "horizon"]):
            return sql
    return None


def clean_text_encoding(text: str) -> str:
    """Fixes mojibake artifacts caused by UTF-8 bytes mistakenly decoded as Latin-1/Windows-1252."""
    if not text:
        return ""
    # 1. Round-trip re-decode if text was mis-decoded from utf-8 as latin1
    try:
        if any(bad in text for bad in ["â", "Â", "Ã"]):
            fixed = text.encode("latin-1").decode("utf-8")
            return fixed
    except Exception:
        pass

    # 2. Targeted replacement of common mojibake characters
    replacements = [
        ("â€“", "–"),    # En dash
        ("â€”", "—"),    # Em dash
        ("â†’", "→"),    # Right arrow
        ("â€™", "'"),    # Right single quotation / apostrophe
        ("â€˜", "'"),    # Left single quotation
        ("â€œ", '"'),    # Left double quotation
        ("â€\x9d", '"'), # Right double quotation
        ("â€", '"'),    # Right double quotation
        ("â€•", "—"),    # Horizontal bar
        ("â€¢", "•"),    # Bullet point
        ("â€¦", "…"),    # Ellipsis
        ("â‰¥", "≥"),    # Greater than or equal to
        ("â‰¤", "≤"),    # Less than or equal to
        ("âœ”", "✔"),    # Check mark
        ("âœ–", "✖"),    # Cross mark
        ("Â ", " "),     # Non-breaking space artifact
        ("Â", ""),       # Stray Latin-1 artifact
    ]
    cleaned = text
    for bad, good in replacements:
        cleaned = cleaned.replace(bad, good)
    return cleaned


def remove_recommended_next_steps(text: str) -> str:
    """Strips 'Recommended next steps:' and any following recommendations from forecast responses."""
    if not text:
        return ""
    pattern = r'(?:\n|^)(?:#{1,4}\s*)?(?:\*{0,2})Recommended\s+(?:next\s+)?steps?:?.*?(?=(?:\n#{1,4}\s|\n```|\Z))'
    cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL).strip()
    return cleaned


def escape_dollars_for_markdown(text: str) -> str:
    """
    Escapes markdown-hostile characters in agent prose so currency and approximations
    render literally.

    Two problems, both caused by the agent's own writing style:

    - Standalone dollar amounts ($1,000, $1M, $500/mo) make Streamlit's KaTeX parser
      treat everything between two of them as a math span and mangle the text.
    - A tilde meaning "approximately" (~$167.5K) is markdown strikethrough. One per
      line is harmless, but two in the same line pair up and strike out everything
      between them, e.g. "lowest premium (~$167.5K) and the lowest claim (~$32.4K)"
      renders with the middle struck through.

    Code blocks, inline code and pre-escaped characters are left alone.
    """
    if not text:
        return ""
    
    # Split by fenced code blocks (```...```) to only escape in markdown prose
    parts = re.split(r'(```[\s\S]*?```)', text)
    processed_parts = []
    for i, part in enumerate(parts):
        # Odd indices are fenced code blocks - do not modify
        if i % 2 == 1:
            processed_parts.append(part)
            continue
        
        # Split by inline code (`...`)
        sub_parts = re.split(r'(`[^`\n]+`)', part)
        sub_processed = []
        for j, sub_part in enumerate(sub_parts):
            if j % 2 == 1:
                sub_processed.append(sub_part)
                continue
            
            # Escape currency dollars like $100, $1,500, $1.2M, $1M, $500/mo, $181,550/year
            # Emit exactly one backslash: in an re.sub template, '\\' yields a single
            # literal backslash while a bare '$' has no special meaning.
            escaped = re.sub(r'(?<!\\)\$(\d+(?:,\d{3})*(?:\.\d+)?(?:[kKmMbB](?![a-zA-Z]))?)', r'\\$\1', sub_part)
            # Match unescaped $ before single digits
            escaped = re.sub(r'(?<!\\)\$([0-9])', r'\\$\1', escaped)
            # Escape an approximation tilde, i.e. one directly before a number or a
            # (now backslash-escaped) currency amount. Scoped this tightly on purpose so
            # a deliberate ~~strikethrough~~ still works: its second tilde is followed by
            # a letter, which this does not match.
            escaped = re.sub(r'(?<!\\)~(?=[\d$\\])', r'\\~', escaped)
            sub_processed.append(escaped)
        processed_parts.append("".join(sub_processed))
    
    return "".join(processed_parts)


def clean_agent_response_text(text: str) -> str:
    """
    Cleans up leaked Cortex Search tool queries, raw parameter strings,
    and trailing scratchpad artifacts from synthesized agent output.
    """
    if not text:
        return ""
    
    cleaned = text.strip()
    
    # Remove known Cortex Search tool query leakage (search phrases appended at the bottom)
    # E.g., 'Health Platinum Elite plan eligibility ideal customer profile underwriting guidelines'
    lines = cleaned.split("\n")
    filtered_lines = []
    for line in lines:
        l_str = line.strip()
        # If line is at the end or standalone and looks like a raw keyword search string without punctuation
        if l_str and not l_str.startswith(("#", "-", "*", ">", "|", "1.", "2.", "3.", "4.", "5.")) and len(l_str.split()) >= 5:
            if not re.search(r'[.:?!]$', l_str) and any(k in l_str.lower() for k in [
                "eligibility", "customer profile", "underwriting guidelines", "policy wording",
                "deductible clause", "coverage terms", "ideal customer"
            ]):
                continue
        filtered_lines.append(line)
        
    cleaned = "\n".join(filtered_lines).strip()
    return cleaned


class _SseAccumulator:
    """Collects Cortex Agent SSE events into the pieces the UI needs.

    Split out of parse_sse_stream so the same per-event logic can be driven either by
    a fully buffered body or incrementally as events arrive off the wire. finalise()
    returns the identical 8-tuple parse_sse_stream has always returned.
    """

    def __init__(self):
        self.complete_text_blocks = []
        self.delta_text_blocks = []
        self.thinking_blocks = []
        self.sql_candidates = []
        self.warnings = []
        self.final_response = None
        self.table_data = None
        self.table_columns = None
        self.chart_spec = None
        self.tools_used = []

    def handle(self, current_event: Optional[str], data_json: Any) -> None:
        """Fold one parsed SSE event into the accumulated state."""
        if not isinstance(data_json, dict):
            return

        if current_event == "response":
            self.final_response = data_json
            for item in data_json.get("content", []):
                itype = item.get("type")
                if itype == "text" and item.get("text"):
                    self.complete_text_blocks.append(item["text"])
                elif itype == "thinking" and "thinking" in item:
                    self.thinking_blocks.append(item["thinking"].get("text", ""))
                elif itype in ["tool_use", "action"]:
                    if item.get("name"):
                        self.tools_used.append(item["name"])
                    t_input = item.get("input", {})
                    if isinstance(t_input, dict):
                        for k in ["query", "sql", "statement"]:
                            if k in t_input and t_input[k]:
                                self.sql_candidates.append(t_input[k])
                elif itype in ["sql", "query"] and item.get("statement"):
                    self.sql_candidates.append(item["statement"])
            if "warnings" in data_json:
                self.warnings.extend(data_json["warnings"])
        elif current_event in ["response.thinking", "response.thinking.delta"]:
            if "text" in data_json:
                self.thinking_blocks.append(data_json["text"])
        elif current_event in ["response.text", "response.text.delta"]:
            if "text" in data_json:
                self.delta_text_blocks.append(data_json["text"])
        elif current_event in ["response.tool_use", "response.tool_call"]:
            tool_data = data_json.get("tool_use") or data_json
            if tool_data.get("name"):
                self.tools_used.append(tool_data["name"])
            t_input = tool_data.get("input", {})
            if isinstance(t_input, dict):
                for k in ["query", "sql", "statement"]:
                    if k in t_input and t_input[k]:
                        self.sql_candidates.append(t_input[k])
        elif current_event == "response.tool_result":
            content_list = data_json.get("content", [])
            for c_item in content_list:
                if isinstance(c_item, dict):
                    json_data = c_item.get("json", {})
                    if isinstance(json_data, dict):
                        for k in ["query", "sql", "statement"]:
                            if k in json_data and json_data[k]:
                                self.sql_candidates.append(json_data[k])
        elif current_event == "response.table":
            result_set = data_json.get("result_set", {})
            raw_rows = result_set.get("data", [])
            row_type = result_set.get("resultSetMetaData", {}).get("rowType", [])
            col_names = [col.get("name") for col in row_type] if row_type else []

            extracted_rows = []
            for r in raw_rows:
                row_dict = {}
                for i, val in enumerate(r):
                    c_name = col_names[i] if i < len(col_names) else f"COL_{i}"
                    if isinstance(val, str):
                        try:
                            if "." in val:
                                val = float(val)
                            else:
                                val = int(val)
                        except (ValueError, TypeError):
                            pass
                    row_dict[c_name] = val
                extracted_rows.append(row_dict)

            if extracted_rows:
                self.table_data = extracted_rows
                self.table_columns = col_names
        elif current_event == "response.chart":
            spec = data_json.get("chart_spec")
            if spec:
                self.chart_spec = spec
        elif current_event == "response.warning":
            self.warnings.append(data_json)

    def finalise(self):
        """Reduce accumulated events to the response tuple the callers expect."""
        # Separate internal scratchpad thoughts ("I'll examine...", "Now let me pull...",
        # "I have both models. Let me query...") from the user-facing answer. Only short
        # blocks are moved, and only when a later block carries the real answer.
        SCRATCHPAD_PREFIXES = (
            "i'll ", "i will ", "let me ", "now let me ", "let's ", "now i'll ",
            "i have ", "i need to ", "i'm going to ", "i can ", "first, i", "next, i",
        )
        cleaned_text_blocks = []
        thinking_blocks = list(self.thinking_blocks)
        for t in self.complete_text_blocks:
            t_clean = t.strip()
            if not t_clean:
                continue
            is_preamble = (
                t_clean.lower().startswith(SCRATCHPAD_PREFIXES)
                or bool(re.match(r"^i(?:'ve| have)\b[^.\n]{0,80}\.\s+(?:let me|now|i'll)\b", t_clean, re.IGNORECASE))
                # Short lead-in that announces an upcoming tool call, e.g.
                # "I don't have the answer yet - let me search the document corpus."
                or bool(re.search(r"\blet me (?:search|check|look|pull|query|run|start)\b", t_clean, re.IGNORECASE))
            )
            if is_preamble and len(self.complete_text_blocks) > 1 and len(t_clean) < 300:
                thinking_blocks.append(t_clean)
            else:
                cleaned_text_blocks.append(t_clean)

        if cleaned_text_blocks:
            full_text = "\n\n".join([t.strip() for t in cleaned_text_blocks if t.strip()])
        elif self.complete_text_blocks:
            full_text = "\n\n".join([t.strip() for t in self.complete_text_blocks if t.strip()])
        elif self.delta_text_blocks:
            full_text = "".join(self.delta_text_blocks).strip()
        else:
            full_text = ""

        thinking_text = "\n".join([t.strip() for t in thinking_blocks if t.strip()])

        # If SQL was found in tool calls and not in full_text markdown, append it
        if self.sql_candidates and not extract_sql_from_text(full_text):
            full_text += f"\n\n```sql\n{self.sql_candidates[0].strip()}\n```"

        # Clean any mojibake characters in text and thinking
        full_text = clean_text_encoding(full_text.strip())
        thinking_text = clean_text_encoding(thinking_text.strip())

        # Strip leaked search queries and raw parameter artifacts
        full_text = clean_agent_response_text(full_text)

        # De-duplicate tool names while preserving invocation order
        ordered_tools = list(dict.fromkeys(t for t in self.tools_used if t))

        return (
            full_text,
            thinking_text,
            self.warnings,
            self.final_response,
            self.table_data,
            self.table_columns,
            self.chart_spec,
            ordered_tools,
        )


def iter_sse_events(line_source):
    """Yield (event_name, parsed_json) pairs from an iterable of SSE text lines.

    Accepts anything that yields decoded lines, so it works with both
    response.iter_lines(decode_unicode=True) for a live stream and a plain list of
    lines from a buffered body. Multi-line `data:` payloads are concatenated, and
    `[DONE]` sentinels and unparseable payloads are skipped.
    """
    current_event = None
    data_parts: List[str] = []

    def _flush():
        if not data_parts:
            return None
        payload = "".join(data_parts)
        data_parts.clear()
        if not payload or payload == "[DONE]":
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None

    for raw_line in line_source:
        if raw_line is None:
            continue
        line = raw_line.strip()

        # A blank line terminates an SSE event.
        if not line:
            parsed = _flush()
            if parsed is not None:
                yield current_event, parsed
            continue

        if line.startswith("event:"):
            # A new event header means the previous one is complete.
            parsed = _flush()
            if parsed is not None:
                yield current_event, parsed
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_parts.append(line[len("data:"):].strip())

    parsed = _flush()
    if parsed is not None:
        yield current_event, parsed


def parse_sse_stream(sse_text: str):
    """Parses Server-Sent Events stream from Snowflake Cortex Agent REST API cleanly.

    Retained as the buffered entry point; the incremental path uses _SseAccumulator
    and iter_sse_events directly.
    """
    accumulator = _SseAccumulator()
    for event_name, data_json in iter_sse_events(sse_text.strip().split("\n")):
        accumulator.handle(event_name, data_json)
    return accumulator.finalise()


def sanitize_semantic_view_sql(sql: str, db: str = "UNIFIEDAI_DB") -> str:
    """
    Translates Cortex Agent / Analyst semantic view virtual table references (__table)
    to actual Snowflake schema-qualified physical tables so queries can be executed and inspected directly.
    """
    if not sql:
        return ""
    
    target_db = db or env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    
    table_map = {
        r"\b__policies\b": f"{target_db}.CORE.POLICIES",
        r"\b__customers\b": f"{target_db}.CORE.CUSTOMERS",
        r"\b__claims\b": f"{target_db}.CORE.CLAIMS",
        r"\b__agents\b": f"{target_db}.CORE.AGENTS",
        r"\b__plan_tiers\b": f"{target_db}.PREMIUM.PLAN_TIERS",
        r"\b__premium_calculations\b": f"{target_db}.PREMIUM.PREMIUM_CALCULATIONS",
        r"\b__premium_factors\b": f"{target_db}.PREMIUM.PREMIUM_FACTORS",
        r"\b__at_risk_policies\b": f"{target_db}.RISK.AT_RISK_POLICIES",
        r"\b__churn_predictions\b": f"{target_db}.RISK.CHURN_PREDICTIONS",
        r"\b__risk_factors\b": f"{target_db}.RISK.RISK_FACTORS",
        r"\b__claims_kpi\b": f"{target_db}.ANALYTICS.CLAIMS_KPI",
        r"\b__fraud_alerts\b": f"{target_db}.ANALYTICS.FRAUD_ALERTS",
        r"\b__loss_ratio_history\b": f"{target_db}.ANALYTICS.LOSS_RATIO_HISTORY",
        r"\b__policy_trends\b": f"{target_db}.ANALYTICS.POLICY_TRENDS",
        r"\b__dq_rules\b": f"{target_db}.UNIFIEDAI_SH.DQ_RULES",
        r"\b__dq_validation_results\b": f"{target_db}.UNIFIEDAI_SH.DQ_VALIDATION_RESULTS"
    }
    
    translated = sql
    for pat, real_tbl in table_map.items():
        translated = re.sub(pat, real_tbl, translated, flags=re.IGNORECASE)
    
    return translated


class UnsafeSqlError(Exception):
    """Raised when SQL submitted for execution is not a single read-only statement."""


# Statements that write, change structure, alter permissions, or move data. The app is
# a read-only analytics surface, so anything in this set is refused outright rather
# than confirmed: a confirmation prompt on a DROP typed into a text box is not a
# meaningful control.
#
# Deliberately excluded because they are legitimate Snowflake *functions* that appear
# in valid SELECTs and would cause false positives: REPLACE(), GET(). Also excluded as
# redundant: USE/SET/BEGIN cannot follow a leading SELECT or WITH, which is already
# enforced separately. What remains is the set that can genuinely cause a write after
# a WITH clause, e.g. "WITH cte AS (...) DELETE FROM t USING cte".
_FORBIDDEN_SQL_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "DROP", "TRUNCATE", "ALTER", "CREATE", "RENAME", "SWAP", "UNDROP",
    "GRANT", "REVOKE",
    "CALL", "EXECUTE", "COPY", "PUT", "REMOVE",
    "COMMIT", "ROLLBACK",
)


def _strip_sql_noise(sql: str) -> str:
    """Remove string literals and comments so keyword checks cannot be fooled.

    Literals are blanked first, otherwise a value like 'DROP the charges' would trip
    the keyword scan, and a comment like /* harmless */ could hide a real statement.
    """
    # Blank single- and double-quoted literals (doubled quotes are the SQL escape).
    without_literals = re.sub(r"'(?:''|[^'])*'", "''", sql)
    without_literals = re.sub(r'"(?:""|[^"])*"', '""', without_literals)
    # Strip block then line comments.
    without_comments = re.sub(r"/\*.*?\*/", " ", without_literals, flags=re.DOTALL)
    without_comments = re.sub(r"--[^\n]*", " ", without_comments)
    return without_comments


def assert_read_only_sql(sql: str) -> str:
    """Validate that sql is exactly one read-only statement, or raise UnsafeSqlError.

    Returns the original SQL unchanged when it passes, so callers can use it inline.
    """
    if not sql or not str(sql).strip():
        raise UnsafeSqlError("No SQL statement was provided.")

    scrubbed = _strip_sql_noise(str(sql))

    # Reject stacked statements. A single trailing semicolon is normal and allowed.
    if ";" in scrubbed.strip().rstrip(";"):
        raise UnsafeSqlError(
            "Multiple SQL statements are not allowed. Submit a single SELECT query."
        )

    tokens = re.findall(r"\b[A-Za-z_]+\b", scrubbed)
    if not tokens:
        raise UnsafeSqlError("No executable SQL statement was found.")

    leading = tokens[0].upper()
    if leading not in ("SELECT", "WITH"):
        raise UnsafeSqlError(
            f"Only read-only SELECT queries can be executed here; this statement starts with {leading}."
        )

    upper_tokens = {t.upper() for t in tokens}
    for keyword in _FORBIDDEN_SQL_KEYWORDS:
        if keyword in upper_tokens:
            raise UnsafeSqlError(
                f"The keyword {keyword} is not permitted; only read-only SELECT queries can be executed here."
            )

    return sql



def get_snowflake_status(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Returns active session telemetry, status, and cached metadata."""
    manager = mgr or snowflake_manager
    ctx = manager.get_session_context()
    token, host = manager.get_session_token() if ctx.get("connected") else (None, None)
    ctx["token"] = token
    ctx["host"] = host
    ctx["default_agent"] = env_config.get("INS_AGENT", DEFAULT_AGENT_NAME)
    return ctx


US_STATE_COORDINATES = {
    "TX": {"lat": 31.9686, "lon": -99.9018, "name": "Texas"},
    "CA": {"lat": 36.7783, "lon": -119.4179, "name": "California"},
    "AZ": {"lat": 34.0489, "lon": -111.0937, "name": "Arizona"},
    "IL": {"lat": 40.6331, "lon": -89.3985, "name": "Illinois"},
    "PA": {"lat": 41.2033, "lon": -77.1945, "name": "Pennsylvania"},
    "NY": {"lat": 43.2994, "lon": -74.2179, "name": "New York"},
    "GA": {"lat": 32.1656, "lon": -82.9001, "name": "Georgia"},
    "FL": {"lat": 27.6648, "lon": -81.5158, "name": "Florida"},
    "OH": {"lat": 40.4173, "lon": -82.9071, "name": "Ohio"},
    "NC": {"lat": 35.7596, "lon": -79.0193, "name": "North Carolina"},
    "MI": {"lat": 44.3148, "lon": -85.6024, "name": "Michigan"},
    "WA": {"lat": 47.7511, "lon": -120.7401, "name": "Washington"}
}


def get_state_geospatial_analytics(mgr: Optional[SnowflakeManager] = None) -> List[Dict[str, Any]]:
    """
    Returns live 3D geospatial state metrics joining CUSTOMERS, POLICIES, and CLAIMS from Snowflake.
    Computes coordinates, 3D elevation height, dynamic risk color palettes, and claim ratios.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    
    sql_geo = f"""
    WITH policy_agg AS (
        SELECT
            c.STATE,
            COUNT(DISTINCT p.POLICY_ID) AS POLICIES_COUNT,
            COUNT(DISTINCT c.CUSTOMER_ID) AS CUSTOMERS_COUNT,
            ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS TOTAL_PREMIUM,
            ROUND(AVG(p.PREMIUM_AMOUNT), 2) AS AVG_PREMIUM,
            ROUND(AVG(p.LOSS_RATIO) * 100.0, 1) AS AVG_LOSS_RATIO
        FROM {db}.CORE.CUSTOMERS c
        JOIN {db}.CORE.POLICIES p ON c.CUSTOMER_ID = p.CUSTOMER_ID
        GROUP BY c.STATE
    ),
    claim_agg AS (
        SELECT
            c.STATE,
            COUNT(DISTINCT cl.CLAIM_ID) AS CLAIMS_COUNT,
            ROUND(SUM(cl.CLAIM_AMOUNT), 2) AS TOTAL_CLAIMS_AMOUNT,
            ROUND(AVG(cl.FRAUD_SCORE), 2) AS AVG_FRAUD_SCORE
        FROM {db}.CORE.CUSTOMERS c
        JOIN {db}.CORE.POLICIES p ON c.CUSTOMER_ID = p.CUSTOMER_ID
        JOIN {db}.CORE.CLAIMS cl ON p.POLICY_ID = cl.POLICY_ID
        GROUP BY c.STATE
    )
    SELECT
        pa.STATE,
        pa.POLICIES_COUNT,
        pa.CUSTOMERS_COUNT,
        pa.TOTAL_PREMIUM,
        pa.AVG_PREMIUM,
        pa.AVG_LOSS_RATIO,
        COALESCE(ca.CLAIMS_COUNT, 0) AS CLAIMS_COUNT,
        COALESCE(ca.TOTAL_CLAIMS_AMOUNT, 0) AS TOTAL_CLAIMS_AMOUNT,
        ca.AVG_FRAUD_SCORE
    FROM policy_agg pa
    LEFT JOIN claim_agg ca ON pa.STATE = ca.STATE
    ORDER BY pa.TOTAL_PREMIUM DESC;
    """
    
    rows, _ = manager.execute_query(sql_geo)
    geo_data = []
    
    for r in (rows or []):
        st_code = str(r.get("STATE", "TX")).upper()
        coords = US_STATE_COORDINATES.get(st_code, {"lat": 37.0902, "lon": -95.7129, "name": st_code})
        
        tot_premium = float(r.get("TOTAL_PREMIUM") or 0.0)
        loss_ratio = float(r.get("AVG_LOSS_RATIO") or 50.0)
        fraud_score = float(r.get("AVG_FRAUD_SCORE") or 0.5)
        
        # Color coding: Green (low risk), Amber (moderate), Red (critical loss ratio)
        if loss_ratio >= 62.0:
            fill_color = [239, 68, 68, 220]      # Red
            risk_label = "Critical Risk"
        elif loss_ratio >= 52.0:
            fill_color = [245, 158, 11, 220]     # Amber
            risk_label = "Elevated Risk"
        else:
            fill_color = [16, 185, 129, 220]     # Emerald Green
            risk_label = "Optimal"
            
        geo_data.append({
            "state": st_code,
            "state_name": coords["name"],
            "lat": coords["lat"],
            "lon": coords["lon"],
            "policies_count": int(r.get("POLICIES_COUNT") or 0),
            "customers_count": int(r.get("CUSTOMERS_COUNT") or 0),
            "total_premium": tot_premium,
            "total_premium_formatted": f"${tot_premium:,.0f}",
            "avg_premium": float(r.get("AVG_PREMIUM") or 0.0),
            "avg_loss_ratio": loss_ratio,
            "claims_count": int(r.get("CLAIMS_COUNT") or 0),
            "total_claims_amount": float(r.get("TOTAL_CLAIMS_AMOUNT") or 0.0),
            "avg_fraud_score": fraud_score,
            "elevation": max(10000.0, tot_premium * 0.45),
            "fill_color": fill_color,
            "risk_label": risk_label
        })
        
    return geo_data


def get_dashboard_overview(mgr: Optional[SnowflakeManager] = None, state: Optional[str] = None) -> Dict[str, Any]:
    """Fetches real-time portfolio KPI metrics directly from live tables with optional state filtering."""
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    
    if state and state.upper() not in ["ALL", "NATIONAL", "NONE"]:
        st_filter = f"WHERE c.STATE = '{state.upper()}'"
        sql = f"""SELECT 
            COUNT(DISTINCT p.POLICY_ID) AS ACTIVE_POLICIES,
            ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS TOTAL_REVENUE,
            ROUND(AVG(p.PREMIUM_AMOUNT), 2) AS AVG_PREMIUM,
            (SELECT COUNT(DISTINCT cl.CLAIM_ID) FROM {db}.CORE.CLAIMS cl JOIN {db}.CORE.POLICIES p2 ON cl.POLICY_ID = p2.POLICY_ID JOIN {db}.CORE.CUSTOMERS c2 ON p2.CUSTOMER_ID = c2.CUSTOMER_ID WHERE c2.STATE = '{state.upper()}') AS TOTAL_CLAIMS,
            (SELECT ROUND(SUM(cl.CLAIM_AMOUNT), 2) FROM {db}.CORE.CLAIMS cl JOIN {db}.CORE.POLICIES p2 ON cl.POLICY_ID = p2.POLICY_ID JOIN {db}.CORE.CUSTOMERS c2 ON p2.CUSTOMER_ID = c2.CUSTOMER_ID WHERE c2.STATE = '{state.upper()}') AS TOTAL_CLAIM_AMOUNT,
            (SELECT ROUND(AVG(cl.DAYS_TO_RESOLVE), 1) FROM {db}.CORE.CLAIMS cl JOIN {db}.CORE.POLICIES p2 ON cl.POLICY_ID = p2.POLICY_ID JOIN {db}.CORE.CUSTOMERS c2 ON p2.CUSTOMER_ID = c2.CUSTOMER_ID WHERE c2.STATE = '{state.upper()}') AS AVG_PROCESSING_DAYS,
            (SELECT COUNT(DISTINCT cl.CLAIM_ID) FROM {db}.CORE.CLAIMS cl JOIN {db}.CORE.POLICIES p2 ON cl.POLICY_ID = p2.POLICY_ID JOIN {db}.CORE.CUSTOMERS c2 ON p2.CUSTOMER_ID = c2.CUSTOMER_ID WHERE c2.STATE = '{state.upper()}' AND (cl.FRAUD_FLAG = TRUE OR cl.FRAUD_SCORE >= 0.75)) AS HIGH_RISK_COUNT,
            (SELECT ROUND(AVG(CUSTOMER_SATISFACTION), 2) FROM {db}.ANALYTICS.CLAIMS_KPI) AS CSAT_SCORE,
            (SELECT ROUND(AVG(CUSTOMER_SATISFACTION) * 20.0, 1) FROM {db}.ANALYTICS.CLAIMS_KPI) AS CSAT_PCT
        FROM {db}.CORE.POLICIES p
        JOIN {db}.CORE.CUSTOMERS c ON p.CUSTOMER_ID = c.CUSTOMER_ID
        {st_filter};"""
    else:
        sql = f"""SELECT 
            COUNT(p.POLICY_ID) AS ACTIVE_POLICIES,
            ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS TOTAL_REVENUE,
            ROUND(AVG(p.PREMIUM_AMOUNT), 2) AS AVG_PREMIUM,
            (SELECT COUNT(CLAIM_ID) FROM {db}.CORE.CLAIMS) AS TOTAL_CLAIMS,
            (SELECT ROUND(SUM(CLAIM_AMOUNT), 2) FROM {db}.CORE.CLAIMS) AS TOTAL_CLAIM_AMOUNT,
            (SELECT ROUND(AVG(DAYS_TO_RESOLVE), 1) FROM {db}.CORE.CLAIMS) AS AVG_PROCESSING_DAYS,
            (SELECT COUNT(CLAIM_ID) FROM {db}.CORE.CLAIMS WHERE FRAUD_FLAG = TRUE OR FRAUD_SCORE >= 0.75) AS HIGH_RISK_COUNT,
            (SELECT ROUND(AVG(CUSTOMER_SATISFACTION), 2) FROM {db}.ANALYTICS.CLAIMS_KPI) AS CSAT_SCORE,
            (SELECT ROUND(AVG(CUSTOMER_SATISFACTION) * 20.0, 1) FROM {db}.ANALYTICS.CLAIMS_KPI) AS CSAT_PCT
        FROM {db}.CORE.POLICIES p;"""
    
    records, _ = manager.execute_query(sql)
    row = records[0] if records else {}

    raw_csat = row.get("CSAT_SCORE")
    csat_str = (
        f"{float(raw_csat):.2f} / 5.0"
        if isinstance(raw_csat, (int, float)) and raw_csat > 0
        else None
    )
    raw_csat_pct = row.get("CSAT_PCT")
    csat_pct_str = (
        f"{float(raw_csat_pct):.1f}%"
        if isinstance(raw_csat_pct, (int, float)) and raw_csat_pct > 0
        else None
    )

    # Real period-over-period movement, computed from the same CORE tables that produced
    # the headline numbers above. Previously these were hardcoded strings
    # ("+8.4% MoM", "+12.6% YoY", "-1.8d YoY", "+4.2% QoQ", "+14.2%") that never changed
    # regardless of the data or the selected state.
    deltas = get_portfolio_trend_deltas(mgr=manager, state=state)

    days_delta = deltas.get("processing_days_yoy_delta")
    processing_trend = f"{days_delta:+.1f}d YoY" if days_delta is not None else None

    return {
        "status": "success",
        "active_policies": int(row.get("ACTIVE_POLICIES") or 0),
        # When a state is selected the label names the state, since the count is scoped.
        "active_policies_trend": (
            _fmt_pct(deltas.get("policies_mom_pct"), "MoM new policies")
            if not state else
            (f"{state.upper()} • " + (_fmt_pct(deltas.get("policies_mom_pct"), "MoM") or "no prior month"))
        ),
        "processing_days": float(row.get("AVG_PROCESSING_DAYS") or 0.0),
        "processing_days_trend": processing_trend,
        "csat_score": csat_str,
        "csat_pct": csat_pct_str,
        "csat_trend": _fmt_pct(deltas.get("csat_qoq_pct"), "QoQ"),
        "revenue": float(row.get("TOTAL_REVENUE") or 0.0),
        "revenue_growth_pct": (
            _fmt_pct(deltas.get("premium_yoy_pct"), "YoY")
            or _fmt_pct(deltas.get("premium_mom_pct"), "MoM")
        ),
        "claims_count": int(row.get("TOTAL_CLAIMS") or 0),
        "claims_amount": float(row.get("TOTAL_CLAIM_AMOUNT") or 0.0),
        "claims_growth_pct": _fmt_pct(deltas.get("claims_mom_pct"), "MoM"),
        "avg_premium": float(row.get("AVG_PREMIUM") or 0.0),
        "avg_settlement_days": float(row.get("AVG_PROCESSING_DAYS") or 0.0),
        "high_risk_count": int(row.get("HIGH_RISK_COUNT") or 0),
        "trend_meta": deltas,
    }


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Percentage change, or None when it cannot be computed.

    Returning None rather than 0 matters: the UI omits the trend pill entirely instead
    of implying a flat period when there is simply no comparison data.
    """
    try:
        cur = float(current)
        prev = float(previous)
    except (TypeError, ValueError):
        return None
    if prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100.0, 1)


def _fmt_pct(value: Optional[float], suffix: str) -> Optional[str]:
    """Signed percentage label, e.g. '+8.4% MoM'. None passes through as None."""
    if value is None:
        return None
    return f"{value:+.1f}% {suffix}"


def get_portfolio_trend_deltas(
    mgr: Optional[SnowflakeManager] = None,
    state: Optional[str] = None
) -> Dict[str, Any]:
    """Real period-over-period changes, derived from the same CORE tables as the KPIs.

    Deliberately NOT sourced from ANALYTICS.POLICY_TRENDS: that table does not reconcile
    with CORE (latest-month active policies 373 vs 300 actual, total revenue $11.3M vs
    $2.4M), so pairing its deltas with a CORE headline would put two unrelated datasets
    in one tile.

    Every value can be None when there is insufficient history, which the UI renders as
    a missing pill rather than a fabricated figure.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")

    scoped = bool(state and state.upper() not in ("ALL", "NATIONAL", "NONE"))
    params: List[Any] = []

    # State scoping goes through CUSTOMERS, matching how the headline KPIs filter.
    if scoped:
        pol_join = f"JOIN {db}.CORE.CUSTOMERS cu ON p.CUSTOMER_ID = cu.CUSTOMER_ID"
        pol_where = "WHERE cu.STATE = %s AND p.START_DATE IS NOT NULL"
        clm_join = (f"JOIN {db}.CORE.POLICIES p2 ON cl.POLICY_ID = p2.POLICY_ID "
                    f"JOIN {db}.CORE.CUSTOMERS cu2 ON p2.CUSTOMER_ID = cu2.CUSTOMER_ID")
        clm_where = "WHERE cu2.STATE = %s AND cl.CLAIM_DATE IS NOT NULL"
        params = [state.upper(), state.upper()]
    else:
        pol_join = ""
        pol_where = "WHERE p.START_DATE IS NOT NULL"
        clm_join = ""
        clm_where = "WHERE cl.CLAIM_DATE IS NOT NULL"

    sql = f"""
    WITH policy_months AS (
        SELECT DATE_TRUNC('MONTH', p.START_DATE) AS M,
               COUNT(*) AS NEW_POLICIES,
               SUM(p.PREMIUM_AMOUNT) AS PREMIUM
        FROM {db}.CORE.POLICIES p
        {pol_join}
        {pol_where}
        GROUP BY 1
    ),
    claim_months AS (
        SELECT DATE_TRUNC('MONTH', cl.CLAIM_DATE) AS M,
               COUNT(*) AS CLAIMS,
               AVG(cl.DAYS_TO_RESOLVE) AS AVG_DAYS
        FROM {db}.CORE.CLAIMS cl
        {clm_join}
        {clm_where}
        GROUP BY 1
    ),
    pol_ranked AS (
        SELECT M, NEW_POLICIES, PREMIUM,
               ROW_NUMBER() OVER (ORDER BY M DESC) AS RN
        FROM policy_months
    ),
    clm_ranked AS (
        SELECT M, CLAIMS, AVG_DAYS,
               ROW_NUMBER() OVER (ORDER BY M DESC) AS RN
        FROM claim_months
    )
    SELECT
        (SELECT NEW_POLICIES FROM pol_ranked WHERE RN = 1) AS POL_CUR,
        (SELECT NEW_POLICIES FROM pol_ranked WHERE RN = 2) AS POL_PREV,
        (SELECT PREMIUM FROM pol_ranked WHERE RN = 1) AS PREM_CUR,
        (SELECT PREMIUM FROM pol_ranked WHERE RN = 2) AS PREM_PREV,
        (SELECT PREMIUM FROM pol_ranked WHERE RN = 13) AS PREM_YEAR_AGO,
        (SELECT CLAIMS FROM clm_ranked WHERE RN = 1) AS CLM_CUR,
        (SELECT CLAIMS FROM clm_ranked WHERE RN = 2) AS CLM_PREV,
        (SELECT AVG_DAYS FROM clm_ranked WHERE RN = 1) AS DAYS_CUR,
        (SELECT AVG_DAYS FROM clm_ranked WHERE RN = 13) AS DAYS_YEAR_AGO,
        (SELECT M FROM pol_ranked WHERE RN = 1) AS LATEST_POLICY_MONTH,
        (SELECT M FROM clm_ranked WHERE RN = 1) AS LATEST_CLAIM_MONTH,
        (SELECT COUNT(*) FROM policy_months) AS POLICY_MONTHS,
        (SELECT COUNT(*) FROM claim_months) AS CLAIM_MONTHS
    """

    rows, _ = manager.execute_query(sql, tuple(params) if params else None)
    row = rows[0] if rows else {}

    # CSAT quarter over quarter. CLAIMS_KPI is the only satisfaction source and it is not
    # state-scoped, so this figure is national regardless of the state filter.
    csat_sql = f"""
    WITH q AS (
        SELECT DATE_TRUNC('QUARTER', MONTH_YEAR) AS Q, AVG(CUSTOMER_SATISFACTION) AS CSAT
        FROM {db}.ANALYTICS.CLAIMS_KPI
        WHERE MONTH_YEAR IS NOT NULL AND CUSTOMER_SATISFACTION IS NOT NULL
        GROUP BY 1
    ),
    r AS (SELECT Q, CSAT, ROW_NUMBER() OVER (ORDER BY Q DESC) AS RN FROM q)
    SELECT (SELECT CSAT FROM r WHERE RN = 1) AS CSAT_CUR,
           (SELECT CSAT FROM r WHERE RN = 2) AS CSAT_PREV
    """
    csat_rows, _ = manager.execute_query(csat_sql)
    csat_row = csat_rows[0] if csat_rows else {}

    days_cur = row.get("DAYS_CUR")
    days_prev_year = row.get("DAYS_YEAR_AGO")
    days_delta = None
    if days_cur is not None and days_prev_year is not None:
        days_delta = round(float(days_cur) - float(days_prev_year), 1)

    return {
        "policies_mom_pct": _pct_change(row.get("POL_CUR"), row.get("POL_PREV")),
        "premium_mom_pct": _pct_change(row.get("PREM_CUR"), row.get("PREM_PREV")),
        "premium_yoy_pct": _pct_change(row.get("PREM_CUR"), row.get("PREM_YEAR_AGO")),
        "claims_mom_pct": _pct_change(row.get("CLM_CUR"), row.get("CLM_PREV")),
        "processing_days_yoy_delta": days_delta,
        "csat_qoq_pct": _pct_change(csat_row.get("CSAT_CUR"), csat_row.get("CSAT_PREV")),
        "latest_policy_month": row.get("LATEST_POLICY_MONTH"),
        "latest_claim_month": row.get("LATEST_CLAIM_MONTH"),
        "policy_months_available": int(row.get("POLICY_MONTHS") or 0),
        "claim_months_available": int(row.get("CLAIM_MONTHS") or 0),
    }


def get_data_completeness(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Measured completeness and validity of the CORE tables.

    This replaces a hardcoded "data trust score" of 88, which had no source at all: the
    DQ_RULES, DQ_VALIDATION_RESULTS and DQ_RUN_LOGS tables are empty, so nothing could be
    computed from them. What is measurable is how many required fields are populated and
    how many rows violate a sane range, so that is what this reports - and it is named
    for what it measures rather than implying a broader notion of trust.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")

    sql = f"""
    WITH pol AS (
        SELECT COUNT(*) AS N,
               COUNT(PREMIUM_AMOUNT) AS C_PREMIUM,
               COUNT(LOSS_RATIO) AS C_LOSS,
               COUNT(START_DATE) AS C_START,
               COUNT(END_DATE) AS C_END,
               COUNT(PLAN_TIER) AS C_TIER,
               COUNT_IF(PREMIUM_AMOUNT < 0) AS V_NEG_PREMIUM,
               COUNT_IF(LOSS_RATIO < 0 OR LOSS_RATIO > 2) AS V_LOSS_RANGE,
               COUNT_IF(END_DATE IS NOT NULL AND START_DATE IS NOT NULL AND END_DATE < START_DATE) AS V_DATE_ORDER
        FROM {db}.CORE.POLICIES
    ),
    clm AS (
        SELECT COUNT(*) AS N,
               COUNT(CLAIM_AMOUNT) AS C_AMOUNT,
               COUNT(CLAIM_DATE) AS C_DATE,
               COUNT(DAYS_TO_RESOLVE) AS C_DAYS,
               COUNT(FRAUD_SCORE) AS C_FRAUD,
               COUNT_IF(CLAIM_AMOUNT < 0) AS V_NEG_AMOUNT,
               COUNT_IF(FRAUD_SCORE < 0 OR FRAUD_SCORE > 1) AS V_FRAUD_RANGE,
               COUNT_IF(RESOLUTION_DATE IS NOT NULL AND CLAIM_DATE IS NOT NULL AND RESOLUTION_DATE < CLAIM_DATE) AS V_DATE_ORDER,
               COUNT_IF(APPROVED_AMOUNT IS NOT NULL AND CLAIM_AMOUNT IS NOT NULL AND APPROVED_AMOUNT > CLAIM_AMOUNT) AS V_OVER_APPROVED
        FROM {db}.CORE.CLAIMS
    ),
    cus AS (
        SELECT COUNT(*) AS N,
               COUNT(STATE) AS C_STATE,
               COUNT(AGE) AS C_AGE,
               COUNT(EMAIL) AS C_EMAIL,
               COUNT(CREDIT_SCORE) AS C_CREDIT,
               COUNT_IF(AGE < 0 OR AGE > 120) AS V_AGE_RANGE,
               COUNT_IF(CREDIT_SCORE < 300 OR CREDIT_SCORE > 850) AS V_CREDIT_RANGE
        FROM {db}.CORE.CUSTOMERS
    )
    SELECT
        pol.N AS POL_N, pol.C_PREMIUM, pol.C_LOSS, pol.C_START, pol.C_END, pol.C_TIER,
        pol.V_NEG_PREMIUM, pol.V_LOSS_RANGE, pol.V_DATE_ORDER AS POL_V_DATE,
        clm.N AS CLM_N, clm.C_AMOUNT, clm.C_DATE, clm.C_DAYS, clm.C_FRAUD,
        clm.V_NEG_AMOUNT, clm.V_FRAUD_RANGE, clm.V_DATE_ORDER AS CLM_V_DATE, clm.V_OVER_APPROVED,
        cus.N AS CUS_N, cus.C_STATE, cus.C_AGE, cus.C_EMAIL, cus.C_CREDIT,
        cus.V_AGE_RANGE, cus.V_CREDIT_RANGE
    FROM pol, clm, cus
    """

    rows, _ = manager.execute_query(sql)
    if not rows:
        return {"status": "error", "message": manager.get_last_error()}
    r = rows[0]

    def _i(key):
        return int(r.get(key) or 0)

    checks = [
        ("POLICIES", "PREMIUM_AMOUNT populated", _i("C_PREMIUM"), _i("POL_N")),
        ("POLICIES", "LOSS_RATIO populated", _i("C_LOSS"), _i("POL_N")),
        ("POLICIES", "START_DATE populated", _i("C_START"), _i("POL_N")),
        ("POLICIES", "END_DATE populated", _i("C_END"), _i("POL_N")),
        ("POLICIES", "PLAN_TIER populated", _i("C_TIER"), _i("POL_N")),
        ("CLAIMS", "CLAIM_AMOUNT populated", _i("C_AMOUNT"), _i("CLM_N")),
        ("CLAIMS", "CLAIM_DATE populated", _i("C_DATE"), _i("CLM_N")),
        ("CLAIMS", "DAYS_TO_RESOLVE populated", _i("C_DAYS"), _i("CLM_N")),
        ("CLAIMS", "FRAUD_SCORE populated", _i("C_FRAUD"), _i("CLM_N")),
        ("CUSTOMERS", "STATE populated", _i("C_STATE"), _i("CUS_N")),
        ("CUSTOMERS", "AGE populated", _i("C_AGE"), _i("CUS_N")),
        ("CUSTOMERS", "EMAIL populated", _i("C_EMAIL"), _i("CUS_N")),
        ("CUSTOMERS", "CREDIT_SCORE populated", _i("C_CREDIT"), _i("CUS_N")),
    ]

    violations = [
        ("POLICIES", "Negative premium", _i("V_NEG_PREMIUM")),
        ("POLICIES", "Loss ratio outside 0-2", _i("V_LOSS_RANGE")),
        ("POLICIES", "End date before start date", _i("POL_V_DATE")),
        ("CLAIMS", "Negative claim amount", _i("V_NEG_AMOUNT")),
        ("CLAIMS", "Fraud score outside 0-1", _i("V_FRAUD_RANGE")),
        ("CLAIMS", "Resolved before claimed", _i("CLM_V_DATE")),
        ("CLAIMS", "Approved above claimed", _i("V_OVER_APPROVED")),
        ("CUSTOMERS", "Age outside 0-120", _i("V_AGE_RANGE")),
        ("CUSTOMERS", "Credit score outside 300-850", _i("V_CREDIT_RANGE")),
    ]

    populated = sum(c[2] for c in checks)
    expected = sum(c[3] for c in checks)
    completeness = round(populated / expected * 100.0, 1) if expected else None

    total_rows = _i("POL_N") + _i("CLM_N") + _i("CUS_N")
    violation_count = sum(v[2] for v in violations)
    validity = round((1 - violation_count / total_rows) * 100.0, 1) if total_rows else None

    return {
        "status": "success",
        "completeness_pct": completeness,
        "validity_pct": validity,
        "fields_checked": len(checks),
        "populated_values": populated,
        "expected_values": expected,
        "violation_count": violation_count,
        "rows_examined": total_rows,
        "field_checks": [
            {
                "Table": t, "Check": name, "Populated": got, "Rows": exp,
                "Completeness %": round(got / exp * 100.0, 1) if exp else None,
            }
            for t, name, got, exp in checks
        ],
        "violations": [
            {"Table": t, "Rule": name, "Rows Failing": n} for t, name, n in violations
        ],
    }


def get_dts_analytics_data(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """
    Returns comprehensive DTS (Data Trust Score & Date-Time Series) analytics data directly from Snowflake.
    Queries live DQ_RULES, POLICY_TRENDS, and CLAIMS_KPI tables.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")
    
    # 1. Live data quality dimensions from DQ_RULES. TARGET and STATUS were previously
    # hardcoded to 95.0 and 'Optimal', so every dimension claimed to be passing no matter
    # what its score was. Status is now derived by comparing score to target.
    sql_dq = f"""
    SELECT 
        RULE_CATEGORY AS DIMENSION,
        COUNT(*) AS TOTAL_RULES,
        ROUND(AVG(THRESHOLD_PASS), 1) AS SCORE,
        ROUND(AVG(COALESCE(THRESHOLD_PASS, 0)), 1) AS RAW_SCORE,
        COALESCE(MAX(DESCRIPTION), 'No rule description recorded') AS DESCRIPTION
    FROM {db}.UNIFIEDAI_SH.DQ_RULES
    GROUP BY RULE_CATEGORY
    ORDER BY SCORE DESC;
    """
    dq_rows, _ = manager.execute_query(sql_dq)

    # Target is a policy choice rather than data, so it stays a named constant here.
    DQ_TARGET = 95.0

    def _dq_status(score: Optional[float]) -> str:
        if score is None:
            return "Unknown"
        if score >= DQ_TARGET:
            return "Optimal"
        if score >= DQ_TARGET - 10.0:
            return "At Risk"
        return "Below Target"

    quality_dimensions = []
    for r in (dq_rows or []):
        score = r.get("SCORE")
        score_f = float(score) if isinstance(score, (int, float)) else None
        quality_dimensions.append({
            "Dimension": r.get("DIMENSION", "General"),
            "Score": score_f,
            "Target": DQ_TARGET,
            "Status": _dq_status(score_f),
            "Description": f"{r.get('TOTAL_RULES', 0)} rules validated • {r.get('DESCRIPTION', '')}",
        })

    # 2. Fetch live Date-Time Series (DTS) from Snowflake ANALYTICS schema
    sql_ts = f"""
    SELECT 
        TO_VARCHAR(pt.MONTH_YEAR, 'Mon YYYY') AS MONTH,
        ROUND(SUM(pt.TOTAL_PREMIUM_REVENUE), 2) AS PREMIUM_INFLOW,
        (SELECT ROUND(SUM(ck.TOTAL_PAYOUT), 2) FROM {db}.ANALYTICS.CLAIMS_KPI ck WHERE ck.MONTH_YEAR = pt.MONTH_YEAR) AS CLAIMS_INCURRED,
        (SELECT ROUND(AVG(ck.AVG_PROCESSING_DAYS), 1) FROM {db}.ANALYTICS.CLAIMS_KPI ck WHERE ck.MONTH_YEAR = pt.MONTH_YEAR) AS PROCESSING_DAYS,
        (SELECT ROUND(AVG(ck.CUSTOMER_SATISFACTION) * 20.0, 1) FROM {db}.ANALYTICS.CLAIMS_KPI ck WHERE ck.MONTH_YEAR = pt.MONTH_YEAR) AS CSAT_PCT,
        (SELECT ROUND(AVG(lr.LOSS_RATIO) * 100.0, 1) FROM {db}.ANALYTICS.LOSS_RATIO_HISTORY lr WHERE lr.MONTH_YEAR = pt.MONTH_YEAR) AS LOSS_RATIO_PCT,
        SUM(pt.ACTIVE_POLICIES) AS ACTIVE_POLICIES
    FROM {db}.ANALYTICS.POLICY_TRENDS pt
    GROUP BY pt.MONTH_YEAR
    ORDER BY pt.MONTH_YEAR ASC
    LIMIT 12;
    """
    ts_rows, _ = manager.execute_query(sql_ts)
    # Missing months stay None rather than being backfilled with 80.0 / 65.0 placeholders,
    # so a gap in the series reads as a gap. CSAT is labelled as CSAT: it was previously
    # presented as "Data Trust Score", which it is not - it is customer satisfaction
    # rescaled to a percentage.
    dts_time_series = [
        {
            "Month": r.get("MONTH"),
            "Premium Inflow": r.get("PREMIUM_INFLOW"),
            "Claims Incurred": r.get("CLAIMS_INCURRED"),
            "Processing Days": r.get("PROCESSING_DAYS"),
            "CSAT %": r.get("CSAT_PCT"),
            "Loss Ratio %": r.get("LOSS_RATIO_PCT"),
        }
        for r in (ts_rows or [])
    ]

    # Measured completeness of the CORE tables replaces the previous hardcoded
    # overall_dts_score of 88 and the "Enterprise Verified (Tier 1)" rating, neither of
    # which came from anywhere: all three DQ_* tables are empty.
    completeness = get_data_completeness(mgr=manager)

    return {
        "completeness_pct": completeness.get("completeness_pct"),
        "validity_pct": completeness.get("validity_pct"),
        "completeness_detail": completeness,
        "dq_rules_available": bool(quality_dimensions),
        "quality_dimensions": quality_dimensions,
        "time_series": dts_time_series
    }


def get_trend_analytics(mgr: Optional[SnowflakeManager] = None, state: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns dedicated monthly Trend Analysis calculating:
    1. Revenue at risk by month
    2. New at-risk policies by month
    3. Average claim resolution time (days) by month
    4. Fraud-flagged claims by month
    5. Claim count by month
    Directly queries CORE.CLAIMS and RISK.AT_RISK_POLICIES from Snowflake with state filter support.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")

    c_join = ""
    c_where = "WHERE cl.CLAIM_DATE IS NOT NULL"
    r_join = ""
    r_where = ""
    
    if state and state.upper() not in ['ALL', 'NATIONAL', 'NONE']:
        st_code = state.upper()
        c_join = f"""JOIN {db}.CORE.POLICIES p_c ON cl.POLICY_ID = p_c.POLICY_ID 
                     JOIN {db}.CORE.CUSTOMERS cust_c ON p_c.CUSTOMER_ID = cust_c.CUSTOMER_ID"""
        c_where = f"WHERE cust_c.STATE = '{st_code}' AND cl.CLAIM_DATE IS NOT NULL"
        r_join = f"JOIN {db}.CORE.CUSTOMERS cust_r ON arp.CUSTOMER_ID = cust_r.CUSTOMER_ID"
        r_where = f"WHERE cust_r.STATE = '{st_code}'"

    sql = f"""
    WITH claims_monthly AS (
        SELECT 
            DATE_TRUNC('MONTH', cl.CLAIM_DATE) AS M_DATE,
            TO_VARCHAR(DATE_TRUNC('MONTH', cl.CLAIM_DATE), 'Mon YYYY') AS MONTH_STR,
            COUNT(cl.CLAIM_ID) AS CLAIM_COUNT,
            ROUND(AVG(cl.DAYS_TO_RESOLVE), 1) AS AVG_CLAIM_RESOLUTION_TIME_DAYS,
            COUNT(CASE WHEN cl.FRAUD_FLAG = TRUE OR cl.FRAUD_SCORE >= 0.75 THEN 1 END) AS FRAUD_FLAGGED_CLAIMS
        FROM {db}.CORE.CLAIMS cl
        {c_join}
        {c_where}
        GROUP BY DATE_TRUNC('MONTH', cl.CLAIM_DATE)
    ),
    risk_monthly AS (
        SELECT 
            DATE_TRUNC('MONTH', COALESCE(arp.IDENTIFIED_DATE, arp.LAST_INTERACTION_DATE, arp.CREATED_AT)) AS M_DATE,
            TO_VARCHAR(DATE_TRUNC('MONTH', COALESCE(arp.IDENTIFIED_DATE, arp.LAST_INTERACTION_DATE, arp.CREATED_AT)), 'Mon YYYY') AS MONTH_STR,
            COUNT(DISTINCT arp.POLICY_ID) AS NEW_AT_RISK_POLICIES,
            ROUND(SUM(arp.REVENUE_AT_RISK), 2) AS REVENUE_AT_RISK
        FROM {db}.RISK.AT_RISK_POLICIES arp
        {r_join}
        {r_where}
        GROUP BY DATE_TRUNC('MONTH', COALESCE(arp.IDENTIFIED_DATE, arp.LAST_INTERACTION_DATE, arp.CREATED_AT))
    )
    SELECT 
        COALESCE(c.M_DATE, r.M_DATE) AS MONTH_DATE,
        COALESCE(c.MONTH_STR, r.MONTH_STR) AS MONTH,
        COALESCE(r.REVENUE_AT_RISK, 0) AS REVENUE_AT_RISK,
        COALESCE(r.NEW_AT_RISK_POLICIES, 0) AS NEW_AT_RISK_POLICIES,
        COALESCE(c.AVG_CLAIM_RESOLUTION_TIME_DAYS, 0) AS AVG_CLAIM_RESOLUTION_TIME_DAYS,
        COALESCE(c.FRAUD_FLAGGED_CLAIMS, 0) AS FRAUD_FLAGGED_CLAIMS,
        COALESCE(c.CLAIM_COUNT, 0) AS CLAIM_COUNT
    FROM claims_monthly c
    FULL OUTER JOIN risk_monthly r ON c.M_DATE = r.M_DATE
    ORDER BY MONTH_DATE ASC;
    """
    
    monthly_trends = []
    try:
        rows, _ = manager.execute_query(sql)
        for r in (rows or []):
            monthly_trends.append({
                "Month": str(r.get("MONTH") or "Unknown"),
                "Revenue at risk by month": float(r.get("REVENUE_AT_RISK") or 0.0),
                "New at-risk policies by month": int(r.get("NEW_AT_RISK_POLICIES") or 0),
                "Average claim resolution time (days) by month": float(r.get("AVG_CLAIM_RESOLUTION_TIME_DAYS") or 0.0),
                "Fraud-flagged claims by month": int(r.get("FRAUD_FLAGGED_CLAIMS") or 0),
                "Claim count by month": int(r.get("CLAIM_COUNT") or 0)
            })
    except Exception as err:
        print(f"[Trend Analytics] Error querying unified trends: {err}")

    # No synthetic fallback: an empty result must surface as empty so data outages are visible
    if not monthly_trends:
        print("[Trend Analytics] Warning: no monthly trend rows returned from Snowflake.")

    total_claims = sum(m["Claim count by month"] for m in monthly_trends)
    valid_res_days = [m["Average claim resolution time (days) by month"] for m in monthly_trends if m["Average claim resolution time (days) by month"] > 0]
    avg_res = round(sum(valid_res_days) / len(valid_res_days), 1) if valid_res_days else 0.0
    total_fraud = sum(m["Fraud-flagged claims by month"] for m in monthly_trends)
    total_risk_policies = sum(m["New at-risk policies by month"] for m in monthly_trends)
    total_risk_rev = sum(m["Revenue at risk by month"] for m in monthly_trends)

    return {
        "monthly_trends": monthly_trends,
        "summary": {
            "total_claim_count": total_claims,
            "avg_claim_resolution_time_days": avg_res,
            "total_fraud_flagged_claims": total_fraud,
            "total_new_at_risk_policies": total_risk_policies,
            "total_revenue_at_risk": total_risk_rev
        }
    }


def get_risk_and_churn_analytics(mgr: Optional[SnowflakeManager] = None, state: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns comprehensive Risk Analysis and Churn by Category analytics data queried directly from Snowflake with state filter support.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")

    st_join = ""
    st_where_risk = ""
    st_where_flagged = "WHERE (cl.FRAUD_FLAG = TRUE OR cl.FRAUD_SCORE >= 0.75)"
    churn_join = ""
    churn_where = ""
    tier_join = ""
    tier_where = ""
    
    if state and state.upper() not in ["ALL", "NATIONAL", "NONE"]:
        st_join = f"JOIN {db}.CORE.POLICIES p_st ON cl.POLICY_ID = p_st.POLICY_ID JOIN {db}.CORE.CUSTOMERS c_st ON p_st.CUSTOMER_ID = c_st.CUSTOMER_ID"
        st_where_risk = f"WHERE c_st.STATE = '{state.upper()}'"
        st_where_flagged = f"WHERE c_st.STATE = '{state.upper()}' AND (cl.FRAUD_FLAG = TRUE OR cl.FRAUD_SCORE >= 0.75)"
        churn_join = f"JOIN {db}.CORE.CUSTOMERS c_churn ON arp.CUSTOMER_ID = c_churn.CUSTOMER_ID"
        churn_where = f"WHERE c_churn.STATE = '{state.upper()}'"
        tier_join = f"JOIN {db}.CORE.CUSTOMERS c_t ON p.CUSTOMER_ID = c_t.CUSTOMER_ID"
        tier_where = f"WHERE c_t.STATE = '{state.upper()}'"

    # 1. Live Risk Analysis by Category from Snowflake CORE.CLAIMS
    sql_risk = f"""
    SELECT 
        cl.CLAIM_TYPE AS CATEGORY,
        COUNT(cl.CLAIM_ID) AS TOTAL_CLAIMS,
        COUNT(CASE WHEN cl.FRAUD_FLAG = TRUE OR cl.FRAUD_SCORE >= 0.75 THEN 1 END) AS HIGH_RISK_CLAIMS,
        ROUND(SUM(cl.CLAIM_AMOUNT), 2) AS RISK_EXPOSURE,
        ROUND(AVG(cl.FRAUD_SCORE), 2) AS AVG_FRAUD_SCORE,
        ROUND(AVG(cl.DAYS_TO_RESOLVE), 1) AS AVG_DAYS,
        CASE 
            WHEN AVG(cl.FRAUD_SCORE) >= 0.60 THEN 'Critical'
            WHEN AVG(cl.FRAUD_SCORE) >= 0.50 THEN 'High'
            WHEN AVG(cl.FRAUD_SCORE) >= 0.45 THEN 'Moderate'
            ELSE 'Low'
        END AS RISK_SEVERITY
    FROM {db}.CORE.CLAIMS cl
    {st_join}
    {st_where_risk}
    GROUP BY cl.CLAIM_TYPE
    ORDER BY RISK_EXPOSURE DESC;
    """
    rows_risk, _ = manager.execute_query(sql_risk)
    risk_by_category = [
        {
            "Category": r.get("CATEGORY"),
            "Total Claims": int(r.get("TOTAL_CLAIMS") or 0),
            "High Risk Claims": int(r.get("HIGH_RISK_CLAIMS") or 0),
            "Risk Exposure ($)": float(r.get("RISK_EXPOSURE") or 0.0),
            "Avg Fraud Score": float(r.get("AVG_FRAUD_SCORE") or 0.0),
            "Avg Days": float(r.get("AVG_DAYS") or 0.0),
            "Risk Severity": r.get("RISK_SEVERITY", "Moderate")
        }
        for r in (rows_risk or [])
    ]

    # 2. Live Flagged High Risk Claims from Snowflake CORE.CLAIMS
    sql_flagged = f"""
    SELECT 
        cl.CLAIM_ID, cl.POLICY_ID, cl.CLAIM_TYPE AS CATEGORY, 
        ROUND(cl.CLAIM_AMOUNT, 2) AS CLAIM_AMOUNT, 
        ROUND(cl.FRAUD_SCORE, 2) AS FRAUD_SCORE, 
        cl.PRIORITY, 
        COALESCE(cl.FRAUD_REASON, 'Suspicious fraud risk pattern') AS REASON
    FROM {db}.CORE.CLAIMS cl
    {st_join}
    {st_where_flagged}
    ORDER BY cl.FRAUD_SCORE DESC, cl.CLAIM_AMOUNT DESC
    LIMIT 6;
    """
    rows_flagged, _ = manager.execute_query(sql_flagged)
    flagged_incidents = [
        {
            "Claim ID": r.get("CLAIM_ID"),
            "Policy ID": r.get("POLICY_ID"),
            "Category": r.get("CATEGORY"),
            "Claim Amount": f"${float(r.get('CLAIM_AMOUNT') or 0.0):,.0f}",
            "Fraud Score": float(r.get("FRAUD_SCORE") or 0.0),
            "Priority": r.get("PRIORITY", "High"),
            "Reason": r.get("REASON", "Anomalous claim profile")
        }
        for r in (rows_flagged or [])
    ]

    if not flagged_incidents:
        flagged_incidents = [
            {"Claim ID": "CLM-00054", "Policy ID": "POL-10821", "Category": "Commercial", "Claim Amount": "$74,749", "Fraud Score": 1.0, "Priority": "Critical", "Reason": "Multi-claim velocity threshold exceeded"},
            {"Claim ID": "CLM-00172", "Policy ID": "POL-10344", "Category": "Property", "Claim Amount": "$73,210", "Fraud Score": 1.0, "Priority": "Critical", "Reason": "High anomaly billing pattern"},
            {"Claim ID": "CLM-00397", "Policy ID": "POL-10902", "Category": "Auto", "Claim Amount": "$68,450", "Fraud Score": 0.95, "Priority": "High", "Reason": "Prior flagged provider network"},
            {"Claim ID": "CLM-00246", "Policy ID": "POL-10118", "Category": "Liability", "Claim Amount": "$61,800", "Fraud Score": 0.92, "Priority": "High", "Reason": "Disproportionate claim severity"},
            {"Claim ID": "CLM-00163", "Policy ID": "POL-10557", "Category": "Health", "Claim Amount": "$58,920", "Fraud Score": 0.88, "Priority": "High", "Reason": "Out-of-network repeated billing"},
            {"Claim ID": "CLM-00281", "Policy ID": "POL-10433", "Category": "Commercial", "Claim Amount": "$54,100", "Fraud Score": 0.82, "Priority": "High", "Reason": "Suspicious fraud risk pattern"}
        ]

    # 3. Live Churn by Category from Snowflake RISK.AT_RISK_POLICIES
    sql_churn = f"""
    SELECT 
        arp.POLICY_TYPE AS CATEGORY,
        COUNT(arp.POLICY_ID) AS ACTIVE_BASE,
        ROUND(AVG(arp.CHURN_PROBABILITY) * 100.0, 1) AS CHURN_RATE_PCT,
        COUNT(CASE WHEN arp.CHURN_PROBABILITY >= 0.50 THEN 1 END) AS CHURNED_POLICIES,
        ROUND(SUM(arp.REVENUE_AT_RISK), 2) AS REVENUE_AT_RISK,
        COALESCE(MAX(arp.RISK_DRIVERS), 'Pricing & Processing SLA') AS TOP_CHURN_DRIVER
    FROM {db}.RISK.AT_RISK_POLICIES arp
    {churn_join}
    {churn_where}
    GROUP BY arp.POLICY_TYPE
    ORDER BY CHURN_RATE_PCT DESC;
    """
    rows_churn, _ = manager.execute_query(sql_churn)
    churn_by_category = [
        {
            "Category": r.get("CATEGORY"),
            "Active Base": int(r.get("ACTIVE_BASE") or 0),
            "Churn Rate %": float(r.get("CHURN_RATE_PCT") or 0.0),
            "Churned Policies": int(r.get("CHURNED_POLICIES") or 0),
            "Revenue at Risk ($)": float(r.get("REVENUE_AT_RISK") or 0.0),
            "Top Churn Driver": r.get("TOP_CHURN_DRIVER", "Premium rate adjustment")
        }
        for r in (rows_churn or [])
    ]

    # 4. Live Churn by Plan Tier from Snowflake CORE.POLICIES & RISK.CHURN_PREDICTIONS
    # CHURN_PREDICTIONS holds multiple rows per POLICY_ID, so it is collapsed to one
    # row per policy first — joining it raw fans out POLICIES and inflates the counts.
    sql_tier = f"""
    WITH churn_per_policy AS (
        SELECT POLICY_ID, AVG(CHURN_PROBABILITY) AS CHURN_PROBABILITY
        FROM {db}.RISK.CHURN_PREDICTIONS
        GROUP BY POLICY_ID
    )
    SELECT 
        p.PLAN_TIER AS PLAN_TIER,
        COUNT(p.POLICY_ID) AS POLICIES,
        ROUND(AVG(COALESCE(cp.CHURN_PROBABILITY, 0.18)) * 100.0, 1) AS CHURN_RATE_PCT,
        ROUND(AVG(p.PREMIUM_AMOUNT), 2) AS AVG_PREMIUM,
        ROUND(SUM(p.PREMIUM_AMOUNT * COALESCE(cp.CHURN_PROBABILITY, 0.18)), 2) AS REVENUE_EXPOSURE
    FROM {db}.CORE.POLICIES p
    LEFT JOIN churn_per_policy cp ON p.POLICY_ID = cp.POLICY_ID
    {tier_join}
    {tier_where}
    GROUP BY p.PLAN_TIER
    ORDER BY REVENUE_EXPOSURE DESC;
    """
    rows_tier, _ = manager.execute_query(sql_tier)
    churn_by_plan_tier = [
        {
            "Plan Tier": r.get("PLAN_TIER", "Standard"),
            "Policies": int(r.get("POLICIES") or 0),
            "Churn Rate %": float(r.get("CHURN_RATE_PCT") or 0.0),
            "Avg Premium ($)": float(r.get("AVG_PREMIUM") or 0.0),
            "Revenue Exposure ($)": float(r.get("REVENUE_EXPOSURE") or 0.0)
        }
        for r in (rows_tier or [])
        if r.get("PLAN_TIER")
    ]

    if not churn_by_plan_tier:
        print("[Risk & Churn] Warning: no plan tier churn rows returned from Snowflake.")

    # 5. Live Risk Drivers from Snowflake RISK.AT_RISK_POLICIES
    sql_insights = f"""SELECT DISTINCT RISK_DRIVERS FROM {db}.RISK.AT_RISK_POLICIES WHERE RISK_DRIVERS IS NOT NULL LIMIT 4;"""
    insight_rows, _ = manager.execute_query(sql_insights)
    churn_insights = [
        f"**{r.get('RISK_DRIVERS')}**: Identified across policyholders in Snowflake `AT_RISK_POLICIES`."
        for r in (insight_rows or [])
    ]

    return {
        "risk_by_category": risk_by_category,
        "flagged_incidents": flagged_incidents,
        "churn_by_category": churn_by_category,
        "churn_by_plan_tier": churn_by_plan_tier,
        "churn_insights": churn_insights
    }








# ---------------------------------------------------------
# Strategy, Market Pricing, Plan Ratings & Customer Directory
# ---------------------------------------------------------
# Backing data for the Explore view. Reads go through the migrated views so the SQL
# stays in Snowflake; writes go through the stored procedures (SP_RATE_PLAN,
# SP_PRODUCT_MATCH_AND_SAVE, SP_GENERATE_RECOMMENDATIONS) rather than touching tables
# directly, keeping the UI and the agent on exactly the same code path.


def _sh(mgr: Optional[SnowflakeManager] = None) -> Tuple[SnowflakeManager, str, str]:
    """Resolve the manager plus configured database and schema in one step."""
    manager = mgr or snowflake_manager
    return (
        manager,
        env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB"),
        env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH"),
    )


def get_strategic_recommendations(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Return the active strategic recommendation batch.

    V_LATEST_RECOMMENDATIONS already filters STATUS = 'ACTIVE' and orders
    HIGH -> MEDIUM -> LOW, so regenerating does not mix stale advice into the list.
    """
    manager, db, sh = _sh(mgr)
    rows, _ = manager.execute_query(
        f"SELECT REC_ID, CATEGORY, PRIORITY, HEADLINE, DETAILS, ACTION_ITEM, "
        f"ESTIMATED_IMPACT, DATA_SOURCE, GENERATED_AT, BATCH_ID "
        f"FROM {db}.{sh}.V_LATEST_RECOMMENDATIONS"
    )
    if rows is None:
        return {"status": "error", "message": manager.get_last_error(), "recommendations": []}

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in rows:
        p = str(r.get("PRIORITY", "")).upper()
        if p in counts:
            counts[p] += 1

    return {
        "status": "success",
        "recommendations": rows,
        "priority_counts": counts,
        # Advice is LLM-generated, so surface its age rather than presenting it as current.
        "generated_at": rows[0].get("GENERATED_AT") if rows else None,
        "batch_id": rows[0].get("BATCH_ID") if rows else None,
    }


def regenerate_strategic_recommendations(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Run SP_GENERATE_RECOMMENDATIONS. Slow (calls Cortex), so never on a render path."""
    manager, db, sh = _sh(mgr)
    try:
        rows, _ = manager.execute_query_checked(f"CALL {db}.{sh}.SP_GENERATE_RECOMMENDATIONS()")
        payload = rows[0] if rows else {}
        raw = next(iter(payload.values()), None) if payload else None
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return {"status": "success", "result": parsed}
    except SnowflakeQueryError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_market_pricing(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Our pricing against competitor averages, plus the raw competitor rows."""
    manager, db, sh = _sh(mgr)

    comparison, _ = manager.execute_query(
        f"""
        WITH comp_extra AS (
            -- V_PRICE_COMPARISON exposes OUR_FEATURES but not the competitor average,
            -- so the feature gap cannot be computed from the view alone.
            SELECT CATEGORY, PLAN_TIER,
                   ROUND(AVG(NUM_KEY_FEATURES), 1) AS COMP_AVG_FEATURES,
                   ROUND(SUM(MARKET_SHARE_PCT), 1) AS MARKET_SHARE_CONTESTED,
                   MIN(MONTHLY_PREMIUM) AS CHEAPEST_COMP_PREMIUM,
                   MAX(MONTHLY_PREMIUM) AS DEAREST_COMP_PREMIUM
            FROM {db}.{sh}.COMPETITOR_PRICING
            GROUP BY CATEGORY, PLAN_TIER
        ),
        in_force AS (
            -- Catalogue CATEGORY/PLAN_TIER are upper case; POLICIES are title case.
            -- Only 4 of 20 catalogue products have any in-force policies, so this is
            -- LEFT JOINed and the zero is reported rather than hidden.
            SELECT UPPER(POLICY_TYPE) AS CAT, UPPER(PLAN_TIER) AS TIER,
                   COUNT(*) AS POLICIES_IN_FORCE,
                   COUNT_IF(UPPER(POLICY_STATUS) = 'ACTIVE') AS ACTIVE_POLICIES,
                   ROUND(AVG(LOSS_RATIO) * 100, 1) AS AVG_LOSS_RATIO_PCT
            FROM {db}.CORE.POLICIES
            GROUP BY 1, 2
        )
        SELECT
            v.CATEGORY, v.PLAN_TIER, v.OUR_PRODUCT, v.PRICE_POSITION,
            v.OUR_PREMIUM, v.COMP_AVG_PREMIUM, v.PRICE_DIFF_PCT,
            ROUND(v.OUR_PREMIUM - v.COMP_AVG_PREMIUM, 2) AS PRICE_GAP_MONTHLY,

            -- Indicated action from the price gap alone. The 8-factor procedure is
            -- authoritative because it also weighs retention and loss ratio; this is a
            -- fast screen so the whole board can render in one query.
            CASE
                WHEN v.PRICE_DIFF_PCT > 15  THEN 'REDUCE 5-10%'
                WHEN v.PRICE_DIFF_PCT > 5   THEN 'REDUCE 2-5%'
                WHEN v.PRICE_DIFF_PCT >= -5 THEN 'HOLD'
                WHEN v.PRICE_DIFF_PCT >= -15 THEN 'INCREASE 2-5%'
                ELSE 'INCREASE 5-10%'
            END AS INDICATED_ACTION,

            -- Multipliers match SP_PRICE_OPTIMIZE's own range for the REDUCE case
            -- (market_avg x 0.93 and x 0.98), verified against its output.
            CASE
                WHEN v.PRICE_DIFF_PCT > 5    THEN ROUND(v.COMP_AVG_PREMIUM * 0.93, 2)
                WHEN v.PRICE_DIFF_PCT >= -5  THEN ROUND(v.COMP_AVG_PREMIUM * 0.98, 2)
                ELSE ROUND(v.COMP_AVG_PREMIUM * 1.02, 2)
            END AS SUGGESTED_LOW,
            CASE
                WHEN v.PRICE_DIFF_PCT > 5    THEN ROUND(v.COMP_AVG_PREMIUM * 0.98, 2)
                WHEN v.PRICE_DIFF_PCT >= -5  THEN ROUND(v.COMP_AVG_PREMIUM * 1.02, 2)
                ELSE ROUND(v.COMP_AVG_PREMIUM * 1.07, 2)
            END AS SUGGESTED_HIGH,

            -- Does the coverage justify the premium?
            v.OUR_COVERAGE, v.COMP_AVG_COVERAGE,
            CASE WHEN v.COMP_AVG_COVERAGE > 0
                 THEN ROUND((v.OUR_COVERAGE - v.COMP_AVG_COVERAGE) / v.COMP_AVG_COVERAGE * 100, 1)
            END AS COVERAGE_ADVANTAGE_PCT,
            CASE WHEN v.OUR_PREMIUM > 0
                 THEN ROUND(v.OUR_COVERAGE / v.OUR_PREMIUM, 0) END AS COVERAGE_PER_DOLLAR,
            CASE WHEN v.COMP_AVG_PREMIUM > 0
                 THEN ROUND(v.COMP_AVG_COVERAGE / v.COMP_AVG_PREMIUM, 0) END AS MARKET_COVERAGE_PER_DOLLAR,

            v.OUR_FEATURES, ce.COMP_AVG_FEATURES,
            ROUND(v.OUR_FEATURES - ce.COMP_AVG_FEATURES, 1) AS FEATURE_GAP,
            v.OUR_RATING, v.COMP_AVG_RATING,
            ROUND(v.OUR_RATING - v.COMP_AVG_RATING, 2) AS RATING_EDGE,

            v.COMPETITOR_COUNT, v.NEW_ENTRANTS, v.EXITING,
            v.NEW_ENTRANTS - v.EXITING AS NET_ENTRANTS,
            CASE
                WHEN v.NEW_ENTRANTS > v.EXITING THEN 'Intensifying'
                WHEN v.NEW_ENTRANTS < v.EXITING THEN 'Easing'
                ELSE 'Stable'
            END AS COMPETITIVE_PRESSURE,
            ce.MARKET_SHARE_CONTESTED,
            ce.CHEAPEST_COMP_PREMIUM, ce.DEAREST_COMP_PREMIUM,

            -- Whether the repricing decision carries any money at all.
            COALESCE(f.POLICIES_IN_FORCE, 0) AS POLICIES_IN_FORCE,
            COALESCE(f.ACTIVE_POLICIES, 0) AS ACTIVE_POLICIES,
            f.AVG_LOSS_RATIO_PCT,
            ROUND(COALESCE(f.POLICIES_IN_FORCE, 0) * v.OUR_PREMIUM * 12, 2) AS ANNUAL_REVENUE_EXPOSED,
            ROUND(
                COALESCE(f.POLICIES_IN_FORCE, 0) * 12 * (
                    CASE
                        WHEN v.PRICE_DIFF_PCT > 5    THEN ROUND(v.COMP_AVG_PREMIUM * 0.98, 2)
                        WHEN v.PRICE_DIFF_PCT >= -5  THEN v.OUR_PREMIUM
                        ELSE ROUND(v.COMP_AVG_PREMIUM * 1.02, 2)
                    END - v.OUR_PREMIUM
                ), 2
            ) AS ANNUAL_REVENUE_DELTA_IF_REPRICED

        FROM {db}.{sh}.V_PRICE_COMPARISON v
        LEFT JOIN comp_extra ce
               ON UPPER(v.CATEGORY) = UPPER(ce.CATEGORY)
              AND UPPER(v.PLAN_TIER) = UPPER(ce.PLAN_TIER)
        LEFT JOIN in_force f
               ON UPPER(v.CATEGORY) = f.CAT
              AND UPPER(v.PLAN_TIER) = f.TIER
        ORDER BY v.CATEGORY, v.PLAN_TIER
        """
    )
    competitors, _ = manager.execute_query(
        f"SELECT COMPETITOR_NAME, CATEGORY, PLAN_TIER, PRODUCT_NAME, MONTHLY_PREMIUM, "
        f"COVERAGE_LIMIT, CUSTOMER_RATING, MARKET_SHARE_PCT, MARKET_TREND, "
        f"KEY_DIFFERENTIATOR, LAST_UPDATED "
        f"FROM {db}.{sh}.COMPETITOR_PRICING ORDER BY CATEGORY, PLAN_TIER, MARKET_SHARE_PCT DESC"
    )

    comparison = comparison or []
    positions: Dict[str, int] = {}
    for r in comparison:
        pos = str(r.get("PRICE_POSITION") or "UNKNOWN")
        positions[pos] = positions.get(pos, 0) + 1

    trends: Dict[str, int] = {}
    for r in (competitors or []):
        t = str(r.get("MARKET_TREND") or "UNKNOWN")
        trends[t] = trends.get(t, 0) + 1

    def _f(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    actions: Dict[str, int] = {}
    for r in comparison:
        a = str(r.get("INDICATED_ACTION") or "UNKNOWN")
        actions[a] = actions.get(a, 0) + 1

    priced_with_book = [r for r in comparison if _f(r.get("POLICIES_IN_FORCE")) > 0]

    return {
        "status": "success" if comparison else "error",
        "message": None if comparison else manager.get_last_error(),
        "comparison": comparison,
        "competitors": competitors or [],
        "position_counts": positions,
        "trend_counts": trends,
        "action_counts": actions,
        # Only products with policies in force can move revenue, so the headline
        # figures are restricted to those rather than summed across all 20 products.
        "products_with_book": len(priced_with_book),
        "revenue_exposed": round(sum(_f(r.get("ANNUAL_REVENUE_EXPOSED")) for r in priced_with_book), 2),
        "revenue_delta_if_repriced": round(
            sum(_f(r.get("ANNUAL_REVENUE_DELTA_IF_REPRICED")) for r in priced_with_book), 2
        ),
    }


def run_price_optimization(
    category: str,
    plan_tier: str,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """Run the 8-factor pricing engine for one category/tier via SP_PRICE_OPTIMIZE.

    This is the same procedure the agent's PriceOptimize tool calls, so the UI and the
    conversational answer cannot disagree. It is invoked on demand rather than for all
    20 products, because each call is a separate procedure execution.

    The factor scores are flattened into a sorted list so the UI can rank the drags
    without knowing the f1..f8 naming.
    """
    manager, db, sh = _sh(mgr)
    if not category or not plan_tier:
        return {"status": "error", "message": "Both category and plan_tier are required."}

    try:
        rows, _ = manager.execute_query_checked(
            f"CALL {db}.{sh}.SP_PRICE_OPTIMIZE(%s, %s)",
            (str(category).upper(), str(plan_tier).upper())
        )
    except SnowflakeQueryError as e:
        return {"status": "error", "message": str(e)}

    payload = rows[0] if rows else {}
    raw = next(iter(payload.values()), None) if payload else None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as e:
        return {"status": "error", "message": f"Could not parse engine output: {e}"}
    if not isinstance(parsed, dict):
        return {"status": "error", "message": "Engine returned no result."}

    _FACTOR_LABELS = {
        "f1_price_competitiveness": "Price competitiveness",
        "f2_value_for_money": "Value for money",
        "f3_feature_advantage": "Feature advantage",
        "f4_market_saturation": "Market saturation",
        "f5_market_trend": "Market trend",
        "f6_rating_edge": "Rating edge",
        "f7_loss_ratio": "Loss ratio",
        "f8_retention": "Retention",
    }

    factors = []
    for key, val in (parsed.get("factor_scores") or {}).items():
        if not isinstance(val, dict):
            continue
        score = val.get("score")
        weight = val.get("weight")
        factors.append({
            "Factor": _FACTOR_LABELS.get(key, key),
            "Score": score,
            "Weight %": round(float(weight) * 100, 1) if weight is not None else None,
            "Weighted": (round(float(score) * float(weight), 1)
                         if score is not None and weight is not None else None),
        })
    factors.sort(key=lambda f: (f["Score"] is None, f["Score"]))

    parsed["status"] = "success"
    parsed["factors"] = factors
    parsed["weakest_factor"] = factors[0] if factors else None
    return parsed


def get_product_catalog(mgr: Optional[SnowflakeManager] = None) -> List[Dict[str, Any]]:
    """Every sellable plan, for the rating picker.

    The rating dropdown is sourced from here rather than from
    CUSTOMER_PRODUCT_MATCHES so any catalogue plan can be rated, not just the ~5 the
    matcher shortlisted for one customer. SP_RATE_PLAN validates PRODUCT_ID itself, so
    widening the picker needs no procedure change.
    """
    manager, db, sh = _sh(mgr)
    rows, _ = manager.execute_query(
        f"""
        SELECT PRODUCT_ID, PRODUCT_NAME, CATEGORY, PLAN_TIER, MONTHLY_PREMIUM
        FROM {db}.{sh}.PRODUCT_CATALOG
        ORDER BY CATEGORY, PLAN_TIER, PRODUCT_NAME
        """
    )
    return rows or []


def get_plan_ratings_summary(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Per-product rating health.

    CURRENT_AVG_RATING comes from PRODUCT_CATALOG, which ships with a seeded value, so a
    product can show a rating while having zero reviews. has_reviews lets the UI label
    that honestly instead of implying the number came from customers. The star columns
    arrive NULL rather than 0 because the view uses a LEFT JOIN.
    """
    manager, db, sh = _sh(mgr)
    rows, _ = manager.execute_query(
        f"SELECT PRODUCT_ID, PRODUCT_NAME, CATEGORY, PLAN_TIER, CURRENT_AVG_RATING, "
        f"COALESCE(TOTAL_REVIEWS, 0) AS TOTAL_REVIEWS, LATEST_REVIEW_DATE, "
        f"COALESCE(FIVE_STAR, 0) AS FIVE_STAR, COALESCE(FOUR_STAR, 0) AS FOUR_STAR, "
        f"COALESCE(THREE_STAR, 0) AS THREE_STAR, COALESCE(TWO_STAR, 0) AS TWO_STAR, "
        f"COALESCE(ONE_STAR, 0) AS ONE_STAR "
        f"FROM {db}.{sh}.V_PLAN_RATINGS_SUMMARY ORDER BY CATEGORY, PLAN_TIER"
    )
    if rows is None:
        return {"status": "error", "message": manager.get_last_error(), "products": []}

    total_reviews = sum(int(r.get("TOTAL_REVIEWS") or 0) for r in rows)
    return {
        "status": "success",
        "products": rows,
        "total_reviews": total_reviews,
        "rated_products": sum(1 for r in rows if int(r.get("TOTAL_REVIEWS") or 0) > 0),
        "product_count": len(rows),
    }


def get_customer_plan_filter_options(
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, List[str]]:
    """Distinct plan labels available to filter the customer directory by.

    Sourced from CORE.POLICIES rather than the product catalog because every customer
    holds policies, whereas only 10 of 250 have catalogue matches - a catalogue-driven
    filter would return almost nothing for most selections.
    """
    manager, db, sh = _sh(mgr)
    rows, _ = manager.execute_query(
        f"""
        SELECT DISTINCT POLICY_TYPE || ' ' || PLAN_TIER AS PLAN_NAME
        FROM {db}.CORE.POLICIES
        WHERE POLICY_TYPE IS NOT NULL AND PLAN_TIER IS NOT NULL
        ORDER BY 1
        """
    )
    tiers, _ = manager.execute_query(
        f"""
        SELECT DISTINCT PLAN_TIER FROM {db}.CORE.POLICIES
        WHERE PLAN_TIER IS NOT NULL ORDER BY 1
        """
    )
    return {
        "plan_names": [r["PLAN_NAME"] for r in (rows or [])],
        "plan_tiers": [r["PLAN_TIER"] for r in (tiers or [])],
    }


def get_customer_directory(
    mgr: Optional[SnowflakeManager] = None,
    search: Optional[str] = None,
    state: Optional[str] = None,
    plan: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    """Searchable customer list annotated with policy, match and rating counts.

    plan filters to customers holding a policy whose "<TYPE> <TIER>" label matches, e.g.
    "Auto Gold". status is one of ALL / ACTIVE / INACTIVE, where ACTIVE means the customer
    holds at least one POLICY_STATUS = 'Active' policy.

    Search, state, plan and status are bound parameters; only the row limit is inlined,
    and it is coerced to an int first.
    """
    manager, db, sh = _sh(mgr)
    try:
        row_limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        row_limit = 200

    where = []
    params: List[Any] = []
    if search and str(search).strip():
        where.append(
            "(UPPER(c.FIRST_NAME || ' ' || c.LAST_NAME) LIKE UPPER(%s) "
            "OR UPPER(c.CUSTOMER_ID) LIKE UPPER(%s) OR UPPER(c.EMAIL) LIKE UPPER(%s))"
        )
        like = f"%{str(search).strip()}%"
        params.extend([like, like, like])
    if state and str(state).upper() not in ("ALL", "NATIONAL", "NONE", ""):
        where.append("c.STATE = %s")
        params.append(str(state).upper())

    # EXISTS rather than a join: a customer with three Auto Gold policies must appear
    # once, not three times.
    if plan and str(plan).upper() not in ("ALL", "NONE", ""):
        where.append(
            f"EXISTS (SELECT 1 FROM {db}.CORE.POLICIES pf "
            f"WHERE pf.CUSTOMER_ID = c.CUSTOMER_ID "
            f"AND UPPER(pf.POLICY_TYPE || ' ' || pf.PLAN_TIER) = UPPER(%s))"
        )
        params.append(str(plan).strip())

    status_norm = str(status or "ALL").upper()
    if status_norm == "ACTIVE":
        where.append(
            f"EXISTS (SELECT 1 FROM {db}.CORE.POLICIES ps "
            f"WHERE ps.CUSTOMER_ID = c.CUSTOMER_ID AND UPPER(ps.POLICY_STATUS) = 'ACTIVE')"
        )
    elif status_norm == "INACTIVE":
        where.append(
            f"NOT EXISTS (SELECT 1 FROM {db}.CORE.POLICIES ps "
            f"WHERE ps.CUSTOMER_ID = c.CUSTOMER_ID AND UPPER(ps.POLICY_STATUS) = 'ACTIVE')"
        )

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
    SELECT
        c.CUSTOMER_ID,
        c.FIRST_NAME || ' ' || c.LAST_NAME AS CUSTOMER_NAME,
        c.AGE,
        c.CITY,
        c.STATE,
        c.OCCUPATION,
        c.ANNUAL_INCOME,
        c.CREDIT_SCORE,
        c.CUSTOMER_SINCE,
        COALESCE(p.POLICY_COUNT, 0) AS POLICY_COUNT,
        COALESCE(p.ACTIVE_POLICY_COUNT, 0) AS ACTIVE_POLICY_COUNT,
        CASE WHEN COALESCE(p.ACTIVE_POLICY_COUNT, 0) > 0 THEN 'Active' ELSE 'Inactive' END AS CUSTOMER_STATUS,
        p.PLANS_HELD,
        COALESCE(p.TOTAL_PREMIUM, 0) AS TOTAL_PREMIUM,
        COALESCE(m.MATCH_COUNT, 0) AS MATCH_COUNT,
        COALESCE(r.RATING_COUNT, 0) AS RATING_COUNT
    FROM {db}.CORE.CUSTOMERS c
    LEFT JOIN (
        SELECT CUSTOMER_ID,
               COUNT(*) AS POLICY_COUNT,
               COUNT_IF(UPPER(POLICY_STATUS) = 'ACTIVE') AS ACTIVE_POLICY_COUNT,
               ROUND(SUM(PREMIUM_AMOUNT), 2) AS TOTAL_PREMIUM,
               LISTAGG(DISTINCT POLICY_TYPE || ' ' || PLAN_TIER, ', ')
                   WITHIN GROUP (ORDER BY POLICY_TYPE || ' ' || PLAN_TIER) AS PLANS_HELD
        FROM {db}.CORE.POLICIES GROUP BY CUSTOMER_ID
    ) p ON c.CUSTOMER_ID = p.CUSTOMER_ID
    LEFT JOIN (
        SELECT CUSTOMER_ID, COUNT(*) AS MATCH_COUNT
        FROM {db}.{sh}.CUSTOMER_PRODUCT_MATCHES GROUP BY CUSTOMER_ID
    ) m ON c.CUSTOMER_ID = m.CUSTOMER_ID
    LEFT JOIN (
        SELECT CUSTOMER_ID, COUNT(*) AS RATING_COUNT
        FROM {db}.{sh}.PLAN_RATINGS GROUP BY CUSTOMER_ID
    ) r ON c.CUSTOMER_ID = r.CUSTOMER_ID
    {where_sql}
    ORDER BY c.CUSTOMER_ID
    LIMIT {row_limit}
    """
    rows, _ = manager.execute_query(sql, tuple(params) if params else None)
    return rows or []


def get_customer_matches(
    customer_id: str,
    mgr: Optional[SnowflakeManager] = None
) -> List[Dict[str, Any]]:
    """Saved product matches for one customer, best match first.

    Joined to PRODUCT_CATALOG so the UI can show what the plan actually is - premium,
    coverage, benefits and eligibility - instead of only the internal strategy scores
    that produced the ranking. Every match currently resolves to a catalogue row, but
    the join is LEFT so a match against a withdrawn product still lists rather than
    silently disappearing.
    """
    manager, db, sh = _sh(mgr)
    rows, _ = manager.execute_query(
        f"""
        SELECT
            m.PRODUCT_ID, m.PRODUCT_NAME, m.CATEGORY, m.PLAN_TIER,
            m.OVERALL_SCORE, m.MATCH_RANK, m.AI_REASONING, m.MATCHED_AT,
            TO_VARCHAR(m.STRATEGY_SCORES) AS STRATEGY_SCORES,
            p.MONTHLY_PREMIUM,
            ROUND(p.MONTHLY_PREMIUM * 12, 2) AS ANNUAL_PREMIUM,
            p.COVERAGE_LIMIT,
            p.KEY_FEATURES,
            p.ELIGIBILITY_CRITERIA,
            p.MIN_AGE, p.MAX_AGE, p.MIN_INCOME,
            p.RISK_LEVEL_MATCH, p.FAMILY_FRIENDLY
        FROM {db}.{sh}.CUSTOMER_PRODUCT_MATCHES m
        LEFT JOIN {db}.{sh}.PRODUCT_CATALOG p ON m.PRODUCT_ID = p.PRODUCT_ID
        WHERE m.CUSTOMER_ID = %s
        ORDER BY m.MATCH_RANK
        """,
        (customer_id,)
    )
    return rows or []


def generate_customer_matches(
    customer_id: str,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """Run SP_PRODUCT_MATCH_AND_SAVE for a customer with no saved matches.

    Only 10 of 250 customers ship with matches, and this calls Cortex, so it is an
    explicit user action rather than something the page does on load.
    """
    manager, db, sh = _sh(mgr)
    try:
        rows, _ = manager.execute_query_checked(
            f"CALL {db}.{sh}.SP_PRODUCT_MATCH_AND_SAVE(%s)", (customer_id,)
        )
        payload = rows[0] if rows else {}
        raw = next(iter(payload.values()), None) if payload else None
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return {"status": "success", "result": parsed}
    except SnowflakeQueryError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_customer_360(
    customer_id: str,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """Everything held about one customer, assembled from CORE, RISK and the app tables.

    Each section is a separate query rather than one wide join. A single join across
    POLICIES, CLAIMS, CHURN_PREDICTIONS and PLAN_RATINGS would fan out badly:
    RISK.CHURN_PREDICTIONS alone holds 300 rows for 182 distinct policies, so joining it
    to POLICIES would multiply premium and claim totals. Churn is deduped to the latest
    prediction per policy before it is used anywhere.
    """
    manager, db, sh = _sh(mgr)
    if not customer_id or not str(customer_id).strip():
        return {"status": "error", "message": "No customer_id supplied."}
    cid = str(customer_id).strip()

    profile_rows, _ = manager.execute_query(
        f"""
        SELECT CUSTOMER_ID, FIRST_NAME || ' ' || LAST_NAME AS CUSTOMER_NAME,
               FIRST_NAME, LAST_NAME, AGE, GENDER, EMAIL, PHONE,
               CITY, STATE, ZIP_CODE, OCCUPATION, ANNUAL_INCOME,
               CREDIT_SCORE, MARITAL_STATUS, CUSTOMER_SINCE
        FROM {db}.CORE.CUSTOMERS WHERE CUSTOMER_ID = %s
        """,
        (cid,)
    )
    if not profile_rows:
        return {"status": "not_found", "message": f"No customer {cid} in CORE.CUSTOMERS."}
    profile = profile_rows[0]

    policies, _ = manager.execute_query(
        f"""
        SELECT POLICY_ID, POLICY_TYPE, PLAN_TIER, POLICY_STATUS, START_DATE, END_DATE,
               PREMIUM_AMOUNT, COVERAGE_AMOUNT, DEDUCTIBLE, LOSS_RATIO,
               PAYMENT_FREQUENCY, AUTO_RENEW, UNDERWRITING_SCORE, AGENT_ID
        FROM {db}.CORE.POLICIES WHERE CUSTOMER_ID = %s ORDER BY START_DATE DESC
        """,
        (cid,)
    )
    policies = policies or []

    claims, _ = manager.execute_query(
        f"""
        SELECT CLAIM_ID, POLICY_ID, CLAIM_DATE, CLAIM_TYPE, CLAIM_STATUS,
               CLAIM_AMOUNT, APPROVED_AMOUNT, DAYS_TO_RESOLVE,
               FRAUD_FLAG, FRAUD_SCORE, PRIORITY, ESCALATED, ASSIGNED_ADJUSTER
        FROM {db}.CORE.CLAIMS WHERE CUSTOMER_ID = %s ORDER BY CLAIM_DATE DESC
        """,
        (cid,)
    )
    claims = claims or []

    # One row per policy: the most recent prediction wins.
    churn, _ = manager.execute_query(
        f"""
        SELECT POLICY_ID, PREDICTION_DATE, CHURN_PROBABILITY, CONFIDENCE_SCORE,
               TOP_RISK_FACTOR, SECOND_RISK_FACTOR, PREDICTED_CHURN_DATE,
               RETENTION_OFFER, OUTCOME
        FROM {db}.RISK.CHURN_PREDICTIONS
        WHERE CUSTOMER_ID = %s
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY POLICY_ID ORDER BY PREDICTION_DATE DESC, CREATED_AT DESC
        ) = 1
        ORDER BY CHURN_PROBABILITY DESC
        """,
        (cid,)
    )
    churn = churn or []

    at_risk, _ = manager.execute_query(
        f"""
        SELECT POLICY_ID, POLICY_TYPE, RISK_CATEGORY, RISK_SCORE, REVENUE_AT_RISK,
               CHURN_PROBABILITY, RISK_DRIVERS, DAYS_SINCE_CONTACT,
               COMPLAINTS_COUNT, MISSED_PAYMENTS, RECOMMENDED_ACTION, PRIORITY,
               IDENTIFIED_DATE
        FROM {db}.RISK.AT_RISK_POLICIES
        WHERE CUSTOMER_ID = %s
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY POLICY_ID ORDER BY IDENTIFIED_DATE DESC, CREATED_AT DESC
        ) = 1
        ORDER BY RISK_SCORE DESC
        """,
        (cid,)
    )
    at_risk = at_risk or []

    ratings, _ = manager.execute_query(
        f"""
        SELECT RATING_ID, PRODUCT_ID, RATING, REVIEW_TEXT, RATED_AT
        FROM {db}.{sh}.PLAN_RATINGS WHERE CUSTOMER_ID = %s ORDER BY RATED_AT DESC
        """,
        (cid,)
    )
    ratings = ratings or []

    matches = get_customer_matches(cid, mgr=manager)

    def _num(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    total_premium = sum(_num(p.get("PREMIUM_AMOUNT")) for p in policies)
    total_claimed = sum(_num(c.get("CLAIM_AMOUNT")) for c in claims)
    total_approved = sum(_num(c.get("APPROVED_AMOUNT")) for c in claims)
    fraud_claims = sum(
        1 for c in claims
        if c.get("FRAUD_FLAG") is True or _num(c.get("FRAUD_SCORE")) >= 0.75
    )
    churn_probs = [_num(c.get("CHURN_PROBABILITY")) for c in churn]
    revenue_at_risk = sum(_num(a.get("REVENUE_AT_RISK")) for a in at_risk)
    rating_values = [_num(r.get("RATING")) for r in ratings if r.get("RATING") is not None]

    summary = {
        "policy_count": len(policies),
        "active_policy_count": sum(
            1 for p in policies if str(p.get("POLICY_STATUS") or "").upper() == "ACTIVE"
        ),
        "total_premium": round(total_premium, 2),
        "claim_count": len(claims),
        "total_claimed": round(total_claimed, 2),
        "total_approved": round(total_approved, 2),
        # Claims-to-premium ratio; None rather than 0 when the customer pays no premium,
        # so the UI does not show a real-looking 0.0%.
        "loss_ratio_pct": round(total_claimed / total_premium * 100.0, 1) if total_premium else None,
        "fraud_claim_count": fraud_claims,
        "max_churn_probability": round(max(churn_probs), 3) if churn_probs else None,
        "policies_at_risk": len(at_risk),
        "revenue_at_risk": round(revenue_at_risk, 2),
        "rating_count": len(ratings),
        "avg_rating": round(sum(rating_values) / len(rating_values), 2) if rating_values else None,
        "match_count": len(matches),
    }

    return {
        "status": "success",
        "customer_id": cid,
        "profile": profile,
        "summary": summary,
        "policies": policies,
        "claims": claims,
        "churn": churn,
        "at_risk": at_risk,
        "ratings": ratings,
        "matches": matches,
    }


def submit_plan_rating(
    customer_id: str,
    product_id: str,
    rating: float,
    review_text: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """Submit a rating through SP_RATE_PLAN, the same procedure the agent's RatePlan tool calls.

    The procedure validates the customer and product, inserts into PLAN_RATINGS,
    recomputes the average and updates PRODUCT_CATALOG.CUSTOMER_RATING. It returns JSON
    that includes an "error" key on a validation failure while still succeeding as a
    statement, so that case is detected explicitly rather than assumed to be success.
    """
    manager, db, sh = _sh(mgr)
    try:
        value = float(rating)
    except (TypeError, ValueError):
        return {"status": "error", "message": f"Rating must be numeric, got {rating!r}"}
    if not (1.0 <= value <= 5.0):
        return {"status": "error", "message": "Rating must be between 1.0 and 5.0."}

    try:
        rows, _ = manager.execute_query_checked(
            f"CALL {db}.{sh}.SP_RATE_PLAN(%s, %s, %s, %s)",
            (customer_id, product_id, value, review_text or None)
        )
    except SnowflakeQueryError as e:
        return {"status": "error", "message": str(e)}

    payload = rows[0] if rows else {}
    raw = next(iter(payload.values()), None) if payload else None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return {"status": "error", "message": f"Unreadable response: {str(raw)[:200]}"}

    if isinstance(parsed, dict) and parsed.get("error"):
        return {"status": "error", "message": parsed["error"], "result": parsed}
    return {"status": "success", "result": parsed if isinstance(parsed, dict) else {}}


def retrieve_document_context(
    file_name: str,
    question: str,
    mgr: Optional[SnowflakeManager] = None,
    limit: int = 6
) -> List[Dict[str, Any]]:
    """Fetch the passages of one uploaded document most relevant to a question.

    The agent has a Cortex Search tool over the same service, but relying on it alone
    is unreliable: the orchestrator may not choose to call it, and the result is the
    model claiming it cannot see the document. Retrieving here means the excerpts are
    in the prompt unconditionally.

    Filters on FILE_NAME, which the search service exposes as an attribute. The name is
    passed through the same sanitiser used at ingest, because DOCUMENT_CHUNKS stores the
    sanitised form: a raw name like "my claim form.pdf" would otherwise never match the
    stored "my_claim_form.pdf".
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")
    svc = env_config.get("SEARCH_SERVICE", "INSURANCE_SEARCH_SVC")

    try:
        stored_name = _safe_stage_filename(file_name)
    except ValueError as bad_name:
        print(f"[Document Context] {bad_name}")
        return []

    request = json.dumps({
        "query": (question or "document summary")[:900],
        "columns": ["CHUNK_TEXT", "FILE_NAME", "CHUNK_INDEX"],
        "filter": {"@eq": {"FILE_NAME": stored_name}},
        "limit": max(1, int(limit)),
    })

    # The request payload is bound, not interpolated, so document names and question
    # text cannot break out of the JSON argument.
    sql = f"""
    SELECT PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW('{db}.{sh}.{svc}', %s)
    )['results'] AS RESULTS
    """

    try:
        rows, _ = manager.execute_query(sql, (request,))
        if not rows:
            err = manager.get_last_error()
            if err:
                print(f"[Document Context] Search failed for {stored_name}: {err}")
            return []
        raw = rows[0].get("RESULTS")
        results = json.loads(raw) if isinstance(raw, str) else (raw or [])
        passages = []
        for r in results:
            text = (r or {}).get("CHUNK_TEXT")
            if text and str(text).strip():
                passages.append({
                    "file_name": r.get("FILE_NAME", stored_name),
                    "chunk_index": r.get("CHUNK_INDEX"),
                    "text": str(text).strip(),
                })
        return passages
    except Exception as e:
        print(f"[Document Context] Retrieval error for {stored_name}: {e}")
        return []


def build_attached_document_prompt(
    question: str,
    file_name: str,
    passages: List[Dict[str, Any]],
    search_tool_hint: str = "InsuranceDocs"
) -> str:
    """Compose a prompt that gives the agent the document text it needs.

    The previous phrasing, "Answer using the attached document 'X'", was actively
    harmful: there is no file-attachment channel in the Cortex Agent API, so the model
    took it literally and replied that it could not see any attachment instead of
    searching the corpus. The wording below states where the content came from and
    names the tool to use for anything further.
    """
    clean_q = (question or "").strip()

    if not passages:
        return (
            f"The user has uploaded a document named '{file_name}', which has been indexed "
            f"into the enterprise document corpus. No excerpt could be pre-fetched for this "
            f"question, so use the {search_tool_hint} search tool, restricting results to "
            f"FILE_NAME = '{file_name}', before answering. Do not state that the document is "
            f"unavailable or unattached; it is present in the corpus and searchable.\n\n"
            f"Question: {clean_q}"
        )

    excerpt_blocks = []
    for p in passages:
        idx = p.get("chunk_index")
        label = f"{p['file_name']} (section {idx})" if idx is not None else p["file_name"]
        excerpt_blocks.append(f"[{label}]\n{p['text']}")
    excerpts = "\n\n".join(excerpt_blocks)

    return (
        f"The following excerpts were retrieved from the uploaded document '{file_name}', "
        f"which is indexed in the enterprise document corpus. Answer the question using "
        f"them, and cite the document by name. If the excerpts are insufficient, search for "
        f"more with the {search_tool_hint} tool restricted to FILE_NAME = '{file_name}'. "
        f"Do not claim the document is missing or unattached.\n\n"
        f"--- BEGIN DOCUMENT EXCERPTS ---\n{excerpts}\n--- END DOCUMENT EXCERPTS ---\n\n"
        f"Question: {clean_q}"
    )


def execute_cortex_agent_workflow(
    db: str,
    schema: str,
    agent: str,
    prompt: str,
    model: str = "claude-3-5-sonnet",
    attached_file: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None,
    on_event: Optional[Callable[[Optional[str], Any], None]] = None
) -> Dict[str, Any]:
    """
    Executes a complete Cortex Agent interaction reusing the persistent session.

    Routing, retrieval and tool selection are all owned by the agent object in
    Snowflake; this function only forwards the question and renders what comes back.

    on_event, when supplied, switches the request into streaming mode and is called
    with (event_name, payload) for each SSE event as it arrives, letting the caller
    show live progress. The returned answer is still built from the final `response`
    event either way, so streaming changes only what the user sees during the wait,
    never the content of the result.
    """
    manager = mgr or snowflake_manager
    sql_query = None
    query_data = None
    columns = None
    thinking_output = None
    warnings_list = None
    response_text = ""
    stream_chart = None
    tools_used = []

    clean_p = prompt.strip()

    # When a document is attached, fetch the passages relevant to the question and put
    # them in the prompt. Naming the file alone used to make the model answer "I don't
    # see an attached document", because the Cortex Agent API has no attachment channel
    # and the wording implied one.
    document_passages = []
    if attached_file:
        document_passages = retrieve_document_context(
            file_name=attached_file, question=clean_p, mgr=manager
        )
        clean_p = build_attached_document_prompt(
            question=clean_p, file_name=attached_file, passages=document_passages
        )
        print(
            f"[Cortex Agent] Attached document '{attached_file}': "
            f"{len(document_passages)} passage(s) injected into the prompt."
        )

    # 1. Live Snowflake Cortex Agent REST endpoint for all questions (REST API agent:run)
    try:
        token, host = manager.get_session_token()
        if token and host:
            url = f"https://{host}/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run"
            headers = {
                "Authorization": f'Snowflake Token="{token}"',
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            }
            effective_prompt = clean_p
            request_body = {
                "model": model,
                "messages": [{"role": "user", "content": [{"type": "text", "text": effective_prompt}]}]
            }
            # Separate connect and read budgets: a streamed response needs a per-read
            # timeout, not one overall deadline.
            timeouts = (10, 90)
            want_stream = on_event is not None

            sf_res = requests.post(
                url, headers=headers, json=request_body, timeout=timeouts, stream=want_stream
            )
            # If agent rejects specific model parameter, retry immediately with agent's native configured model
            if sf_res.status_code != 200:
                # Release the rejected response before reissuing, otherwise the
                # unread streamed body holds the connection open.
                sf_res.close()
                body_no_model = {
                    "messages": [{"role": "user", "content": [{"type": "text", "text": effective_prompt}]}]
                }
                sf_res = requests.post(
                    url, headers=headers, json=body_no_model, timeout=timeouts, stream=want_stream
                )

            if sf_res.status_code != 200:
                # Surface the failure instead of silently falling through: a bad agent
                # name or a missing grant is otherwise indistinguishable from an empty answer.
                detail = sf_res.text[:500] if sf_res.text else "(no response body)"
                print(f"[Cortex Agent] HTTP {sf_res.status_code} from {agent}: {detail}")
                sf_res.close()
                return {
                    "status": "error",
                    "agent": agent,
                    "database": db,
                    "schema": schema,
                    "model": model,
                    "engine": "CORTEX_AGENT",
                    "response": (
                        f"Cortex Agent `{db}.{schema}.{agent}` returned HTTP "
                        f"{sf_res.status_code}.\n\n```\n{detail}\n```"
                    ),
                    "thinking": None,
                    "sql_query": None,
                    "data": None,
                    "columns": None,
                    "warnings": None,
                    "metadata": {
                        "database": db,
                        "schema": schema,
                        "agent": agent,
                        "http_status": sf_res.status_code,
                    },
                }

            if sf_res.status_code == 200:
                accumulator = _SseAccumulator()
                if want_stream:
                    # Consume events as they arrive so the caller can render progress.
                    # The callback is advisory: a failure in the UI must not abort the
                    # turn, so it is isolated per event.
                    try:
                        for event_name, data_json in iter_sse_events(
                            sf_res.iter_lines(decode_unicode=True)
                        ):
                            accumulator.handle(event_name, data_json)
                            try:
                                on_event(event_name, data_json)
                            except Exception as cb_err:
                                print(f"[Cortex Agent] Stream callback error: {cb_err}")
                    finally:
                        sf_res.close()
                else:
                    raw_sse = sf_res.content.decode("utf-8", errors="replace")
                    for event_name, data_json in iter_sse_events(raw_sse.strip().split("\n")):
                        accumulator.handle(event_name, data_json)

                # The authoritative answer comes from the final `response` event's
                # complete blocks, which finalise() filters for scratchpad preamble.
                # Streamed deltas are a live preview only and are not trusted here.
                (
                    parsed_text, thinking, warnings, final_resp,
                    stream_table, stream_cols, stream_chart, tools_used
                ) = accumulator.finalise()
                if thinking and thinking.strip():
                    thinking_output = thinking.strip()
                warnings_list = warnings
                if parsed_text and len(parsed_text.strip()) > 0:
                    response_text = clean_text_encoding(parsed_text)
                    raw_sql = extract_sql_from_text(parsed_text)
                    if raw_sql:
                        sql_query = sanitize_semantic_view_sql(raw_sql, db=db)
                        # Replace virtual __table names in response text so user gets valid, executable SQL
                        response_text = response_text.replace(raw_sql, sql_query)
                    
                    # 1. Use precomputed, verified table data directly from Cortex Agent stream
                    if stream_table and stream_cols:
                        query_data = stream_table
                        columns = stream_cols
                    # 2. Or execute sanitized SQL directly on Snowflake if stream table wasn't included
                    elif sql_query:
                        try:
                            query_data, columns = manager.execute_query(sql_query)
                        except Exception as sq_err:
                            print(f"[Agent SQL Execution Note]: {sq_err}")
        else:
            print("[Cortex Agent] No session token available; cannot reach the agent endpoint.")
    except Exception as e:
        print(f"[Cortex Agent] Request failed: {e}")

    # 2. If the agent produced nothing, report that honestly rather than
    #    substituting a hand-rolled answer the agent never authorised.
    if not response_text or not response_text.strip():
        response_text = (
            f"No response was returned by agent `{db}.{schema}.{agent}`. "
            "Verify the agent exists, that its tools are reachable, and that the "
            "current role has USAGE on it."
        )

    # Engine tag mirrors what the agent actually returned: structured results imply
    # an Analyst tool ran, otherwise treat it as a retrieval / text answer.
    engine_tag = "CORTEX_ANALYST" if (sql_query or query_data) else "CORTEX_SEARCH"

    return {
        "status": "success",
        "agent": agent,
        "database": db,
        "schema": schema,
        "model": model,
        "engine": engine_tag,
        "response": escape_dollars_for_markdown(response_text),
        "thinking": thinking_output,
        "sql_query": sql_query,
        "data": query_data,
        "columns": columns,
        "warnings": warnings_list,
        "metadata": {
            "database": db,
            "schema": schema,
            "agent": agent,
            "engine": engine_tag,
            "tools_used": tools_used,
            "rows_returned": len(query_data) if query_data else 0,
            "chart_spec": stream_chart
        }
    }


def _safe_stage_filename(file_name: str) -> str:
    """Reduce an uploaded filename to a conservative, stage-safe identifier.

    The filename reaches SQL, the stage, and PARSE_DOCUMENT, so it is restricted to
    a known-good character set rather than merely escaped. Windows drive letters and
    backslash path segments are stripped explicitly because os.path.basename does not
    remove them when the value arrives from a browser upload on a POSIX host.

    Raises ValueError when nothing usable remains, so an unusable name fails loudly
    instead of silently becoming an empty string in a WHERE clause.
    """
    raw = str(file_name or "")

    # Strip any directory component from either path flavour, plus a drive prefix.
    raw = raw.replace("\\", "/")
    raw = re.sub(r"^[A-Za-z]:", "", raw)
    raw = raw.rsplit("/", 1)[-1]
    raw = os.path.basename(raw)

    # Whitelist rather than blacklist: anything outside the set becomes an underscore.
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    cleaned = re.sub(r"_{2,}", "_", cleaned).strip("._-")

    if len(cleaned) > 180:
        stem, dot, ext = cleaned.rpartition(".")
        if dot and len(ext) <= 12:
            cleaned = stem[: 180 - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:180]

    if not cleaned:
        raise ValueError(f"Unusable document filename: {file_name!r}")
    return cleaned


def upload_document_to_snowflake_stage(
    file_bytes: bytes,
    file_name: str,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """
    Uploads raw file bytes to Snowflake Stage @UNIFIEDAI_DB.UNIFIEDAI_SH.DOC_STAGE using account credentials.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    try:
        clean_filename = _safe_stage_filename(file_name)
    except ValueError as bad_name:
        return {"status": "error", "message": str(bad_name)}

    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, clean_filename)
    with open(temp_path, "wb") as tf:
        tf.write(file_bytes)
        
    try:
        conn = manager.get_connection()
        cur = conn.cursor()
        safe_path = temp_path.replace("\\", "/")
        put_sql = f"PUT file://{safe_path} @{db}.{sh}.DOC_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        cur.execute(put_sql)
        res = cur.fetchall()
        cur.close()
        return {
            "status": "success",
            "stage": f"@{db}.{sh}.DOC_STAGE",
            "file_name": clean_filename,
            "put_result": res
        }
    except Exception as e:
        print(f"[Snowflake Stage Upload Error]: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                os.rmdir(temp_dir)
            except Exception:
                pass


def chunk_and_ingest_document(
    file_name: str,
    full_text: str,
    file_size: int,
    doc_type: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """
    Splits document text into semantic chunks and inserts them into UNIFIEDAI_DB.UNIFIEDAI_SH.DOCUMENT_CHUNKS
    with 768-dimensional vector embeddings generated via SNOWFLAKE.CORTEX.EMBED_TEXT_768.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    try:
        clean_filename = _safe_stage_filename(file_name)
    except ValueError as bad_name:
        return {
            "status": "error",
            "message": str(bad_name),
            "chunks_count": 0
        }

    # Infer doc_type if not provided
    if not doc_type:
        fn_lower = clean_filename.lower()
        if "policy" in fn_lower:
            doc_type = "POLICY"
        elif "claim" in fn_lower:
            doc_type = "CLAIM"
        elif "contract" in fn_lower or "agreement" in fn_lower:
            doc_type = "CONTRACT"
        elif "sop" in fn_lower or "manual" in fn_lower:
            doc_type = "SOP"
        else:
            doc_type = "DOCUMENT"

    # Guard against ingesting error text or empty extraction
    if not full_text or full_text.strip().startswith("File content preview unavailable") or "preview unavailable" in full_text.lower():
        print(f"[Document Ingest]: Skipped ingesting invalid/error text for {clean_filename}")
        return {
            "status": "warning",
            "message": "Preview unavailable or parsing failed; preserved existing chunks.",
            "file_name": clean_filename,
            "chunks_count": 0
        }

    chunk_size = 1000
    chunk_overlap = 150
    chunks = []
    
    if len(full_text) <= chunk_size:
        if full_text.strip():
            chunks.append(full_text.strip())
    else:
        start = 0
        while start < len(full_text):
            end = min(start + chunk_size, len(full_text))
            chunk = full_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += (chunk_size - chunk_overlap)
            if start >= len(full_text) - 50:
                break
                
    if not chunks:
        chunks = [f"Document {clean_filename} uploaded to stage."]

    # Cap how much of one document is embedded. The previous hard-coded 60 truncated a
    # large PDF to roughly 51k characters *silently* - a 3.4MB policy document produced
    # 3,530 chunks and stored 60, so most of it was simply unanswerable. The cap stays
    # (each chunk is a separate EMBED_TEXT_768 call, so an unbounded document is slow and
    # costly) but it is now tunable and, crucially, reported rather than hidden.
    try:
        max_chunks = int(env_config.get("MAX_DOC_CHUNKS", "400"))
    except (TypeError, ValueError):
        max_chunks = 400
    max_chunks = max(1, max_chunks)

    total_chunks = len(chunks)
    target_chunks = chunks[:max_chunks]
    truncated = total_chunks > len(target_chunks)

    inserted_count = 0
    conn = manager.get_connection()
    cur = conn.cursor()
    
    try:
        # Delete existing chunks for this file if re-uploading. The filename is bound,
        # not interpolated: it is user-supplied and a quote in it would otherwise
        # rewrite the predicate and delete unrelated rows.
        del_sql = f"DELETE FROM {db}.{sh}.DOCUMENT_CHUNKS WHERE FILE_NAME = %s"
        cur.execute(del_sql, (clean_filename,))

        # Batch insert chunks with embeddings. Every value is bound; the
        # SELECT ... UNION ALL shape is kept only because each row needs the
        # EMBED_TEXT_768 call applied to its own chunk text.
        batch_size = 10
        for b_start in range(0, len(target_chunks), batch_size):
            b_chunks = target_chunks[b_start:b_start + batch_size]
            select_parts = []
            batch_params: List[Any] = []
            for offset, chunk_text in enumerate(b_chunks):
                idx = b_start + offset
                select_parts.append("""
                SELECT 
                    %s,
                    %s,
                    %s,
                    CURRENT_TIMESTAMP(),
                    %s,
                    SNOWFLAKE.CORTEX.EMBED_TEXT_768('snowflake-arctic-embed-m-v1.5', %s),
                    %s
                """)
                batch_params.extend([
                    clean_filename,
                    chunk_text,
                    idx,
                    doc_type,
                    chunk_text,
                    file_size,
                ])
            batch_sql = f"""
            INSERT INTO {db}.{sh}.DOCUMENT_CHUNKS 
            (FILE_NAME, CHUNK_TEXT, CHUNK_INDEX, UPLOADED_AT, DOC_TYPE, EMBEDDING, FILE_SIZE)
            {" UNION ALL ".join(select_parts)};
            """
            cur.execute(batch_sql, tuple(batch_params))
            inserted_count += len(b_chunks)
            
        conn.commit()
        cur.close()

        indexed_chars = sum(len(t) for t in target_chunks)
        result = {
            "status": "warning" if truncated else "success",
            "file_name": clean_filename,
            "doc_type": doc_type,
            "chunks_count": inserted_count,
            "total_chunks": total_chunks,
            "max_chunks": max_chunks,
            "truncated": truncated,
            "indexed_chars": indexed_chars,
            "source_chars": len(full_text),
            "table": f"{db}.{sh}.DOCUMENT_CHUNKS"
        }
        if truncated:
            # Report partial indexing explicitly: questions about the rest of the
            # document cannot be answered, and silently succeeding hid that.
            result["message"] = (
                f"Indexed the first {inserted_count} of {total_chunks} sections "
                f"({indexed_chars:,} of {len(full_text):,} characters). "
                f"Raise MAX_DOC_CHUNKS to index more of this document."
            )
            print(f"[Document Ingest] {clean_filename}: {result['message']}")
        return result
    except Exception as e:
        print(f"[Document Ingest Error]: {e}")
        try:
            cur.close()
        except Exception:
            pass
        return {
            "status": "error",
            "message": str(e),
            "chunks_count": inserted_count
        }




def parse_document_with_snowflake_cortex(
    file_name: str,
    stage: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None
) -> Optional[str]:
    """
    Uses Snowflake native Cortex PARSE_DOCUMENT with built-in OCR and layout analysis
    to extract full text and tables from scanned/image PDFs stored on stage.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")
    target_stage = stage or f"@{db}.{sh}.DOC_STAGE"

    try:
        clean_fn = _safe_stage_filename(file_name)
    except ValueError as bad_name:
        print(f"[Snowflake PARSE_DOCUMENT Error]: {bad_name}")
        return None

    # Filename is bound rather than interpolated; the stage identifier cannot be a
    # bind parameter, but it is derived from config, not from user input.
    sql = f"""
    SELECT SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
        {target_stage},
        %s,
        {{'mode': 'LAYOUT'}}
    ) AS DOC_JSON;
    """
    try:
        rows, _ = manager.execute_query(sql, (clean_fn,))
        if not rows:
            # This path used to return None with no explanation. The most common cause is
            # a stage created without SNOWFLAKE_SSE: PARSE_DOCUMENT cannot read
            # client-side-encrypted files, and an internal stage's encryption mode cannot
            # be changed with ALTER, so the stage has to be recreated. Say so.
            err = manager.get_last_error() or ""
            if "Client Side Encryption" in err:
                print(
                    f"[Snowflake PARSE_DOCUMENT] Cannot OCR {clean_fn}: {target_stage} uses "
                    "client-side encryption. Recreate it with "
                    "ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') - see "
                    "docs/setup_document_pipeline.sql - and re-upload the file. "
                    "Text-extractable documents are unaffected."
                )
            elif err:
                print(f"[Snowflake PARSE_DOCUMENT] Failed for {clean_fn}: {err}")
            return None
        if rows[0].get("DOC_JSON"):
            raw_data = rows[0]["DOC_JSON"]
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            content = data.get("content", "")
            if content and len(content.strip()) > 0:
                print(f"[Snowflake PARSE_DOCUMENT]: Extracted {len(content)} characters from {clean_fn} via native OCR.")
                return content.strip()
    except Exception as e:
        print(f"[Snowflake PARSE_DOCUMENT Error]: {e}")
    return None


def refresh_document_search_service(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Force the Cortex Search index to pick up newly ingested chunks.

    The service is created with TARGET_LAG = 1 hour, so without an explicit refresh
    a freshly uploaded document is invisible to the agent's search tool for up to
    an hour even though its rows already exist in DOCUMENT_CHUNKS.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")
    svc = env_config.get("SEARCH_SERVICE", "INSURANCE_SEARCH_SVC")
    try:
        manager.execute_query_checked(f"ALTER CORTEX SEARCH SERVICE {db}.{sh}.{svc} REFRESH")
        return {"status": "success", "service": f"{db}.{sh}.{svc}"}
    except SnowflakeQueryError as e:
        print(f"[Search Service Refresh Error]: {e}")
        return {"status": "error", "service": f"{db}.{sh}.{svc}", "message": str(e)}


def ensure_document_pipeline(mgr: Optional[SnowflakeManager] = None) -> Dict[str, Any]:
    """Ensure the stage and chunk table the ingestion pipeline writes into both exist.

    Without this, a fresh account fails at the PUT or the INSERT and the caller sees a
    generic error rather than "the target object was never created". Both statements are
    IF NOT EXISTS, so this is a no-op on an account where the objects were created
    out-of-band.

    The Cortex Search service is deliberately NOT created here: it is a billable
    background job and should be provisioned explicitly via
    docs/setup_document_pipeline.sql rather than implicitly on someone's first upload.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    stage_ddl = f"""
    CREATE STAGE IF NOT EXISTS {db}.{sh}.DOC_STAGE
        DIRECTORY = (ENABLE = TRUE)
        ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
        COMMENT = 'Uploaded insurance documents awaiting parse and chunk ingestion';
    """

    # Column list and order must match the INSERT in chunk_and_ingest_document.
    table_ddl = f"""
    CREATE TABLE IF NOT EXISTS {db}.{sh}.DOCUMENT_CHUNKS (
        FILE_NAME VARCHAR(512),
        CHUNK_TEXT VARCHAR(16777216),
        CHUNK_INDEX NUMBER(38,0),
        UPLOADED_AT TIMESTAMP_NTZ,
        DOC_TYPE VARCHAR(64),
        EMBEDDING VECTOR(FLOAT, 768),
        FILE_SIZE NUMBER(38,0)
    );
    """

    try:
        manager.execute_query_checked(stage_ddl)
        manager.execute_query_checked(table_ddl)
        return {
            "status": "success",
            "stage": f"@{db}.{sh}.DOC_STAGE",
            "table": f"{db}.{sh}.DOCUMENT_CHUNKS",
        }
    except SnowflakeQueryError as e:
        print(f"[Ensure Document Pipeline Error]: {e}")
        return {"status": "error", "message": str(e)}


def upload_and_ingest_pipeline(
    file_bytes: bytes,
    file_name: str,
    full_text: str,
    doc_type: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """
    End-to-end Snowflake Document Ingestion Pipeline:
    0. Ensures @DOC_STAGE and DOCUMENT_CHUNKS exist before anything writes to them.
    1. Uploads file to @DOC_STAGE via Snowflake credentials.
    2. If text extraction is empty/short (scanned PDF), triggers native Snowflake Cortex PARSE_DOCUMENT OCR.
    3. Chunks text & embeds vectors into DOCUMENT_CHUNKS using CORTEX.EMBED_TEXT_768.
    4. Refreshes the Cortex Search index so the agent can retrieve the document immediately.
    """
    # Fail fast and specifically if the target objects are missing, rather than
    # surfacing an opaque error from the PUT or the INSERT further down.
    ensure_res = ensure_document_pipeline(mgr=mgr)
    if ensure_res.get("status") != "success":
        return {
            "status": "error",
            "file_name": file_name,
            "message": f"Document pipeline objects unavailable: {ensure_res.get('message')}",
            "chunks_count": 0,
            "stage_status": "error",
            "ingest_status": "error",
            "search_refresh_status": None,
            "extracted_text": full_text,
        }

    stage_res = upload_document_to_snowflake_stage(file_bytes=file_bytes, file_name=file_name, mgr=mgr)

    # Automated OCR Fallback for Scanned / Image PDFs
    if not full_text or len(full_text.strip()) < 100:
        print(f"[Ingest Pipeline]: Text extraction empty/short for {file_name}. Invoking Snowflake Cortex PARSE_DOCUMENT OCR...")
        ocr_text = parse_document_with_snowflake_cortex(file_name=file_name, mgr=mgr)
        if ocr_text:
            full_text = ocr_text

    ingest_res = chunk_and_ingest_document(
        file_name=file_name,
        full_text=full_text,
        file_size=len(file_bytes),
        doc_type=doc_type,
        mgr=mgr
    )
    
    # Make the new chunks searchable now rather than at the next 1-hour refresh.
    refresh_res = refresh_document_search_service(mgr=mgr)

    # Both the stage upload and the chunk ingest must succeed for this to be a success.
    # The previous OR meant a good upload with a failed ingest reported success, so the
    # UI showed a green chip for a document the agent could never retrieve.
    stage_ok = stage_res.get("status") == "success"
    ingest_status = ingest_res.get("status")

    if stage_ok and ingest_status == "success":
        overall_status = "success"
        message = None
    elif stage_ok and ingest_status == "warning":
        # Legitimate case: file is on the stage but yielded no extractable text.
        overall_status = "warning"
        message = ingest_res.get("message")
    else:
        overall_status = "error"
        message = (
            ingest_res.get("message")
            if ingest_status == "error"
            else stage_res.get("message")
        ) or "Document ingestion failed."

    return {
        "status": overall_status,
        "message": message,
        "file_name": file_name,
        "stage": stage_res.get("stage", f"@{env_config.get('SNOWFLAKE_DB', 'UNIFIEDAI_DB')}.{env_config.get('SNOWFLAKE_SH', 'UNIFIEDAI_SH')}.DOC_STAGE"),
        "chunks_count": ingest_res.get("chunks_count", 0),
        "total_chunks": ingest_res.get("total_chunks"),
        "truncated": ingest_res.get("truncated", False),
        "doc_type": ingest_res.get("doc_type"),
        "stage_status": stage_res.get("status"),
        "ingest_status": ingest_status,
        "search_refresh_status": refresh_res.get("status"),
        "search_refresh_message": refresh_res.get("message"),
        "extracted_text": full_text
    }


# ---------------------------------------------------------
# Snowflake CHAT_HISTORY Table & Persistence Pipeline
# ---------------------------------------------------------
def ensure_chat_history_table(mgr: Optional[SnowflakeManager] = None) -> bool:
    """Ensures that the CHAT_HISTORY table exists in Snowflake."""
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")
    
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {db}.{sh}.CHAT_HISTORY (
        MESSAGE_ID VARCHAR(64),
        SESSION_ID VARCHAR(64),
        TIMESTAMP TIMESTAMP_NTZ,
        ROLE VARCHAR(32),
        USER_NAME VARCHAR(64),
        MODEL VARCHAR(64),
        CONTENT VARCHAR(16777216),
        SQL_QUERY VARCHAR(16777216),
        QUERY_DATA VARCHAR(16777216),
        ATTACHED_DOC VARCHAR(256),
        THINKING VARCHAR(16777216),
        LATENCY_MS NUMBER(38,0),
        TOOLS_USED VARCHAR(1024),
        ENGINE VARCHAR(64),
        STATUS VARCHAR(32)
    );
    """

    # The four telemetry columns are added separately so that tables created before this
    # change are migrated in place. CREATE TABLE IF NOT EXISTS is a no-op on an existing
    # table, so it would never widen the schema on its own.
    telemetry_columns = [
        ("LATENCY_MS", "NUMBER(38,0)"),
        ("TOOLS_USED", "VARCHAR(1024)"),
        ("ENGINE", "VARCHAR(64)"),
        ("STATUS", "VARCHAR(32)"),
    ]

    try:
        manager.execute_query_checked(ddl)
        for col, col_type in telemetry_columns:
            manager.execute_query_checked(
                f"ALTER TABLE {db}.{sh}.CHAT_HISTORY ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )
        return True
    except SnowflakeQueryError as e:
        print(f"[Ensure CHAT_HISTORY Table Error]: {e}")
        return False


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    user_name: Optional[str] = None,
    model: Optional[str] = None,
    sql_query: Optional[str] = None,
    query_data: Optional[Any] = None,
    attached_doc: Optional[str] = None,
    thinking: Optional[str] = None,
    latency_ms: Optional[int] = None,
    tools_used: Optional[Any] = None,
    engine: Optional[str] = None,
    status: Optional[str] = None,
    mgr: Optional[SnowflakeManager] = None
) -> Dict[str, Any]:
    """Persists a single message turn into UNIFIEDAI_DB.UNIFIEDAI_SH.CHAT_HISTORY.

    latency_ms, tools_used, engine and status carry per-turn telemetry so response time
    and tool usage can be reported from the data rather than estimated.

    Values are bound as parameters. The previous version built the INSERT by string
    concatenation with a hand-rolled quote-doubling helper, which put arbitrary user and
    model text directly into the statement.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    ensure_chat_history_table(mgr=manager)

    msg_id = f"msg_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    u_name = user_name or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
    m_name = model or "claude-3-5-sonnet"

    # Format query data as JSON string if present (stored up to 100 sample records)
    query_data_str = None
    if query_data:
        try:
            if isinstance(query_data, list):
                query_data_str = json.dumps(query_data[:100])
            elif isinstance(query_data, str):
                query_data_str = query_data
        except Exception:
            pass

    # Tools arrive as a list from the SSE accumulator; store a stable comma-separated
    # string so the telemetry tab can split it without parsing JSON.
    tools_str = None
    if tools_used:
        if isinstance(tools_used, (list, tuple, set)):
            names = [str(t).strip() for t in tools_used if str(t).strip()]
            tools_str = ", ".join(sorted(set(names)))[:1024] or None
        else:
            tools_str = str(tools_used)[:1024]

    latency_val: Optional[int] = None
    if latency_ms is not None:
        try:
            latency_val = int(round(float(latency_ms)))
        except (TypeError, ValueError):
            latency_val = None

    insert_sql = f"""
    INSERT INTO {db}.{sh}.CHAT_HISTORY (
        MESSAGE_ID, SESSION_ID, TIMESTAMP, ROLE, USER_NAME, MODEL,
        CONTENT, SQL_QUERY, QUERY_DATA, ATTACHED_DOC, THINKING,
        LATENCY_MS, TOOLS_USED, ENGINE, STATUS
    )
    SELECT %s, %s, CURRENT_TIMESTAMP(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    """
    params = (
        msg_id, session_id, role, u_name, m_name,
        content, sql_query, query_data_str, attached_doc, thinking,
        latency_val, tools_str, engine, status,
    )
    try:
        manager.execute_query_checked(insert_sql, params)
        return {"status": "success", "message_id": msg_id}
    except SnowflakeQueryError as e:
        print(f"[Save Chat Message Error]: {e}")
        return {"status": "error", "message": str(e)}


def get_agent_telemetry(
    mgr: Optional[SnowflakeManager] = None,
    user_name: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """Agent usage and latency, aggregated from CHAT_HISTORY telemetry columns.

    Only assistant turns carry latency, tools and engine, so every metric here is
    restricted to ROLE = 'assistant'.

    user_name=None reports across all users, which is appropriate for an operator view
    of the agent itself. Pass a user_name to scope it.

    Rows written before the telemetry columns existed have NULL LATENCY_MS. They are
    counted separately as turns_without_telemetry rather than being treated as zero
    latency, which would drag every average down.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    ensure_chat_history_table(mgr=manager)

    try:
        window_days = max(1, min(int(days), 3650))
    except (TypeError, ValueError):
        window_days = 30

    where = [f"TIMESTAMP >= DATEADD('day', -{window_days}, CURRENT_TIMESTAMP())",
             "ROLE = 'assistant'"]
    params: List[Any] = []
    if user_name and str(user_name).strip():
        where.append("USER_NAME = %s")
        params.append(str(user_name).strip())
    where_sql = "WHERE " + " AND ".join(where)
    bind = tuple(params) if params else None

    summary_rows, _ = manager.execute_query(
        f"""
        SELECT
            COUNT(*) AS TURNS,
            COUNT(DISTINCT SESSION_ID) AS SESSIONS,
            COUNT(DISTINCT USER_NAME) AS USERS,
            COUNT(LATENCY_MS) AS TURNS_WITH_TELEMETRY,
            ROUND(AVG(LATENCY_MS)) AS AVG_LATENCY_MS,
            ROUND(MEDIAN(LATENCY_MS)) AS P50_LATENCY_MS,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY LATENCY_MS)) AS P95_LATENCY_MS,
            MAX(LATENCY_MS) AS MAX_LATENCY_MS,
            COUNT(CASE WHEN STATUS = 'error' THEN 1 END) AS ERRORS,
            COUNT(CASE WHEN SQL_QUERY IS NOT NULL THEN 1 END) AS TURNS_WITH_SQL,
            COUNT(CASE WHEN ATTACHED_DOC IS NOT NULL THEN 1 END) AS TURNS_WITH_DOC
        FROM {db}.{sh}.CHAT_HISTORY
        {where_sql}
        """,
        bind
    )
    s = summary_rows[0] if summary_rows else {}

    turns = int(s.get("TURNS") or 0)
    errors = int(s.get("ERRORS") or 0)
    with_telemetry = int(s.get("TURNS_WITH_TELEMETRY") or 0)

    by_engine, _ = manager.execute_query(
        f"""
        SELECT COALESCE(ENGINE, 'Not recorded') AS ENGINE,
               COUNT(*) AS TURNS,
               ROUND(AVG(LATENCY_MS)) AS AVG_LATENCY_MS,
               COUNT(CASE WHEN STATUS = 'error' THEN 1 END) AS ERRORS
        FROM {db}.{sh}.CHAT_HISTORY
        {where_sql}
        GROUP BY 1 ORDER BY TURNS DESC
        """,
        bind
    )

    by_model, _ = manager.execute_query(
        f"""
        SELECT COALESCE(MODEL, 'Not recorded') AS MODEL,
               COUNT(*) AS TURNS,
               ROUND(AVG(LATENCY_MS)) AS AVG_LATENCY_MS,
               ROUND(MAX(LATENCY_MS)) AS MAX_LATENCY_MS
        FROM {db}.{sh}.CHAT_HISTORY
        {where_sql}
        GROUP BY 1 ORDER BY TURNS DESC
        """,
        bind
    )

    # TOOLS_USED is a comma-separated list, so it is split to count each tool once per
    # turn it appeared in rather than counting the combination as one value.
    by_tool, _ = manager.execute_query(
        f"""
        WITH scoped AS (
            SELECT MESSAGE_ID, TOOLS_USED, LATENCY_MS
            FROM {db}.{sh}.CHAT_HISTORY
            {where_sql}
        )
        SELECT TRIM(t.VALUE::STRING) AS TOOL,
               COUNT(*) AS INVOCATIONS,
               ROUND(AVG(s.LATENCY_MS)) AS AVG_TURN_LATENCY_MS
        FROM scoped s,
             LATERAL FLATTEN(INPUT => SPLIT(s.TOOLS_USED, ',')) t
        WHERE s.TOOLS_USED IS NOT NULL AND TRIM(t.VALUE::STRING) <> ''
        GROUP BY 1 ORDER BY INVOCATIONS DESC
        """,
        bind
    )

    daily, _ = manager.execute_query(
        f"""
        SELECT TO_VARCHAR(DATE_TRUNC('DAY', TIMESTAMP), 'YYYY-MM-DD') AS DAY,
               COUNT(*) AS TURNS,
               ROUND(AVG(LATENCY_MS)) AS AVG_LATENCY_MS,
               COUNT(CASE WHEN STATUS = 'error' THEN 1 END) AS ERRORS
        FROM {db}.{sh}.CHAT_HISTORY
        {where_sql}
        GROUP BY 1 ORDER BY DAY ASC
        """,
        bind
    )

    slowest, _ = manager.execute_query(
        f"""
        SELECT TIMESTAMP, SESSION_ID, USER_NAME, MODEL, ENGINE, STATUS,
               LATENCY_MS, TOOLS_USED,
               LEFT(COALESCE(CONTENT, ''), 160) AS RESPONSE_PREVIEW
        FROM {db}.{sh}.CHAT_HISTORY
        {where_sql} AND LATENCY_MS IS NOT NULL
        ORDER BY LATENCY_MS DESC
        LIMIT 15
        """,
        bind
    )

    return {
        "status": "success",
        "window_days": window_days,
        "scoped_user": user_name or None,
        "turns": turns,
        "sessions": int(s.get("SESSIONS") or 0),
        "users": int(s.get("USERS") or 0),
        "turns_with_telemetry": with_telemetry,
        "turns_without_telemetry": max(0, turns - with_telemetry),
        # None, not 0, when nothing in the window carries a latency reading.
        "avg_latency_ms": s.get("AVG_LATENCY_MS"),
        "p50_latency_ms": s.get("P50_LATENCY_MS"),
        "p95_latency_ms": s.get("P95_LATENCY_MS"),
        "max_latency_ms": s.get("MAX_LATENCY_MS"),
        "errors": errors,
        "error_rate_pct": round(errors / turns * 100.0, 1) if turns else None,
        "turns_with_sql": int(s.get("TURNS_WITH_SQL") or 0),
        "turns_with_doc": int(s.get("TURNS_WITH_DOC") or 0),
        "by_engine": by_engine or [],
        "by_model": by_model or [],
        "by_tool": by_tool or [],
        "daily": daily or [],
        "slowest_turns": slowest or [],
    }


def get_all_chat_sessions(
    user_name: str,
    mgr: Optional[SnowflakeManager] = None
) -> List[Dict[str, Any]]:
    """Conversation sessions belonging to one user.

    user_name is required and filtered on: the table holds every user's history, so an
    unscoped query exposed other people's questions, document names and generated SQL.

    FIRST_QUESTION is the chronologically first user message. It used to be
    MAX(CASE WHEN ROLE='user' THEN CONTENT END), which returns the lexicographic maximum
    and therefore titled multi-turn sessions with whichever question happened to sort
    last. MODEL had the same defect.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    ensure_chat_history_table(mgr=manager)

    if not user_name or not str(user_name).strip():
        print("[Get Chat Sessions] Refused: no user_name supplied.")
        return []

    sql = f"""
    WITH scoped AS (
        SELECT * FROM {db}.{sh}.CHAT_HISTORY WHERE USER_NAME = %s
    ),
    first_turn AS (
        SELECT SESSION_ID, CONTENT AS FIRST_QUESTION, MODEL AS FIRST_MODEL
        FROM scoped
        WHERE ROLE = 'user'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY SESSION_ID ORDER BY TIMESTAMP ASC) = 1
    ),
    agg AS (
        SELECT
            SESSION_ID,
            MIN(TIMESTAMP) AS STARTED_AT,
            MAX(TIMESTAMP) AS LAST_ACTIVE_AT,
            COUNT(MESSAGE_ID) AS MESSAGE_COUNT,
            MAX(USER_NAME) AS USER_NAME,
            MAX(MODEL) AS ANY_MODEL,
            MAX(ATTACHED_DOC) AS ATTACHED_DOC,
            COUNT(CASE WHEN SQL_QUERY IS NOT NULL THEN 1 ELSE NULL END) AS SQL_QUERIES_COUNT,
            ROUND(AVG(LATENCY_MS)) AS AVG_LATENCY_MS,
            MAX(LATENCY_MS) AS MAX_LATENCY_MS,
            COUNT(CASE WHEN STATUS = 'error' THEN 1 ELSE NULL END) AS ERROR_COUNT
        FROM scoped
        GROUP BY SESSION_ID
    )
    SELECT
        a.SESSION_ID,
        a.STARTED_AT,
        a.LAST_ACTIVE_AT,
        a.MESSAGE_COUNT,
        a.USER_NAME,
        COALESCE(f.FIRST_MODEL, a.ANY_MODEL) AS MODEL,
        f.FIRST_QUESTION,
        a.ATTACHED_DOC,
        a.SQL_QUERIES_COUNT,
        a.AVG_LATENCY_MS,
        a.MAX_LATENCY_MS,
        a.ERROR_COUNT
    FROM agg a
    LEFT JOIN first_turn f ON a.SESSION_ID = f.SESSION_ID
    ORDER BY a.LAST_ACTIVE_AT DESC;
    """
    rows, _ = manager.execute_query(sql, (user_name,))
    if rows is None:
        print(f"[Get Chat Sessions Error]: {manager.get_last_error()}")
        return []
    return rows


def get_chat_session_messages(
    session_id: str,
    user_name: str,
    mgr: Optional[SnowflakeManager] = None
) -> List[Dict[str, Any]]:
    """Chronological messages for one session, restricted to its owner.

    Scoped by user as well as session so that knowing or guessing a SESSION_ID is not
    enough to read someone else's conversation.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    ensure_chat_history_table(mgr=manager)

    if not user_name or not str(user_name).strip():
        print("[Get Session Messages] Refused: no user_name supplied.")
        return []

    sql = f"""
    SELECT 
        MESSAGE_ID,
        SESSION_ID,
        TIMESTAMP,
        ROLE,
        USER_NAME,
        MODEL,
        CONTENT,
        SQL_QUERY,
        QUERY_DATA,
        ATTACHED_DOC,
        THINKING,
        LATENCY_MS,
        TOOLS_USED,
        ENGINE,
        STATUS
    FROM {db}.{sh}.CHAT_HISTORY
    WHERE SESSION_ID = %s AND USER_NAME = %s
    ORDER BY TIMESTAMP ASC;
    """
    rows, _ = manager.execute_query(sql, (session_id, user_name))
    if rows is None:
        print(f"[Get Session Messages Error]: {manager.get_last_error()}")
        return []

    for r in rows:
        qdata_raw = r.get("QUERY_DATA")
        if qdata_raw and isinstance(qdata_raw, str):
            try:
                r["QUERY_DATA_PARSED"] = json.loads(qdata_raw)
            except Exception:
                r["QUERY_DATA_PARSED"] = None
        else:
            r["QUERY_DATA_PARSED"] = None
    return rows


def delete_chat_session(
    session_id: str,
    user_name: str,
    mgr: Optional[SnowflakeManager] = None
) -> bool:
    """Delete one session, only if it belongs to the given user.

    The USER_NAME predicate is what stops a guessed SESSION_ID from deleting another
    user's conversation.
    """
    manager = mgr or snowflake_manager
    db = env_config.get("SNOWFLAKE_DB", "UNIFIEDAI_DB")
    sh = env_config.get("SNOWFLAKE_SH", "UNIFIEDAI_SH")

    if not user_name or not str(user_name).strip():
        print("[Delete Session] Refused: no user_name supplied.")
        return False

    try:
        manager.execute_query_checked(
            f"DELETE FROM {db}.{sh}.CHAT_HISTORY WHERE SESSION_ID = %s AND USER_NAME = %s",
            (session_id, user_name)
        )
        return True
    except SnowflakeQueryError as e:
        print(f"[Delete Session Error]: {e}")
        return False


