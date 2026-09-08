import os
import streamlit as st

def inject_custom_css():
    """Injects the enterprise stylesheet across all views and multi-page apps."""
    css_file = os.path.join(os.path.dirname(__file__), "style.css")
    if os.path.exists(css_file):
        try:
            with open(css_file, "r", encoding="utf-8") as f:
                css_content = f.read()
            st.markdown(f"<style>\n{css_content}\n</style>", unsafe_allow_html=True)
        except Exception as e:
            print(f"[CSS Loader] Error loading style.css: {e}")
