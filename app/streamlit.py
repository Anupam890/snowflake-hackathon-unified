"""
Streamlit Entry Point & Dynamic Multi-Tab Dispatcher.
Allows launching via `streamlit run streamlit.py` or `streamlit run app/streamlit_app.py`.
Executes the main application dynamically on every Streamlit rerun cycle.
"""
import os
import sys
import runpy

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Note: services.backend_service is deliberately NOT reloaded here. Reloading it
# re-executes its imports against whatever is already cached in sys.modules, so any
# new name added to config.snowflake_manager raised ImportError until the server was
# restarted. Streamlit already re-runs this script on every interaction, so the
# reload was never needed.
app_file = os.path.join(os.path.dirname(__file__), "streamlit_app.py")
runpy.run_path(app_file, run_name="__main__")