"""Toast notifications that survive a rerun.

st.toast paints into the current run only. Most write actions in this app finish with
st.rerun() to refresh caches, which discards anything emitted just before it - the
existing st.success("Matches generated.") calls were never actually visible for that
reason. Queueing the message in session_state and flushing it at the top of the next
run is what makes a post-action confirmation appear at all.
"""
from typing import Optional

import streamlit as st

_QUEUE_KEY = "_pending_toasts"

# Kept small and named so call sites read as intent rather than emoji soup.
ICONS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "💡",
    "working": "⏳",
    "saved": "💾",
    "chart": "📊",
    "doc": "📄",
    "deleted": "🗑️",
}


def toast_now(message: str, kind: str = "info", icon: Optional[str] = None) -> None:
    """Show a toast in the current run. Use when no rerun follows."""
    if not message:
        return
    st.toast(str(message), icon=icon or ICONS.get(kind, ICONS["info"]))


def queue_toast(message: str, kind: str = "info", icon: Optional[str] = None) -> None:
    """Hold a toast for the next run. Use immediately before st.rerun()."""
    if not message:
        return
    st.session_state.setdefault(_QUEUE_KEY, []).append(
        (str(message), icon or ICONS.get(kind, ICONS["info"]))
    )


def flush_toasts() -> None:
    """Emit and clear anything queued by the previous run.

    Call once near the top of every page, after the page config. Popping rather than
    reading means a queued toast shows exactly once and cannot stick across reruns.
    """
    for message, icon in st.session_state.pop(_QUEUE_KEY, []):
        st.toast(message, icon=icon)
