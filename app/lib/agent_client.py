"""Cortex Agent client helpers shared by the Streamlit pages.

The agent is invoked in-process against the persistent Snowflake session, which
issues the Cortex Agent REST call itself. There is no intermediate HTTP hop.
"""
from typing import Any, Callable, Dict, Optional

import streamlit as st

import services.backend_service as backend_service


@st.cache_data(ttl=25)
def fetch_snowflake_status(_mgr=None, _env_config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Return live Snowflake session context, falling back to configured defaults."""
    env = _env_config or {}
    try:
        return backend_service.get_snowflake_status(mgr=_mgr)
    except Exception as status_err:
        print(f"[Snowflake Status] Falling back to configured defaults: {status_err}")
    return {
        "connected": False,
        "user": env.get("SNOWFLAKE_USERNAME", "UNIFIEDAI"),
        "role": env.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": env.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": env.get("SNOWFLAKE_DB", "UNIFIEDAI_DB"),
        "schema": env.get("SNOWFLAKE_SH", "UNIFIEDAI_SH"),
        "default_agent": env.get("INS_AGENT", "UNIFIED_ENTERPRISE_AGENT"),
    }


def call_cortex_agent(
    db: str,
    schema: str,
    agent: str,
    prompt: str,
    model: str,
    attached_file: Optional[str] = None,
    mgr=None,
    on_event: Optional[Callable[[Optional[str], Any], None]] = None,
) -> Dict[str, Any]:
    """Run one turn against the Cortex Agent, reusing the persistent session.

    Pass on_event to stream progress events as they arrive; omit it for a single
    buffered response.
    """
    try:
        return backend_service.execute_cortex_agent_workflow(
            db=db,
            schema=schema,
            agent=agent,
            prompt=prompt,
            model=model,
            attached_file=attached_file,
            mgr=mgr,
            on_event=on_event,
        )
    except Exception as agent_err:
        return {
            "status": "error",
            "response": f"Agent call failed: {agent_err}",
            "agent": agent,
            "database": db,
            "schema": schema,
            "model": model,
        }
