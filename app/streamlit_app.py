# import os
import sys
import json
import html
import datetime
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import pydeck as pdk
from dotenv import dotenv_values
import streamlit as st

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
try:
    st.set_page_config(
        page_title=" INSIGHT AI — Insurance Intelligence Studio",
        page_icon="❄️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

import streamlit.components.v1 as components


# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.snowflake_manager import get_st_cached_snowflake_manager
import services.backend_service as backend_service
from app.lib.agent_client import call_cortex_agent, fetch_snowflake_status
from app.lib.render import extract_uploaded_file_content, render_assistant_response
from app.lib.toasts import flush_toasts, queue_toast, toast_now

# Load environment configuration
env_config = {k.strip(): v.strip() for k, v in dotenv_values(os.path.join(PROJECT_ROOT, '.env')).items()}

# Get persistent cached Snowflake manager (reused across all reruns, avoiding Duo prompts)
cached_sf_mgr = get_st_cached_snowflake_manager()

# Emit anything a previous run queued just before calling st.rerun().
flush_toasts()

# Premium Custom CSS Design System
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* ========================================================= */
    /* Hide ONLY Deploy, 3-Dots Menu & Decoration Bar            */
    /* KEEP Sidebar Toggle Visible & Fully Functional            */
    /* ========================================================= */
    #MainMenu,
    .stAppDeployButton,
    div[data-testid="stDeployButton"],
    div[data-testid="stDecoration"],
    footer {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        width: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }

    /* Make header zero-height so it takes no space, while keeping interactive controls visible */
    header[data-testid="stHeader"] {
        background: transparent !important;
        background-color: transparent !important;
        border: none !important;
        height: 0px !important;
        min-height: 0px !important;
        max-height: 0px !important;
        padding: 0px !important;
        margin: 0px !important;
        overflow: visible !important;
        pointer-events: none !important;
        z-index: 10000000 !important;
    }
    header[data-testid="stHeader"] * {
        pointer-events: auto !important;
    }

    /* Sidebar Collapse & Expand Toggle Controls - Explicitly Visible & Clickable */
    div[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"],
    div[data-testid="stSidebarCollapsedControl"],
    div[data-testid="stSidebarHeader"] button,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 10000002 !important;
    }

    /* Expand Button (When Sidebar is Collapsed) */
    div[data-testid="collapsedControl"] {
        position: fixed !important;
        top: 8px !important;
        left: 12px !important;
        background: rgba(15, 23, 42, 0.96) !important;
        border: 1px solid rgba(56, 189, 248, 0.6) !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.7), 0 0 12px rgba(56, 189, 248, 0.35) !important;
        padding: 3px !important;
        cursor: pointer !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[data-testid="collapsedControl"]:hover {
        background: rgba(30, 41, 59, 1) !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.6) !important;
        transform: scale(1.05) !important;
    }
    div[data-testid="collapsedControl"] button {
        color: #38BDF8 !important;
        background: transparent !important;
        border: none !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 4px 6px !important;
    }
    div[data-testid="collapsedControl"] svg {
        fill: #38BDF8 !important;
        width: 20px !important;
        height: 20px !important;
    }

    /* Adjust navbar brand container when sidebar is collapsed so expand button has clean spacing */
    .stApp:has(div[data-testid="collapsedControl"]) .top-navbar .brand-container,
    div[data-testid="stAppViewContainer"]:has(div[data-testid="collapsedControl"]) .top-navbar .brand-container {
        padding-left: 54px !important;
        transition: padding-left 0.2s ease !important;
    }

    /* Sidebar Header (When Sidebar is Open) */
    section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {
        display: flex !important;
        visibility: visible !important;
        align-items: center !important;
        justify-content: flex-end !important;
        padding: 8px 12px 2px 12px !important;
        margin: 0 !important;
        background: transparent !important;
        border: none !important;
        box-sizing: border-box !important;
    }
    button[data-testid="stSidebarCollapseButton"],
    div[data-testid="stSidebarHeader"] button,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] {
        color: #94A3B8 !important;
        background: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(148, 163, 184, 0.3) !important;
        border-radius: 8px !important;
        padding: 4px 8px !important;
        height: 32px !important;
        min-height: 32px !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    button[data-testid="stSidebarCollapseButton"]:hover,
    div[data-testid="stSidebarHeader"] button:hover,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"]:hover {
        color: #38BDF8 !important;
        background: rgba(56, 189, 248, 0.2) !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.4) !important;
    }
    button[data-testid="stSidebarCollapseButton"] svg,
    div[data-testid="stSidebarHeader"] button svg,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] svg {
        fill: #94A3B8 !important;
    }
    button[data-testid="stSidebarCollapseButton"]:hover svg,
    div[data-testid="stSidebarHeader"] button:hover svg,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"]:hover svg {
        fill: #38BDF8 !important;
    }

    /* Ensure Right Side (Main Content Area) Has Full Native Smooth Scrolling */
    section.main,
    section[data-testid="stMain"],
    .main,
    div[data-testid="stAppViewContainer"] > section {
        overflow-y: auto !important;
        overflow-x: hidden !important;
        height: 100vh !important;
        position: relative !important;
        padding-top: 0px !important;
        margin-top: 0px !important;
    }

    /* Zero Top Padding for Main Inner Block Containers */
    div[data-testid="stMainBlockContainer"],
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="block-container"],
    .block-container {
        padding-top: 0px !important;
        margin-top: 0px !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 100% !important;
        overflow: visible !important;
    }

    /* Hide empty element containers, style-only containers & iframe helpers */
    div[data-testid="element-container"]:empty,
    div[data-testid="stElementContainer"]:empty,
    div[data-testid="element-container"]:has(style:only-child),
    div[data-testid="stElementContainer"]:has(style:only-child),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(style:only-child),
    iframe[title="streamlit.components.v1.html"] {
        display: none !important;
        height: 0px !important;
        min-height: 0px !important;
        max-height: 0px !important;
        margin: 0px !important;
        padding: 0px !important;
        position: absolute !important;
        pointer-events: none !important;
        visibility: hidden !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stVerticalBlock"] {
        overflow: visible !important;
        padding-top: 0px !important;
    }

    /* Sticky Edge-to-Edge Flush Top Navbar */
    div[data-testid="element-container"]:has(.top-navbar),
    div[data-testid="stElementContainer"]:has(.top-navbar),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.top-navbar),
    div.stMarkdown:has(.top-navbar),
    div[data-testid="stMarkdownContainer"]:has(.top-navbar) {
        position: sticky !important;
        top: 0px !important;
        z-index: 999999 !important;
        width: 100% !important;
        margin: 0px !important;
        padding: 0px !important;
        background: transparent !important;
    }

    .top-navbar {
        position: sticky !important;
        top: 0px !important;
        z-index: 999999 !important;
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 56px !important;
        min-height: 56px !important;
        max-height: 56px !important;
        width: calc(100% + 1.5rem) !important;
        margin-left: -0.75rem !important;
        margin-right: -0.75rem !important;
        margin-top: 0px !important;
        margin-bottom: 20px !important;
        padding: 0 20px !important;
        background: linear-gradient(90deg, rgba(8, 12, 21, 0.98) 0%, rgba(15, 23, 42, 0.97) 100%) !important;
        backdrop-filter: blur(24px) !important;
        -webkit-backdrop-filter: blur(24px) !important;
        border-bottom: 1px solid rgba(56, 189, 248, 0.28) !important;
        border-top: none !important;
        border-left: none !important;
        border-right: none !important;
        border-radius: 0 !important;
        box-shadow: 0 10px 36px rgba(0, 0, 0, 0.65) !important;
        box-sizing: border-box !important;
    }
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .brand-logo {
        font-size: 1.32rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(135deg, #38BDF8 0%, #00D4B2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .nav-divider {
        width: 1px;
        height: 20px;
        background: rgba(148, 163, 184, 0.25);
        margin: 0 2px;
    }
    .nav-breadcrumb {
        font-size: 0.82rem;
        font-weight: 500;
        color: #94A3B8;
        letter-spacing: 0.2px;
    }
    .nav-status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.35);
        color: #34D399;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 20px;
    }
    .pulse-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #34D399;
        box-shadow: 0 0 8px #34D399;
        animation: pulseGreen 1.8s infinite ease-in-out;
    }
    @keyframes pulseGreen {
        0% { transform: scale(0.9); opacity: 0.7; }
        50% { transform: scale(1.3); opacity: 1; box-shadow: 0 0 12px #34D399; }
        100% { transform: scale(0.9); opacity: 0.7; }
    }
    .header-actions {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .nav-meta-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(30, 41, 59, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.18);
        padding: 4px 12px;
        border-radius: 8px;
        font-size: 0.76rem;
        color: #94A3B8;
        font-family: 'JetBrains Mono', monospace;
    }
    .nav-meta-chip b {
        color: #38BDF8;
    }
    .user-pill {
        display: flex;
        align-items: center;
        gap: 10px;
        background: rgba(14, 165, 233, 0.12);
        border: 1px solid rgba(14, 165, 233, 0.35);
        padding: 3px 12px 3px 6px;
        border-radius: 24px;
    }
    .user-avatar {
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background: linear-gradient(135deg, #0284C7 0%, #0D9488 100%);
        color: #FFFFFF;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.8rem;
        font-weight: 700;
        box-shadow: 0 0 8px rgba(14, 165, 233, 0.4);
    }
    .user-name-text {
        color: #F1F5F9;
        font-weight: 600;
        font-size: 0.8rem;
        line-height: 1.1;
    }
    .user-role-badge {
        color: #00D4B2;
        font-size: 0.66rem;
        font-weight: 600;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }

    /* ========================================================= */
    /* Pixel-Perfect Balanced Sidebar Design System              */
    /* ========================================================= */
    section[data-testid="stSidebar"] {
        background-color: #070B14 !important;
        border-right: 1px solid rgba(56, 189, 248, 0.18) !important;
        z-index: 1000 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarContent"] {
        padding: 12px 14px 20px 14px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"],
    section[data-testid="stSidebar"] div[class*="stSidebarUserContent"],
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0 !important;
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
        gap: 8px !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"],
    section[data-testid="stSidebar"] div.element-container {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarNav"] {
        display: none !important;
    }

    .sidebar-brand-card {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.9) 0%, rgba(10, 15, 29, 0.98) 100%);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 8px;
        padding: 10px 12px;
        margin-top: 2px;
        margin-bottom: 10px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
        box-sizing: border-box;
        width: 100%;
    }
    .sidebar-brand-title {
        font-size: 1.15rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8 0%, #00D4B2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.4px;
        margin: 0;
        line-height: 1.2;
    }
    .sidebar-live-pill {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #34D399;
        font-size: 0.65rem;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 12px;
        letter-spacing: 0.5px;
    }
    .sidebar-brand-sub {
        font-size: 0.72rem;
        color: #94A3B8;
        font-weight: 500;
        margin-top: 4px;
        line-height: 1.2;
    }

    .sidebar-section-header {
        font-size: 0.68rem;
        font-weight: 800;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-top: 14px !important;
        margin-bottom: 6px !important;
        padding-left: 2px;
        display: block !important;
        clear: both !important;
    }
    .sidebar-user-footer {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.8) 100%);
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 8px;
        padding: 10px 12px;
        margin-top: 12px;
        display: flex;
        align-items: center;
        gap: 10px;
        box-sizing: border-box;
        width: 100%;
    }

    /* ========================================================= */
    /* Uniform Responsive Button Design System                   */
    /* Enforces 1 Standard Width & Height Across All Buttons     */
    /* ========================================================= */
    div.stButton > button,
    div.stDownloadButton > button,
    div[data-testid="stPopover"] > button {
        height: 40px !important;
        min-height: 40px !important;
        max-height: 40px !important;
        line-height: 40px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.2px !important;
        border-radius: 8px !important;
        padding: 0 16px !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-sizing: border-box !important;
    }

    /* Primary Buttons Uniformity */
    div.stButton > button[kind="primary"],
    div.stDownloadButton > button[kind="primary"],
    div.stButton > button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #0284C7 0%, #0D9488 100%) !important;
        border: 1px solid rgba(56, 189, 248, 0.45) !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3) !important;
    }
    div.stButton > button[kind="primary"]:hover,
    div.stDownloadButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0369A1 0%, #0F766E 100%) !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 6px 20px rgba(56, 189, 248, 0.45) !important;
        transform: translateY(-1px) !important;
    }

    /* Secondary Buttons Uniformity */
    div.stButton > button[kind="secondary"],
    div.stDownloadButton > button[kind="secondary"],
    div.stButton > button[data-testid="baseButton-secondary"] {
        background: rgba(30, 41, 59, 0.65) !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        color: #CBD5E1 !important;
    }
    div.stButton > button[kind="secondary"]:hover,
    div.stDownloadButton > button[kind="secondary"]:hover {
        background: rgba(51, 65, 85, 0.85) !important;
        border-color: rgba(56, 189, 248, 0.4) !important;
        color: #F8FAFC !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
        transform: translateY(-1px) !important;
    }

    /* Popover Button Uniformity */
    div[data-testid="stPopover"] {
        width: 100% !important;
    }
    div[data-testid="stPopover"] > button {
        width: 100% !important;
        background: rgba(30, 41, 59, 0.65) !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        color: #CBD5E1 !important;
    }
    div[data-testid="stPopover"] > button:hover {
        background: rgba(51, 65, 85, 0.85) !important;
        border-color: rgba(56, 189, 248, 0.4) !important;
        color: #F8FAFC !important;
    }

    /* Sidebar Navigation Buttons - Flush, High-Tech, Zero-Waste */
    section[data-testid="stSidebar"] div.stButton {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] div.stButton > button {
        width: 100% !important;
        height: 40px !important;
        min-height: 40px !important;
        max-height: 40px !important;
        line-height: 40px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        padding: 0 14px !important;
        font-size: 0.86rem !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
        text-align: left !important;
    }
    section[data-testid="stSidebar"] div.stButton > button * {
        text-align: left !important;
        justify-content: flex-start !important;
    }

    /* Active Sidebar Navigation Item Styling */
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(2, 132, 199, 0.35) 0%, rgba(13, 148, 136, 0.25) 100%) !important;
        border: 1px solid #38BDF8 !important;
        border-left: 3.5px solid #38BDF8 !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 14px rgba(56, 189, 248, 0.25) !important;
    }

    /* Inactive Sidebar Navigation Item Styling */
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(148, 163, 184, 0.16) !important;
        color: #94A3B8 !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {
        background: rgba(30, 41, 59, 0.85) !important;
        border-color: rgba(56, 189, 248, 0.5) !important;
        color: #F8FAFC !important;
        transform: translateX(2px) !important;
    }

    /* Compact Selectbox inside Sidebar */
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-baseweb="select"] {
        width: 100% !important;
    }
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: rgba(15, 23, 42, 0.85) !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        border-radius: 8px !important;
        height: 38px !important;
        min-height: 38px !important;
        font-size: 0.82rem !important;
        box-sizing: border-box !important;
    }
    section[data-testid="stSidebar"] hr {
        margin: 10px 0 !important;
        border: none !important;
        border-top: 1px solid rgba(148, 163, 184, 0.16) !important;
    }

    /* State Pills Filter Container - Equal Width & Responsive Scroll */
    div[data-testid="stHorizontalBlock"]:has(button[key*="btn_st_"]) {
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 8px !important;
        padding-bottom: 4px !important;
    }
    div[data-testid="stHorizontalBlock"]:has(button[key*="btn_st_"]) > div[data-testid="column"] {
        flex: 1 1 0px !important;
        min-width: 105px !important;
    }
    div[data-testid="stHorizontalBlock"]:has(button[key*="btn_st_"]) div.stButton > button {
        width: 100% !important;
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        line-height: 38px !important;
        font-size: 0.78rem !important;
        padding: 0 8px !important;
    }

    /* ========================================================= */
    /* UI Responsiveness & Adaptive Breakpoints                  */
    /* ========================================================= */
    /* Greeting Section */
    .greeting-title {
        font-size: clamp(1.4rem, 2.5vw, 2.15rem);
        font-weight: 800;
        color: #F8FAFC;
        margin-bottom: 4px;
        letter-spacing: -0.6px;
    }
    .greeting-sub {
        font-size: clamp(0.9rem, 1.2vw, 1.12rem);
        color: #94A3B8;
        margin-bottom: 20px;
    }

    /* Suggested Pills */
    .suggested-label {
        font-size: 0.88rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }

    /* KPI Metric Cards Responsive Grid */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-top: 20px;
        margin-bottom: 24px;
    }
    @media (max-width: 1200px) {
        .kpi-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
    }
    @media (max-width: 600px) {
        .kpi-grid {
            grid-template-columns: 1fr;
            gap: 10px;
        }
    }

    /* Responsive Multi-Column Layouts */
    @media (max-width: 960px) {
        div[data-testid="stHorizontalBlock"]:not(:has(button[key*="btn_st_"])) {
            flex-direction: column !important;
            gap: 16px !important;
        }
        div[data-testid="stHorizontalBlock"]:not(:has(button[key*="btn_st_"])) > div[data-testid="column"] {
            width: 100% !important;
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        .top-navbar {
            padding: 8px 14px !important;
        }
        .nav-breadcrumb {
            display: none !important;
        }
        .nav-divider {
            display: none !important;
        }
    }

    .kpi-card {
        background: linear-gradient(145deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 12px;
        padding: 20px 22px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .kpi-card:hover {
        border-color: rgba(56, 189, 248, 0.4);
        transform: translateY(-2px);
    }
    .kpi-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .kpi-title {
        color: #94A3B8;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-pill-green {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-blue {
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-purple {
        background: rgba(168, 85, 247, 0.15);
        color: #C084FC;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .kpi-pill-rose {
        background: rgba(244, 63, 94, 0.15);
        color: #FB7185;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .section-header-banner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 10px;
        margin-bottom: 14px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.15);
    }
    .section-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #F8FAFC;
        letter-spacing: -0.3px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-badge {
        font-size: 0.76rem;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 20px;
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .dts-metric-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .insight-callout-box {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-left: 4px solid #38BDF8;
        border-radius: 10px;
        padding: 14px 18px;
        margin-top: 14px;
        color: #E2E8F0;
        font-size: 0.88rem;
        line-height: 1.5;
    }
    .kpi-value {
        color: #F8FAFC;
        font-size: 1.85rem;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .kpi-desc {
        color: #64748B;
        font-size: 0.82rem;
    }

    /* Attached Doc Badge & ChatGPT File Chip */
    .attached-file-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(14, 165, 233, 0.14);
        border: 1px solid rgba(14, 165, 233, 0.35);
        color: #38BDF8;
        padding: 5px 12px;
        border-radius: 8px;
        font-size: 0.84rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .chatgpt-file-chip {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        background: rgba(15, 23, 42, 0.95);
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 8px;
        padding: 8px 16px;
        margin-bottom: 8px;
        font-size: 0.86rem;
        color: #E2E8F0;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    }
    .chatgpt-file-icon {
        color: #38BDF8;
        font-size: 1.15rem;
    }
    .chatgpt-file-name {
        font-weight: 600;
        color: #F8FAFC;
    }
    .chatgpt-file-meta {
        color: #94A3B8;
        font-size: 0.76rem;
    }

    /* Thinking Component */
    div[data-testid="stExpander"] {
        border: 1px solid #2D3748 !important;
        border-radius: 8px !important;
        background-color: rgba(15, 23, 42, 0.5) !important;
        margin-bottom: 12px !important;
    }
    div[data-testid="stExpander"] summary {
        color: #94A3B8 !important;
        font-size: 0.90rem !important;
        font-weight: 500 !important;
    }
    div[data-testid="stExpander"] summary:hover {
        color: #38BDF8 !important;
    }
    .thinking-live-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: #94A3B8;
        font-size: 0.92rem;
        background: rgba(30, 41, 59, 0.5);
        padding: 6px 14px;
        border-radius: 6px;
        border-left: 3px solid #29B5E8;
        margin-bottom: 12px;
        animation: pulseFade 1.6s infinite ease-in-out;
    }
    @keyframes pulseFade {
        0% { opacity: 0.5; }
        50% { opacity: 1; }
        100% { opacity: 0.5; }
    }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Helper Functions & API Clients (Persistent In-Process & Fallback)
# ---------------------------------------------------------


@st.cache_data(ttl=30)
def fetch_overview_metrics(state: Optional[str] = None):
    try:
        # In-process query execution reusing active Snowflake session
        return backend_service.get_dashboard_overview(mgr=cached_sf_mgr, state=state)
    except Exception:
        return backend_service.get_dashboard_overview(mgr=None, state=state)


@st.cache_data(ttl=30)
def fetch_dts_analytics():
    try:
        return backend_service.get_dts_analytics_data(mgr=cached_sf_mgr)
    except Exception:
        return backend_service.get_dts_analytics_data(mgr=None)


@st.cache_data(ttl=30)
def fetch_risk_churn_analytics(state: Optional[str] = None):
    try:
        return backend_service.get_risk_and_churn_analytics(mgr=cached_sf_mgr, state=state)
    except Exception:
        return backend_service.get_risk_and_churn_analytics(mgr=None, state=state)


@st.cache_data(ttl=30)
def fetch_geospatial_analytics():
    try:
        return backend_service.get_state_geospatial_analytics(mgr=cached_sf_mgr)
    except Exception:
        return backend_service.get_state_geospatial_analytics(mgr=None)


@st.cache_data(ttl=30)
def fetch_trend_analytics(state: Optional[str] = None):
    try:
        return backend_service.get_trend_analytics(mgr=cached_sf_mgr, state=state)
    except Exception:
        return backend_service.get_trend_analytics(mgr=None, state=state)


# ---------------------------------------------------------
# Explore view fetchers
# ---------------------------------------------------------
# st.tabs is not lazy: every tab's body runs on every rerun. These are cached so that
# interacting with one tab does not re-query Snowflake for all the others. Writes
# (rating, match generation, recommendation regeneration) are deliberately uncached and
# clear the relevant cache afterwards.


@st.cache_data(ttl=60)
def fetch_strategic_recommendations():
    return backend_service.get_strategic_recommendations(mgr=cached_sf_mgr)


@st.cache_data(ttl=60)
def fetch_market_pricing():
    return backend_service.get_market_pricing(mgr=cached_sf_mgr)


@st.cache_data(ttl=30)
def fetch_plan_ratings_summary():
    return backend_service.get_plan_ratings_summary(mgr=cached_sf_mgr)


@st.cache_data(ttl=30)
def fetch_customer_directory(search: Optional[str] = None, state: Optional[str] = None,
                            plan: Optional[str] = None, status: Optional[str] = None,
                            limit: int = 200):
    return backend_service.get_customer_directory(
        mgr=cached_sf_mgr, search=search, state=state,
        plan=plan, status=status, limit=limit
    )


# Filter options change only when the policy mix does, so this is cached far longer
# than the directory rows themselves.
@st.cache_data(ttl=600)
def fetch_plan_filter_options():
    return backend_service.get_customer_plan_filter_options(mgr=cached_sf_mgr)


@st.cache_data(ttl=30)
def fetch_customer_matches(customer_id: str):
    return backend_service.get_customer_matches(customer_id=customer_id, mgr=cached_sf_mgr)


@st.cache_data(ttl=30)
def fetch_customer_360(customer_id: str):
    return backend_service.get_customer_360(customer_id=customer_id, mgr=cached_sf_mgr)


def clear_rating_caches():
    """Drop the caches a rating or match write invalidates."""
    fetch_plan_ratings_summary.clear()
    fetch_customer_directory.clear()
    fetch_customer_matches.clear()
    fetch_customer_360.clear()
    fetch_plan_filter_options.clear()






def get_time_greeting():
    current_hour = datetime.datetime.now().hour
    if 5 <= current_hour < 12:
        return "Good Morning"
    elif 12 <= current_hour < 17:
        return "Good Afternoon"
    else:
        return "Good Evening"


# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------
if "current_nav" not in st.session_state or st.session_state.current_nav in ["◈ Home", "◉ Ask AI"]:
    st.session_state.current_nav = "◈ Insurance Portfolio"

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

if "selected_state" not in st.session_state:
    st.session_state.selected_state = "National"

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

# Fetch Snowflake session context
sf_context = fetch_snowflake_status(_mgr=cached_sf_mgr, _env_config=env_config)
current_user = sf_context.get("user") or env_config.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
current_role = sf_context.get("role") or "ACCOUNTADMIN"
current_wh = sf_context.get("warehouse") or "COMPUTE_WH"
current_db = sf_context.get("database") or "UNIFIEDAI_DB"
current_sh = sf_context.get("schema") or "UNIFIEDAI_SH"
current_agent = env_config.get("INS_AGENT") or sf_context.get("default_agent") or "UNIFIED_ENTERPRISE_AGENT"

# Active state cross-filter
active_state = st.session_state.selected_state if st.session_state.selected_state != "National" else None

overview_data = fetch_overview_metrics(state=active_state)
dts_data = fetch_dts_analytics()
risk_churn_data = fetch_risk_churn_analytics(state=active_state)
geo_data = fetch_geospatial_analytics()
trend_data = fetch_trend_analytics(state=active_state)


# ---------------------------------------------------------
# Top Navbar Header (Clean & Minimalist: Brand + Dynamic User)
# ---------------------------------------------------------
user_initial = current_user[0].upper() if current_user else "U"

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
# Upgraded Enterprise Sidebar Design System (Zero-Padding Flush)
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

    # 2. Primary Navigation Groups
    st.markdown('<div class="sidebar-section-header">WORKSPACE NAVIGATION</div>', unsafe_allow_html=True)
    
    nav_analytics = ["◈ Insurance Portfolio", "◉ Enterprise AI", "📜 Chat History", "⚡ Explore", "📊 Data"]
    for nav_item in nav_analytics:
        is_active = (st.session_state.current_nav == nav_item)
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"btn_nav_{nav_item}", use_container_width=True, type=btn_type):
            if "Enterprise AI" in nav_item:
                st.session_state.current_nav = "◉ Enterprise AI"
                try:
                    st.switch_page("pages/1_Enterprise_AI.py")
                except Exception:
                    st.rerun()
            elif "Chat History" in nav_item:
                try:
                    st.switch_page("pages/2_Chat_History.py")
                except Exception:
                    st.rerun()
            else:
                st.session_state.current_nav = nav_item
                st.rerun()

    st.divider()

    # Default Cortex AI Engine configuration (silent background execution)
    selected_model = "claude-3-5-sonnet"
    enable_reasoning = True
    auto_run_sql = True

    # 3. Global Timeframe Filter
    # Options reflect the actual span of CORE data (policies 2024-09 to 2026-08, claims
    # 2025-09 to 2026-09) against a current date of 2026. The previous default of
    # "FY2024 YTD" named a year the data has largely moved past.
    st.markdown('<div class="sidebar-section-header">TIMEFRAME SCOPE</div>', unsafe_allow_html=True)
    time_filter = st.selectbox(
        "Timeframe Filter",
        ["All Time Historical", "FY2026 YTD", "FY2026 Q3", "Last 90 Days",
         "Last 30 Days", "FY2025 Full Year"],
        index=0,
        label_visibility="collapsed",
        help=(
            "Reference label only — dashboard queries are not yet scoped by date, so "
            "every view currently reads the full history."
        ),
    )
    st.caption(
        f"<span style='font-size:0.68rem; color:#64748B;'>Label only · "
        f"{html.escape(time_filter)}</span>",
        unsafe_allow_html=True,
    )

    # Quick Actions & User Footer
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.session_state.uploaded_doc_name = None
        st.session_state.uploaded_doc_summary = None
        st.session_state.uploaded_doc_text = None
        st.session_state.uploaded_doc_snowflake = None
        st.session_state.doc_uploader_seq += 1
        queue_toast("Chat cleared", "deleted")
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
# Helper: Render Assistant Chat Response
# ---------------------------------------------------------






# ---------------------------------------------------------
# VIEW 1: ◈ INSURANCE PORTFOLIO DASHBOARD
# ---------------------------------------------------------
if st.session_state.current_nav in ["◈ Insurance Portfolio", "Insurance Portfolio", "◈ Home"]:
    st.markdown(f'<div class="greeting-title">Insurance Portfolio Intelligence Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="greeting-sub" style="margin-bottom: 20px;">Real-time portfolio performance, risk exposure, and operational intelligence.</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------
    # GEOSPATIAL 3D US MAP & CROSS-FILTER SECTION
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner" style="margin-top: 24px;">
            <div class="section-title">🗺️ US Risk & Premium Map</div>
        </div>
    """, unsafe_allow_html=True)

    # State Selection Filter Pills Bar (Uniform 1:1 Width & Height Across All Options)
    state_cols = st.columns(8)
    
    with state_cols[0]:
        is_nat = (st.session_state.selected_state == "National")
        if st.button("🌐 All States", key="btn_st_all", use_container_width=True, type="primary" if is_nat else "secondary"):
            st.session_state.selected_state = "National"
            st.rerun()

    states_list = [
        {"code": "TX", "label": "TX"},
        {"code": "AZ", "label": "AZ"},
        {"code": "IL", "label": "IL"},
        {"code": "CA", "label": "CA"},
        {"code": "PA", "label": "PA"},
        {"code": "NY", "label": "NY"},
        {"code": "GA", "label": "GA"}
    ]

    for idx, st_item in enumerate(states_list):
        with state_cols[idx + 1]:
            is_active = (st.session_state.selected_state == st_item["code"])
            if st.button(st_item["label"], key=f"btn_st_{st_item['code']}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state.selected_state = st_item["code"]
                st.rerun()

    # Active State Filter Callout Indicator
    if st.session_state.selected_state != "National":
        st.markdown(f"""
            <div class="insight-callout-box" style="margin-top: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 700; color: #38BDF8;">📍 Active State Filter: {st.session_state.selected_state}</span>
                    <span style="color: #94A3B8; margin-left: 8px; font-size: 0.86rem;">Dashboard metrics, DTS trajectories, and risk exposure are filtered for this state.</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # KPI Overview Metrics. No .get() fallbacks here: the backend now returns real values
    # or None, and a default like "+8.4% MoM" or "4.8 / 5.0" would silently reinstate a
    # fabricated figure whenever the query returned nothing.
    active_policies_val = overview_data.get("active_policies") or 0
    active_policies_trend = overview_data.get("active_policies_trend")

    proc_days_val = overview_data.get("processing_days") or overview_data.get("avg_settlement_days") or 0.0
    proc_days_trend = overview_data.get("processing_days_trend")

    csat_score_val = overview_data.get("csat_score")
    csat_pct_val = overview_data.get("csat_pct")
    csat_trend = overview_data.get("csat_trend")

    prem_rev = overview_data.get("revenue") or 0.0
    prem_rev_trend = overview_data.get("revenue_growth_pct")

    def kpi_pill(text, invert=False):
        """Render a trend pill, or nothing at all when there is no trend to show.

        Colour follows the sign of the delta instead of being fixed per-card, so a
        decline no longer renders green. invert=True is for metrics where down is good
        (processing days).
        """
        if not text:
            return ""
        label = str(text)
        stripped = label.lstrip("• ").split("•")[-1].strip()
        if stripped.startswith("-"):
            good = invert
        elif stripped.startswith("+"):
            good = not invert
        else:
            good = None
        cls = "kpi-pill-green" if good else ("kpi-pill-rose" if good is False else "kpi-pill-blue")
        return f'<span class="{cls}">{html.escape(label)}</span>'


    # 3D Pydeck Map & Executive KPI Split
    c_map, c_map_stats = st.columns([1.65, 1.35])

    with c_map:
        if geo_data:
            df_geo = pd.DataFrame(geo_data)
            df_geo["lat"] = pd.to_numeric(df_geo["lat"])
            df_geo["lon"] = pd.to_numeric(df_geo["lon"])
            df_geo["elevation"] = pd.to_numeric(df_geo["elevation"])
            
            # Helper styling columns
            def get_hex(status):
                if "Critical" in str(status):
                    return "#EF4444"
                elif "Elevated" in str(status):
                    return "#F59E0B"
                return "#10B981"

            df_geo["status_color_hex"] = df_geo["risk_label"].apply(get_hex)
            df_geo["state_badge"] = df_geo["state"] + "\n" + df_geo["total_premium_formatted"]
            df_geo["halo_radius"] = df_geo["claims_count"].apply(lambda c: max(65000, c * 2200))
            df_geo["pillar_radius"] = 42000
            df_geo["core_radius"] = 18000

            # Default Isometric 3D Elevation scaled by written premium
            df_geo["layer_elevation"] = df_geo["elevation"]

            # Center on selected state or national overview (Isometric 3D Camera)
            if st.session_state.selected_state != "National":
                matching_st = df_geo[df_geo["state"] == st.session_state.selected_state]
                if not matching_st.empty:
                    view_lat = float(matching_st["lat"].values[0])
                    view_lon = float(matching_st["lon"].values[0])
                    view_zoom = 5.0
                else:
                    view_lat, view_lon, view_zoom = 38.0, -96.0, 3.55
            else:
                view_lat, view_lon, view_zoom = 38.0, -96.0, 3.55

            # Locked Default Isometric 3D Perspective
            view_pitch = 48
            view_bearing = 10

            # 1. Base Radial Ambient Glow Layer
            halo_layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_radius="halo_radius",
                radius_min_pixels=14,
                radius_max_pixels=65,
                get_fill_color="fill_color",
                get_line_color="fill_color",
                line_width_min_pixels=2,
                stroked=True,
                filled=True,
                opacity=0.35,
                pickable=False
            )

            # 2. 3D Prismatic Illuminated Columns
            column_layer = pdk.Layer(
                "ColumnLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_elevation="layer_elevation",
                elevation_scale=1,
                radius=42000,
                get_fill_color="fill_color",
                pickable=True,
                auto_highlight=True,
                material={
                    "ambient": 0.45,
                    "diffuse": 0.7,
                    "shininess": 42,
                    "specularColor": [56, 189, 248, 255]
                }
            )

            # 3. Central Pulsing Core Beacon
            beacon_layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_radius="core_radius",
                radius_min_pixels=6,
                radius_max_pixels=22,
                get_fill_color=[255, 255, 255, 230],
                get_line_color=[56, 189, 248, 255],
                line_width_min_pixels=2.5,
                stroked=True,
                filled=True,
                pickable=True
            )

            # 4. Crisp State Label TextLayer
            text_layer = pdk.Layer(
                "TextLayer",
                data=df_geo,
                get_position=["lon", "lat"],
                get_text="state_badge",
                get_size=12,
                get_color=[248, 250, 252, 240],
                get_alignment_baseline="'bottom'",
                get_text_anchor="'middle'",
                get_pixel_offset=[0, -16],
                billboard=True,
                font_family="'Inter', sans-serif",
                font_weight=700
            )

            # Active Layers: Default Isometric 3D Suite (Halos, 3D Columns, Core Beacons, State Badges)
            active_layers = [halo_layer, column_layer, beacon_layer, text_layer]

            tooltip_html = {
                "html": """
                <div style="background: rgba(10, 15, 29, 0.95); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); padding: 14px 18px; border-radius: 12px; border: 1px solid rgba(56, 189, 248, 0.4); box-shadow: 0 16px 36px rgba(0, 0, 0, 0.75); font-family: Inter, -apple-system, sans-serif; color: #F8FAFC; min-width: 230px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid rgba(148, 163, 184, 0.2); padding-bottom: 8px;">
                        <span style="font-size: 15px; font-weight: 800; color: #38BDF8; letter-spacing: -0.3px;">📍 {state_name}</span>
                        <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px;">{state}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; margin-bottom: 10px;">
                        <div>
                            <div style="color: #94A3B8; font-size: 10px; text-transform: uppercase;">Written Premium</div>
                            <div style="font-weight: 700; color: #F1F5F9; font-size: 13px;">{total_premium_formatted}</div>
                        </div>
                        <div>
                            <div style="color: #94A3B8; font-size: 10px; text-transform: uppercase;">Loss Ratio</div>
                            <div style="font-weight: 700; color: #F59E0B; font-size: 13px;">{avg_loss_ratio}%</div>
                        </div>
                        <div>
                            <div style="color: #94A3B8; font-size: 10px; text-transform: uppercase;">Active Policies</div>
                            <div style="font-weight: 600; color: #E2E8F0;">{policies_count}</div>
                        </div>
                        <div>
                            <div style="color: #94A3B8; font-size: 10px; text-transform: uppercase;">Claims Count</div>
                            <div style="font-weight: 600; color: #E2E8F0;">{claims_count}</div>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.8); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(148, 163, 184, 0.15); font-size: 11px;">
                        <span style="color: #94A3B8;">Territory Risk:</span>
                        <span style="font-weight: 700; color: {status_color_hex};">● {risk_label}</span>
                    </div>
                </div>
                """,
                "style": {"color": "white"}
            }

            deck = pdk.Deck(
                layers=active_layers,
                initial_view_state=pdk.ViewState(
                    latitude=view_lat,
                    longitude=view_lon,
                    zoom=view_zoom,
                    pitch=view_pitch,
                    bearing=view_bearing
                ),
                tooltip=tooltip_html,
                map_style=getattr(pdk.map_styles, 'CARTO_DARK', 'dark')
            )

            st.pydeck_chart(deck, use_container_width=True, height=370)
        else:
            st.info("Loading geospatial data from Snowflake...")

    with c_map_stats:
        st.markdown("#### 📊 Executive Portfolio KPIs & Risk")
        
        # 4 KPI Cards in a 2x2 Responsive Grid
        csat_display = csat_score_val or "Not available"
        csat_desc = f"{csat_pct_val} positive sentiment" if csat_pct_val else "No CSAT data in ANALYTICS.CLAIMS_KPI"
        st.markdown(f"""
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 8px;">
                <div class="kpi-card" style="padding: 12px 14px;">
                    <div class="kpi-header">
                        <span class="kpi-title" style="font-size: 0.76rem;">Active Policies</span>
                        {kpi_pill(active_policies_trend)}
                    </div>
                    <div class="kpi-value" style="font-size: 1.45rem; margin-bottom: 2px;">{active_policies_val:,}</div>
                    <div class="kpi-desc" style="font-size: 0.74rem;">Active policyholders across 4 tiers</div>
                </div>
                <div class="kpi-card" style="padding: 12px 14px;">
                    <div class="kpi-header">
                        <span class="kpi-title" style="font-size: 0.76rem;">Processing Days</span>
                        {kpi_pill(proc_days_trend, invert=True)}
                    </div>
                    <div class="kpi-value" style="font-size: 1.45rem; margin-bottom: 2px;">{proc_days_val} Days</div>
                    <div class="kpi-desc" style="font-size: 0.74rem;">Average claims turnaround</div>
                </div>
                <div class="kpi-card" style="padding: 12px 14px;">
                    <div class="kpi-header">
                        <span class="kpi-title" style="font-size: 0.76rem;">Customer CSAT</span>
                        {kpi_pill(csat_trend)}
                    </div>
                    <div class="kpi-value" style="font-size: 1.45rem; margin-bottom: 2px;">{csat_display}</div>
                    <div class="kpi-desc" style="font-size: 0.74rem;">{csat_desc}</div>
                </div>
                <div class="kpi-card" style="padding: 12px 14px;">
                    <div class="kpi-header">
                        <span class="kpi-title" style="font-size: 0.76rem;">Total Revenue</span>
                        {kpi_pill(prem_rev_trend)}
                    </div>
                    <div class="kpi-value" style="font-size: 1.45rem; margin-bottom: 2px;">${prem_rev/1_000_000:.2f}M</div>
                    <div class="kpi-desc" style="font-size: 0.74rem;">Gross written annual premium</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        if geo_data:
            # Top territory summary badges (derived live from Snowflake geo_data)
            def _fmt_premium(val):
                val = float(val or 0.0)
                if val >= 1_000_000:
                    return f"${val / 1_000_000:.2f}M"
                if val >= 1_000:
                    return f"${val / 1_000:.0f}k"
                return f"${val:,.0f}"

            top_prem = max(geo_data, key=lambda g: float(g.get("total_premium") or 0.0))
            top_risk = max(geo_data, key=lambda g: float(g.get("avg_loss_ratio") or 0.0))

            top_prem_lr = float(top_prem.get("avg_loss_ratio") or 0.0)
            top_prem_label = top_prem.get("risk_label", "Optimal")
            top_prem_lr_color = "#34D399" if "Optimal" in top_prem_label else ("#FBBF24" if "Elevated" in top_prem_label else "#FB7185")

            st.markdown(f"""
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 0px;">
                    <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 9px 12px;">
                        <div style="color: #94A3B8; font-size: 0.68rem; text-transform: uppercase;">Top Written Premium</div>
                        <div style="color: #38BDF8; font-weight: 800; font-size: 0.92rem;">{top_prem.get("state", "—")} • {_fmt_premium(top_prem.get("total_premium"))}</div>
                        <div style="color: {top_prem_lr_color}; font-size: 0.70rem;">{top_prem_lr:.1f}% Loss Ratio ({top_prem_label})</div>
                    </div>
                    <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 9px 12px;">
                        <div style="color: #94A3B8; font-size: 0.68rem; text-transform: uppercase;">Highest Risk Territory</div>
                        <div style="color: #FB7185; font-weight: 800; font-size: 0.92rem;">{top_risk.get("state", "—")} • {float(top_risk.get("avg_loss_ratio") or 0.0):.1f}%</div>
                        <div style="color: #94A3B8; font-size: 0.70rem;">{_fmt_premium(top_risk.get("total_premium"))} Written Premium</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # Sleek Glassmorphic Map Legend Bar - Extended Full Width to the Right (No Gaps!)
    # The right-hand slot reports measured CORE data completeness. It replaces a
    # "Data Trust Score: 88 / Enterprise Verified (Tier 1)" badge that was a literal in
    # the backend - all three DQ_* tables are empty, so nothing was ever computed.
    dq_completeness = dts_data.get("completeness_pct")
    dq_validity = dts_data.get("validity_pct")
    if dq_completeness is None:
        dq_chip = '<span style="color: #94A3B8;">Data completeness unavailable</span>'
    else:
        dq_color = "#34D399" if dq_completeness >= 99 else ("#FBBF24" if dq_completeness >= 95 else "#FB7185")
        detail = dts_data.get("completeness_detail", {})
        dq_chip = (
            f'<span>📋 <b style="color: {dq_color};">{dq_completeness:.1f}% Field Completeness</b>'
            f'<span style="color: #64748B;"> ({detail.get("fields_checked", 0)} checks'
            + (f", {dq_validity:.1f}% valid" if dq_validity is not None else "")
            + ')</span></span>'
        )

    st.markdown(f"""
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 8px; padding: 8px 18px; margin-top: 6px; margin-bottom: 4px; font-size: 0.78rem; color: #94A3B8; width: 100%;">
            <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
                <span>🟢 <b style="color: #34D399;">Optimal Loss Ratio (&lt; 52%)</b></span>
                <span>🟠 <b style="color: #FBBF24;">Elevated Risk (52% - 62%)</b></span>
                <span>🔴 <b style="color: #FB7185;">Critical Risk (&gt; 62%)</b></span>
                <span>🗼 <b style="color: #E2E8F0;">Pillar Height: Written Premium</b></span>
            </div>
            <div style="display: flex; gap: 14px; align-items: center;">{dq_chip}</div>
        </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # ROW 2: CHARTS — TREND ANALYSIS (CALCULATED FROM CORE.CLAIMS & RISK.AT_RISK_POLICIES)
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner">
            <div class="section-title">📈 Trend Analysis (Claims, Resolution, Fraud & At-Risk Revenue)</div>
        </div>
    """, unsafe_allow_html=True)

    monthly_trends_list = trend_data.get("monthly_trends", [])
    trend_summary = trend_data.get("summary", {})

    total_risk_rev = trend_summary.get("total_revenue_at_risk", 0.0)
    total_risk_policies = trend_summary.get("total_new_at_risk_policies", 0)
    avg_res_days = trend_summary.get("avg_claim_resolution_time_days", 0.0)
    total_fraud_claims = trend_summary.get("total_fraud_flagged_claims", 0)
    total_claim_count = trend_summary.get("total_claim_count", 0)

    # 5 KPI Summary Cards matching user requirements
    st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 18px;">
            <div class="kpi-card" style="padding: 14px 16px;">
                <div class="kpi-header">
                    <span class="kpi-title" style="font-size: 0.74rem;">Revenue at Risk</span>
                    <span class="kpi-pill-rose">Exposure</span>
                </div>
                <div class="kpi-value" style="font-size: 1.5rem; margin-bottom: 2px;">${total_risk_rev:,.0f}</div>
                <div class="kpi-desc" style="font-size: 0.74rem;">Revenue at risk by month</div>
            </div>
            <div class="kpi-card" style="padding: 14px 16px;">
                <div class="kpi-header">
                    <span class="kpi-title" style="font-size: 0.74rem;">New At-Risk Policies</span>
                    <span class="kpi-pill-amber">Policies</span>
                </div>
                <div class="kpi-value" style="font-size: 1.5rem; margin-bottom: 2px;">{total_risk_policies:,}</div>
                <div class="kpi-desc" style="font-size: 0.74rem;">New at-risk policies by month</div>
            </div>
            <div class="kpi-card" style="padding: 14px 16px;">
                <div class="kpi-header">
                    <span class="kpi-title" style="font-size: 0.74rem;">Avg Resolution Time</span>
                    <span class="kpi-pill-blue">Turnaround</span>
                </div>
                <div class="kpi-value" style="font-size: 1.5rem; margin-bottom: 2px;">{avg_res_days:.1f}d</div>
                <div class="kpi-desc" style="font-size: 0.74rem;">Average claim resolution time (days)</div>
            </div>
            <div class="kpi-card" style="padding: 14px 16px;">
                <div class="kpi-header">
                    <span class="kpi-title" style="font-size: 0.74rem;">Fraud-Flagged Claims</span>
                    <span class="kpi-pill-purple">Anomalies</span>
                </div>
                <div class="kpi-value" style="font-size: 1.5rem; margin-bottom: 2px;">{total_fraud_claims:,}</div>
                <div class="kpi-desc" style="font-size: 0.74rem;">Fraud-flagged claims by month</div>
            </div>
            <div class="kpi-card" style="padding: 14px 16px;">
                <div class="kpi-header">
                    <span class="kpi-title" style="font-size: 0.74rem;">Claim Count</span>
                    <span class="kpi-pill-green">Volume</span>
                </div>
                <div class="kpi-value" style="font-size: 1.5rem; margin-bottom: 2px;">{total_claim_count:,}</div>
                <div class="kpi-desc" style="font-size: 0.74rem;">Claim count by month</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    df_trends = pd.DataFrame(monthly_trends_list)

    c_claim_col, c_risk_col = st.columns([1, 1])

    # ------------------ LEFT: CLAIMS & RESOLUTION TRENDS ------------------
    with c_claim_col:
        st.markdown("### 🚨 Claims Velocity & Resolution Trends")

        claim_chart_metric = st.radio(
            "Select Claims Metric to Visualize:",
            [
                "📊 Claim count by month",
                "⏱ Average claim resolution time (days) by month",
                "🚨 Fraud-flagged claims by month",
                "⚖️ Claim count vs Fraud-flagged claims"
            ],
            horizontal=True,
            key="claims_trend_selector"
        )

        if not df_trends.empty:
            if claim_chart_metric == "📊 Claim count by month":
                chart_cc = df_trends.set_index("Month")[["Claim count by month"]]
                st.bar_chart(chart_cc, use_container_width=True)
            elif claim_chart_metric == "⏱ Average claim resolution time (days) by month":
                chart_rt = df_trends.set_index("Month")[["Average claim resolution time (days) by month"]]
                st.line_chart(chart_rt, use_container_width=True)
            elif claim_chart_metric == "🚨 Fraud-flagged claims by month":
                chart_ff = df_trends.set_index("Month")[["Fraud-flagged claims by month"]]
                st.bar_chart(chart_ff, use_container_width=True)
            else:
                chart_comp = df_trends.set_index("Month")[["Claim count by month", "Fraud-flagged claims by month"]]
                st.bar_chart(chart_comp, use_container_width=True)
        else:
            st.info("Claims trend data loading...")

    # ------------------ RIGHT: AT-RISK POLICIES & REVENUE TRENDS ------------------
    with c_risk_col:
        st.markdown("### 💰 At-Risk Policies & Revenue Exposure Trends")

        risk_chart_metric = st.radio(
            "Select Risk Exposure Metric to Visualize:",
            [
                "💵 Revenue at risk by month",
                "🛡️ New at-risk policies by month",
                "📊 Dual View: Revenue & Policies"
            ],
            horizontal=True,
            key="risk_trend_selector"
        )

        if not df_trends.empty:
            if risk_chart_metric == "💵 Revenue at risk by month":
                chart_rr = df_trends.set_index("Month")[["Revenue at risk by month"]]
                st.area_chart(chart_rr, use_container_width=True)
            elif risk_chart_metric == "🛡️ New at-risk policies by month":
                chart_np = df_trends.set_index("Month")[["New at-risk policies by month"]]
                st.bar_chart(chart_np, use_container_width=True)
            else:
                sub_c1, sub_c2 = st.columns(2)
                with sub_c1:
                    st.caption("Revenue at risk by month ($)")
                    st.area_chart(df_trends.set_index("Month")[["Revenue at risk by month"]], use_container_width=True)
                with sub_c2:
                    st.caption("New at-risk policies by month")
                    st.bar_chart(df_trends.set_index("Month")[["New at-risk policies by month"]], use_container_width=True)
        else:
            st.info("At-risk policy trends data loading...")


    # ---------------------------------------------------------
    # ROW 3: RISK ANALYSIS & CHURN BY CATEGORY
    # ---------------------------------------------------------
    st.markdown("""
        <div class="section-header-banner">
            <div class="section-title">🛡 Risk Analysis & Categorical Churn Intelligence</div>
        </div>
    """, unsafe_allow_html=True)

    c_risk, c_churn = st.columns([1, 1])

    with c_risk:
        st.markdown("### 🚨 Multi-Dimensional Risk Exposure")
        st.caption("Category claim exposure, severity, and fraud indicators.")

        st.markdown("##### 📊 Category Risk Exposure")
        risk_cats = risk_churn_data.get("risk_by_category", [])
        if risk_cats:
            df_risk = pd.DataFrame(risk_cats)

            # Derived hover-only fields
            total_exposure = float(df_risk["Risk Exposure ($)"].sum()) or 1.0
            df_risk["Share of Exposure"] = (df_risk["Risk Exposure ($)"] / total_exposure * 100.0).round(1)
            df_risk["High Risk Rate"] = (
                df_risk["High Risk Claims"] / df_risk["Total Claims"].replace(0, pd.NA) * 100.0
            ).fillna(0.0).round(1)

            pie_spec = {
                "mark": {
                    "type": "arc",
                    "innerRadius": 62,
                    "outerRadius": 108,
                    "stroke": "#0A0F1D",
                    "strokeWidth": 2,
                    "cursor": "pointer"
                },
                "encoding": {
                    "theta": {
                        "field": "Risk Exposure ($)",
                        "type": "quantitative",
                        "stack": True
                    },
                    "order": {
                        "field": "Risk Exposure ($)",
                        "type": "quantitative",
                        "sort": "descending"
                    },
                    "color": {
                        "field": "Category",
                        "type": "nominal",
                        "scale": {
                            "range": ["#38BDF8", "#F59E0B", "#EF4444", "#10B981",
                                      "#A78BFA", "#FB7185", "#22D3EE", "#FBBF24"]
                        },
                        "legend": {
                            "title": None,
                            "orient": "right",
                            "labelColor": "#94A3B8",
                            "labelFontSize": 11,
                            "symbolType": "circle",
                            "symbolSize": 90
                        }
                    },
                    "opacity": {
                        "condition": {"param": "hover_cat", "value": 1.0},
                        "value": 0.55
                    },
                    "tooltip": [
                        {"field": "Category", "type": "nominal", "title": "Category"},
                        {"field": "Risk Severity", "type": "nominal", "title": "Risk Severity"},
                        {"field": "Risk Exposure ($)", "type": "quantitative",
                         "title": "Risk Exposure", "format": "$,.2f"},
                        {"field": "Share of Exposure", "type": "quantitative",
                         "title": "Share of Exposure (%)", "format": ".1f"},
                        {"field": "Total Claims", "type": "quantitative", "title": "Total Claims"},
                        {"field": "High Risk Claims", "type": "quantitative", "title": "High Risk Claims"},
                        {"field": "High Risk Rate", "type": "quantitative",
                         "title": "High Risk Rate (%)", "format": ".1f"},
                        {"field": "Avg Fraud Score", "type": "quantitative",
                         "title": "Avg Fraud Score", "format": ".2f"},
                        {"field": "Avg Days", "type": "quantitative",
                         "title": "Avg Days to Resolve", "format": ".1f"}
                    ]
                },
                "params": [{
                    "name": "hover_cat",
                    "select": {"type": "point", "fields": ["Category"], "on": "pointerover"}
                }],
                "view": {"stroke": None},
                "background": "transparent"
            }

            st.vega_lite_chart(df_risk, pie_spec, use_container_width=True, height=300)
            st.caption("Hover any segment for full category detail — exposure, share, claim volume, high-risk rate, fraud score, and resolution time.")
        else:
            st.info("Category risk exposure data loading...")

    with c_churn:
        st.markdown("### 📉 Policyholder Churn by Category")
        st.caption("Plan tier retention dynamics, categorical attrition rates, and revenue exposure.")
        
        tab_churn_tbl, tab_churn_vis = st.tabs([
            "📊 Plan Tier Churn & Revenue Exposure",
            "📉 Category Churn Rate"
        ])
        
        churn_tiers = risk_churn_data.get("churn_by_plan_tier", [])
        with tab_churn_tbl:
            df_tier = pd.DataFrame(churn_tiers) if churn_tiers else pd.DataFrame()

            # Drop rows with no plan tier or no underlying policies so the grid
            # only renders populated tiers (no blank filler rows)
            if not df_tier.empty and "Plan Tier" in df_tier.columns:
                df_tier = df_tier[df_tier["Plan Tier"].notna() & (df_tier["Plan Tier"].astype(str).str.strip() != "")]
                if "Policies" in df_tier.columns:
                    df_tier = df_tier[df_tier["Policies"].fillna(0) > 0]
                df_tier = df_tier.reset_index(drop=True)

            if not df_tier.empty:
                total_tier_policies = int(df_tier["Policies"].sum()) if "Policies" in df_tier.columns else 0
                total_tier_exp = float(df_tier["Revenue Exposure ($)"].sum()) if "Revenue Exposure ($)" in df_tier.columns else 0.0
                avg_tier_churn = float(df_tier["Churn Rate %"].mean()) if "Churn Rate %" in df_tier.columns else 0.0
                
                # Metric summary cards
                st.markdown(f"""
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px;">
                        <div class="kpi-card" style="padding: 8px 10px;">
                            <div class="kpi-title" style="font-size: 0.72rem; color: #94A3B8;">Monitored Policies</div>
                            <div class="kpi-value" style="font-size: 1.25rem; font-weight: 700; color: #38BDF8; margin-top: 2px;">{total_tier_policies:,}</div>
                        </div>
                        <div class="kpi-card" style="padding: 8px 10px;">
                            <div class="kpi-title" style="font-size: 0.72rem; color: #94A3B8;">Revenue Exposure</div>
                            <div class="kpi-value" style="font-size: 1.25rem; font-weight: 700; color: #EF4444; margin-top: 2px;">${total_tier_exp:,.0f}</div>
                        </div>
                        <div class="kpi-card" style="padding: 8px 10px;">
                            <div class="kpi-title" style="font-size: 0.72rem; color: #94A3B8;">Avg Churn Rate</div>
                            <div class="kpi-value" style="font-size: 1.25rem; font-weight: 700; color: #F59E0B; margin-top: 2px;">{avg_tier_churn:.1f}%</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                st.dataframe(
                    df_tier[["Plan Tier", "Policies", "Churn Rate %", "Avg Premium ($)", "Revenue Exposure ($)"]],
                    column_config={
                        "Plan Tier": st.column_config.TextColumn("Plan Tier", width="small"),
                        "Policies": st.column_config.NumberColumn("Policies", format="%d", width="small"),
                        "Churn Rate %": st.column_config.ProgressColumn(
                            "Churn Rate %",
                            help="Predicted customer churn rate",
                            min_value=0.0,
                            max_value=100.0,
                            format="%.1f%%",
                            width="small",
                        ),
                        "Avg Premium ($)": st.column_config.NumberColumn("Avg Premium ($)", format="$%.2f", width="small"),
                        "Revenue Exposure ($)": st.column_config.NumberColumn("Revenue Exposure ($)", format="$%.2f", width="medium"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No plan tier churn data available for the current filter.")

        with tab_churn_vis:
            churn_cats = risk_churn_data.get("churn_by_category", [])
            if churn_cats:
                df_churn = pd.DataFrame(churn_cats)
                st.bar_chart(df_churn.set_index("Category")[["Churn Rate %"]], use_container_width=True, height=220)
                st.dataframe(
                    df_churn[["Category", "Active Base", "Churn Rate %", "Churned Policies", "Revenue at Risk ($)", "Top Churn Driver"]],
                    column_config={
                        "Churn Rate %": st.column_config.NumberColumn("Churn Rate %", format="%.1f%%"),
                        "Revenue at Risk ($)": st.column_config.NumberColumn("Revenue at Risk ($)", format="$%.2f"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=180
                )
            else:
                st.info("Category churn data loading...")
            


# ---------------------------------------------------------
# VIEW 2: ◉ ENTERPRISE AI (Cortex Conversational Studio + File Upload)
# ---------------------------------------------------------
elif st.session_state.current_nav in ["◉ Enterprise AI", "Enterprise AI", "◉ Ask AI"]:
    try:
        st.switch_page("pages/1_Enterprise_AI.py")
    except Exception:
        pass
    st.markdown("## ◉ Enterprise AI Studio")
    # st.caption(f"Intelligent insurance analytics assistant powered by Snowflake Cortex and `{selected_model}`.")

    # Render active document attachment chip if attached (ChatGPT style)
    # Render active document attachment chip if attached (ChatGPT style)
    if st.session_state.uploaded_doc_name:
        col_chip, col_del = st.columns([9, 2])
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
                            ✅ Indexed • {chunks_count} searchable sections
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with col_del:
            if st.button("✖ Remove File", key="btn_discard_attached_chip", use_container_width=True):
                st.session_state.uploaded_doc_name = None
                st.session_state.uploaded_doc_summary = None
                st.session_state.uploaded_doc_text = None
                st.session_state.uploaded_doc_snowflake = None
                st.session_state.doc_uploader_seq += 1
                st.rerun()

    # Left Attachment Popover (like ChatGPT)
    c_attach_btn, c_spacer = st.columns([2.5, 9.5])
    with c_attach_btn:
        with st.popover("📎 Attach Document", use_container_width=True, help="Attach Claim Document, Policy PDF, or Dataset to query"):
            st.markdown("**Attach File for AI Analysis**")
            st.caption("Supported: PDF, CSV, Excel, TXT, JSON, Images • Synced to Snowflake @DOC_STAGE")
            agent_up = st.file_uploader(
                "Upload document",
                type=["pdf", "csv", "xlsx", "xls", "txt", "json", "png", "jpg", "jpeg"],
                key=f"ask_ai_left_popover_uploader_{st.session_state.doc_uploader_seq}",
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
                        ingest_res = {"status": "warning", "message": str(up_err), "chunks_count": 1}
                    
                    st.session_state.uploaded_doc_name = agent_up.name
                    st.session_state.uploaded_doc_summary = summary
                    st.session_state.uploaded_doc_text = content
                    st.session_state.uploaded_doc_snowflake = ingest_res
                    # Report what actually happened rather than a blanket success:
                    # the pipeline can partially index a large document.
                    _st = ingest_res.get("status")
                    _chunks = ingest_res.get("chunks_count") or 0
                    if _st == "success" and not ingest_res.get("truncated"):
                        queue_toast(f"Document indexed — {_chunks} sections", "doc")
                    elif _st == "success":
                        queue_toast(
                            f"Document partially indexed — {_chunks} of "
                            f"{ingest_res.get('total_chunks', '?')} sections", "warning"
                        )
                    else:
                        queue_toast(
                            f"Document not indexed: {ingest_res.get('message', 'unknown error')}",
                            "error"
                        )
                    st.rerun()
    
    # Render Conversation History
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_assistant_response(message, msg_key_prefix=f"chat_{idx}", mgr=cached_sf_mgr, env_config=env_config)
            else:
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
                if st.button(label, key=f"dash_sug_{i}", use_container_width=True, help=prompt_text):
                    st.session_state.selected_prompt = prompt_text
                    st.rerun()

    # User Input
    chat_val = st.chat_input("Ask INSIGHT AI anything (e.g. policy coverage, claim analysis, state premiums)...")
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

            res = call_cortex_agent(
                db=current_db,
                schema=current_sh,
                agent=current_agent,
                prompt=combined_prompt,
                model=selected_model,
                attached_file=attached_doc_label,
                mgr=cached_sf_mgr,
            )

            live_holder.empty()

            resp_text = res.get("response", "No response returned.")
            sql_query = res.get("sql_query")
            query_data = res.get("data")
            thinking = res.get("thinking")
            debug_info = {"prompt": combined_prompt, "response": res, "metadata": res.get("metadata")}

            assistant_msg = {
                "role": "assistant",
                "content": resp_text,
                "sql": sql_query,
                "data": query_data,
                "thinking": thinking,
                "attached_doc": attached_doc_label,
                "raw_payload": debug_info
            }

            render_assistant_response(assistant_msg, msg_key_prefix="latest", mgr=cached_sf_mgr, env_config=env_config)
            st.session_state.messages.append(assistant_msg)


# ---------------------------------------------------------
# VIEW 3: ⚡ EXPLORE (Multi-Dimensional Analytics)
# ---------------------------------------------------------
elif st.session_state.current_nav in ["⚡ Explore", "Explore"]:
    st.markdown("## ⚡ Multi-Dimensional Analytics Explorer")
    st.caption("Slice and drill into live operations, customer, and market intelligence.")

    # Grouped sub-navigation rather than one row of seven tabs: the groups serve
    # different audiences (analyst / CSR / executive) and keep any tab row to three
    # labels so nothing is truncated on narrower screens.
    if "explore_group" not in st.session_state:
        st.session_state.explore_group = "🏛️ Operations"

    explore_group = st.segmented_control(
        "Explorer area",
        options=["🏛️ Operations", "👤 Customers & Ratings", "💡 Strategy & Market"],
        default=st.session_state.explore_group,
        key="explore_group_selector",
        label_visibility="collapsed",
    ) or st.session_state.explore_group
    st.session_state.explore_group = explore_group

    # ------------------------------------------------------------------
    # GROUP 1: OPERATIONS
    # ------------------------------------------------------------------
    if explore_group == "🏛️ Operations":
        exp_tab1, exp_tab2, exp_tab3 = st.tabs(
            ["🏛️ Policies & Revenue", "🚨 Claims & Loss Ratios", "🗺️ Geographic Distribution"]
        )

        with exp_tab1:
            st.markdown("### Policy Types & Plan Tier Breakdown")
            # Values are returned as numbers and formatted in the dataframe, so the
            # columns remain numerically sortable. Formatting them in SQL with
            # CONCAT/TO_VARCHAR produced strings that sorted lexicographically.
            sql_exp_p = f"""SELECT 
                POLICY_TYPE AS "Policy Type", 
                COUNT(POLICY_ID) AS "Policies", 
                ROUND(SUM(PREMIUM_AMOUNT), 2) AS "Revenue", 
                ROUND(AVG(PREMIUM_AMOUNT), 2) AS "Avg Premium", 
                ROUND(AVG(LOSS_RATIO) * 100.0, 1) AS "Avg Loss Ratio %" 
            FROM {current_db}.CORE.POLICIES 
            GROUP BY POLICY_TYPE 
            ORDER BY SUM(PREMIUM_AMOUNT) DESC;"""
            rows_p, _ = cached_sf_mgr.execute_query(sql_exp_p)
            if rows_p is None:
                st.error(f"❌ Query failed: {cached_sf_mgr.get_last_error()}")
            elif not rows_p:
                st.info("No policy records found.")
            else:
                st.dataframe(
                    pd.DataFrame(rows_p),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Revenue": st.column_config.NumberColumn("Revenue", format="$%.2f"),
                        "Avg Premium": st.column_config.NumberColumn("Avg Premium", format="$%.2f"),
                        "Avg Loss Ratio %": st.column_config.NumberColumn("Avg Loss Ratio %", format="%.1f%%"),
                    },
                )

        with exp_tab2:
            st.markdown("### Claims Distribution by Status")
            # Group on the coalesced expression. Previously the SELECT coalesced NULL to
            # 'Approved' but the GROUP BY used the raw column, so NULL statuses were
            # displayed as genuine approvals.
            sql_exp_c = f"""SELECT 
                COALESCE(CLAIM_STATUS, 'Unspecified') AS "Status", 
                COUNT(CLAIM_ID) AS "Count" 
            FROM {current_db}.CORE.CLAIMS 
            GROUP BY COALESCE(CLAIM_STATUS, 'Unspecified')
            ORDER BY "Count" DESC;"""
            rows_c, _ = cached_sf_mgr.execute_query(sql_exp_c)
            if rows_c is None:
                st.error(f"❌ Query failed: {cached_sf_mgr.get_last_error()}")
            elif not rows_c:
                st.info("No claims status records found.")
            else:
                df_c = pd.DataFrame(rows_c)
                st.bar_chart(df_c.set_index("Status"), use_container_width=True, height=280)
                st.dataframe(df_c, use_container_width=True, hide_index=True)

        with exp_tab3:
            st.markdown("### States by Premium Revenue")
            top_n = st.slider("States to show", min_value=3, max_value=15, value=10, key="exp_geo_topn")
            sql_exp_g = f"""SELECT 
                COALESCE(c.STATE, 'Unknown') AS "State", 
                ROUND(SUM(p.PREMIUM_AMOUNT), 2) AS "Total Premium", 
                COUNT(p.POLICY_ID) AS "Policies" 
            FROM {current_db}.CORE.POLICIES p 
            JOIN {current_db}.CORE.CUSTOMERS c ON p.CUSTOMER_ID = c.CUSTOMER_ID 
            GROUP BY COALESCE(c.STATE, 'Unknown')
            ORDER BY "Total Premium" DESC 
            LIMIT {int(top_n)};"""
            rows_g, _ = cached_sf_mgr.execute_query(sql_exp_g)
            if rows_g is None:
                st.error(f"❌ Query failed: {cached_sf_mgr.get_last_error()}")
            elif not rows_g:
                st.info("No geographic customer data found.")
            else:
                df_geo = pd.DataFrame(rows_g)
                # Bar, not line: states are categorical and a line implies continuity
                # between them.
                st.bar_chart(df_geo.set_index("State")[["Total Premium"]],
                             use_container_width=True, height=300)
                st.dataframe(
                    df_geo, use_container_width=True, hide_index=True,
                    column_config={
                        "Total Premium": st.column_config.NumberColumn("Total Premium", format="$%.2f")
                    },
                )

    # ------------------------------------------------------------------
    # GROUP 2: CUSTOMERS & RATINGS
    # ------------------------------------------------------------------
    elif explore_group == "👤 Customers & Ratings":
        cust_tab, ratings_tab = st.tabs(["👤 Customer Directory & Plan Rating", "⭐ Plan Rating Analytics"])

        with cust_tab:
            st.markdown("### Customer Directory")
            st.caption(
                "Select a customer to see their matched plans and submit a rating. "
                "Ratings are written through `SP_RATE_PLAN` — the same procedure the agent's "
                "RatePlan tool uses."
            )

            f_search, f_state, f_plan, f_status, f_limit = st.columns([3.2, 1.5, 2, 1.8, 1.2])
            with f_search:
                cust_search = st.text_input(
                    "Search by name, ID or email", value="", key="exp_cust_search",
                    placeholder="e.g. John, CUST-00012, @email",
                )
            with f_state:
                state_opts = ["All", "TX", "CA", "PA", "IL", "AZ", "NY", "GA"]
                cust_state = st.selectbox("State", state_opts, key="exp_cust_state")
            with f_plan:
                # Options come from the data rather than a hardcoded list, so they stay
                # correct if the policy mix changes.
                plan_opts = ["All plans"] + fetch_plan_filter_options().get("plan_names", [])
                cust_plan = st.selectbox(
                    "Plan held", plan_opts, key="exp_cust_plan",
                    help="Policy type and tier the customer holds, from CORE.POLICIES",
                )
            with f_status:
                status_labels = {
                    "All": "All",
                    "ACTIVE": "Active only",
                    "INACTIVE": "No active policy",
                }
                cust_status = st.selectbox(
                    "Status", list(status_labels.keys()),
                    format_func=lambda s: status_labels[s], key="exp_cust_status",
                    help="Active means the customer holds at least one policy with POLICY_STATUS = 'Active'",
                )
            with f_limit:
                cust_limit = st.selectbox("Rows", [50, 100, 200, 500], index=2, key="exp_cust_limit")

            directory = fetch_customer_directory(
                search=cust_search or None,
                state=None if cust_state == "All" else cust_state,
                plan=None if cust_plan == "All plans" else cust_plan,
                status=cust_status,
                limit=int(cust_limit),
            )

            if not directory:
                st.info("No customers match the current filters.")
            else:
                df_dir = pd.DataFrame(directory)
                active_n = int((df_dir["ACTIVE_POLICY_COUNT"] > 0).sum())
                st.caption(
                    f"Showing **{len(df_dir):,}** customers — {active_n:,} with an active policy, "
                    f"{len(df_dir) - active_n:,} without"
                )
                st.dataframe(
                    df_dir,
                    use_container_width=True,
                    hide_index=True,
                    height=280,
                    column_config={
                        "CUSTOMER_ID": st.column_config.TextColumn("Customer ID", width="small"),
                        "CUSTOMER_NAME": st.column_config.TextColumn("Name", width="medium"),
                        "CUSTOMER_STATUS": st.column_config.TextColumn("Status", width="small"),
                        "PLANS_HELD": st.column_config.TextColumn("Plans Held", width="medium"),
                        "ACTIVE_POLICY_COUNT": st.column_config.NumberColumn("Active", width="small"),
                        "AGE": st.column_config.NumberColumn("Age", width="small"),
                        "ANNUAL_INCOME": st.column_config.NumberColumn("Income", format="$%.0f"),
                        "CREDIT_SCORE": st.column_config.NumberColumn("Credit", width="small"),
                        "TOTAL_PREMIUM": st.column_config.NumberColumn("Premium", format="$%.2f"),
                        "POLICY_COUNT": st.column_config.NumberColumn("Policies", width="small"),
                        "MATCH_COUNT": st.column_config.NumberColumn("Matches", width="small"),
                        "RATING_COUNT": st.column_config.NumberColumn("Ratings", width="small"),
                    },
                )

                label_by_id = {
                    r["CUSTOMER_ID"]: f"{r['CUSTOMER_ID']} — {r['CUSTOMER_NAME']} ({r.get('STATE') or '—'})"
                    for r in directory
                }
                sel_customer = st.selectbox(
                    "Selected customer",
                    options=list(label_by_id.keys()),
                    format_func=lambda cid: label_by_id.get(cid, cid),
                    key="exp_sel_customer",
                )

                c360 = fetch_customer_360(sel_customer)

                if c360.get("status") != "success":
                    st.warning(
                        f"Could not load the full profile for `{sel_customer}`: "
                        f"{c360.get('message', 'unknown error')}"
                    )
                else:
                    prof = c360["profile"]
                    summ = c360["summary"]

                    st.markdown(
                        f"#### 👤 {prof.get('CUSTOMER_NAME') or sel_customer} "
                        f"<span style='color:#64748B;font-size:0.8rem;'>`{sel_customer}`</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"{prof.get('OCCUPATION') or 'Occupation unknown'} • "
                        f"{prof.get('CITY') or '—'}, {prof.get('STATE') or '—'} "
                        f"{prof.get('ZIP_CODE') or ''} • Age {prof.get('AGE') or '—'} • "
                        f"{prof.get('MARITAL_STATUS') or '—'} • "
                        f"Customer since {str(prof.get('CUSTOMER_SINCE') or '—')[:10]} • "
                        f"{prof.get('EMAIL') or 'no email'}"
                    )

                    k1, k2, k3, k4, k5 = st.columns(5)
                    k1.metric("Policies", f"{summ['policy_count']}",
                              f"{summ['active_policy_count']} active" if summ['policy_count'] else None,
                              delta_color="off")
                    k2.metric("Written Premium", f"${summ['total_premium']:,.0f}")
                    k3.metric("Claims", f"{summ['claim_count']}",
                              f"${summ['total_claimed']:,.0f} claimed" if summ['claim_count'] else None,
                              delta_color="off")
                    # None means there is no premium to divide by, so no ratio is shown
                    # rather than a misleading 0.0%.
                    k4.metric("Claims / Premium",
                              f"{summ['loss_ratio_pct']:.1f}%" if summ['loss_ratio_pct'] is not None else "n/a",
                              help="Total claimed amount as a percentage of written premium")
                    k5.metric("Churn Risk",
                              f"{summ['max_churn_probability'] * 100:.0f}%" if summ['max_churn_probability'] is not None else "No prediction",
                              help="Highest churn probability across this customer's policies")

                    risk_bits = []
                    if summ["policies_at_risk"]:
                        risk_bits.append(
                            f"⚠️ **{summ['policies_at_risk']}** policy(ies) flagged at risk, "
                            f"**${summ['revenue_at_risk']:,.0f}** revenue at risk"
                        )
                    if summ["fraud_claim_count"]:
                        risk_bits.append(f"🚩 **{summ['fraud_claim_count']}** fraud-flagged claim(s)")
                    if summ["avg_rating"] is not None:
                        risk_bits.append(
                            f"⭐ **{summ['avg_rating']:.2f}** average rating from "
                            f"{summ['rating_count']} review(s)"
                        )
                    if risk_bits:
                        st.markdown(" &nbsp;·&nbsp; ".join(risk_bits))

                    c360_tabs = st.tabs([
                        f"📋 Policies ({summ['policy_count']})",
                        f"🧾 Claims ({summ['claim_count']})",
                        f"📉 Risk & Churn ({summ['policies_at_risk']})",
                        f"⭐ Ratings ({summ['rating_count']})",
                    ])

                    with c360_tabs[0]:
                        if c360["policies"]:
                            st.dataframe(
                                pd.DataFrame(c360["policies"]),
                                width="stretch", hide_index=True,
                                column_config={
                                    "PREMIUM_AMOUNT": st.column_config.NumberColumn("Premium", format="$%.0f"),
                                    "COVERAGE_AMOUNT": st.column_config.NumberColumn("Coverage", format="$%.0f"),
                                    "DEDUCTIBLE": st.column_config.NumberColumn("Deductible", format="$%.0f"),
                                    "LOSS_RATIO": st.column_config.NumberColumn("Loss Ratio", format="%.2f"),
                                },
                            )
                        else:
                            st.info("No policies in CORE.POLICIES for this customer.")

                    with c360_tabs[1]:
                        if c360["claims"]:
                            st.dataframe(
                                pd.DataFrame(c360["claims"]),
                                width="stretch", hide_index=True,
                                column_config={
                                    "CLAIM_AMOUNT": st.column_config.NumberColumn("Claimed", format="$%.0f"),
                                    "APPROVED_AMOUNT": st.column_config.NumberColumn("Approved", format="$%.0f"),
                                    "FRAUD_SCORE": st.column_config.ProgressColumn(
                                        "Fraud Score", min_value=0.0, max_value=1.0, format="%.2f"
                                    ),
                                },
                            )
                        else:
                            st.info("No claims in CORE.CLAIMS for this customer.")

                    with c360_tabs[2]:
                        if c360["at_risk"]:
                            st.caption("RISK.AT_RISK_POLICIES — latest identification per policy")
                            st.dataframe(
                                pd.DataFrame(c360["at_risk"]),
                                width="stretch", hide_index=True,
                                column_config={
                                    "REVENUE_AT_RISK": st.column_config.NumberColumn("Revenue at Risk", format="$%.0f"),
                                    "CHURN_PROBABILITY": st.column_config.ProgressColumn(
                                        "Churn Prob.", min_value=0.0, max_value=1.0, format="%.2f"
                                    ),
                                },
                            )
                        else:
                            st.info("Not flagged in RISK.AT_RISK_POLICIES.")

                        if c360["churn"]:
                            st.caption(
                                "RISK.CHURN_PREDICTIONS — latest prediction per policy. "
                                "The table holds multiple predictions per policy, so it is "
                                "deduped here rather than showing every historic run."
                            )
                            st.dataframe(
                                pd.DataFrame(c360["churn"]),
                                width="stretch", hide_index=True,
                                column_config={
                                    "CHURN_PROBABILITY": st.column_config.ProgressColumn(
                                        "Churn Prob.", min_value=0.0, max_value=1.0, format="%.2f"
                                    ),
                                    "CONFIDENCE_SCORE": st.column_config.NumberColumn("Confidence", format="%.2f"),
                                },
                            )
                        else:
                            st.info("No churn predictions for this customer.")

                    with c360_tabs[3]:
                        if c360["ratings"]:
                            st.dataframe(
                                pd.DataFrame(c360["ratings"]),
                                width="stretch", hide_index=True,
                                column_config={
                                    "RATING": st.column_config.NumberColumn("★", format="%.1f"),
                                    "REVIEW_TEXT": st.column_config.TextColumn("Review", width="large"),
                                },
                            )
                        else:
                            st.info("This customer has not rated any plan yet.")


                st.markdown("#### 🎯 Matched Plans")
                matches = fetch_customer_matches(sel_customer)

                if not matches:
                    st.info(
                        "No saved product matches for this customer. Only 10 of 250 customers "
                        "ship with matches; generating them calls Cortex, so it runs on request."
                    )
                    if st.button("⚙ Generate Matches", key="exp_gen_matches", type="primary"):
                        with st.spinner("Matching products with INSIGHT AI..."):
                            gen = backend_service.generate_customer_matches(
                                customer_id=sel_customer, mgr=cached_sf_mgr
                            )
                        if gen.get("status") == "success":
                            clear_rating_caches()
                            # Queued, not shown inline: the st.rerun() below discards anything
                            # emitted here, which is why the old st.success was never seen.
                            queue_toast("Product matches generated", "success")
                            st.rerun()
                        else:
                            st.error(f"❌ Match generation failed: {gen.get('message')}")
                            toast_now("Match generation failed", "error")
                else:
                    df_m = pd.DataFrame(matches)
                    # Plan economics and benefits instead of STRATEGY_SCORES: the raw
                    # per-strategy weights explain how the ranking was produced but say
                    # nothing about the plan, which is what matters when choosing or
                    # rating one.
                    st.dataframe(
                        df_m[["MATCH_RANK", "PRODUCT_NAME", "CATEGORY", "PLAN_TIER",
                              "MONTHLY_PREMIUM", "ANNUAL_PREMIUM", "COVERAGE_LIMIT",
                              "KEY_FEATURES", "OVERALL_SCORE"]],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "MATCH_RANK": st.column_config.NumberColumn("Rank", width="small"),
                            "PRODUCT_NAME": st.column_config.TextColumn("Plan", width="medium"),
                            "CATEGORY": st.column_config.TextColumn("Category", width="small"),
                            "PLAN_TIER": st.column_config.TextColumn("Tier", width="small"),
                            "MONTHLY_PREMIUM": st.column_config.NumberColumn("Premium / mo", format="$%.2f"),
                            "ANNUAL_PREMIUM": st.column_config.NumberColumn("Premium / yr", format="$%.2f"),
                            "COVERAGE_LIMIT": st.column_config.NumberColumn("Coverage", format="$%.0f"),
                            "KEY_FEATURES": st.column_config.TextColumn("Benefits", width="large"),
                            "OVERALL_SCORE": st.column_config.ProgressColumn(
                                "Match Score", min_value=0.0, max_value=100.0, format="%.1f"
                            ),
                        },
                    )

                    with st.expander("📄 Plan Detail — eligibility, benefits & match reasoning"):
                        for mrow in matches:
                            fam = mrow.get("FAMILY_FRIENDLY")
                            premium = mrow.get("MONTHLY_PREMIUM")
                            coverage = mrow.get("COVERAGE_LIMIT")
                            st.markdown(
                                f"**#{mrow.get('MATCH_RANK')} · {mrow.get('PRODUCT_NAME')}** "
                                f"`{mrow.get('PRODUCT_ID')}` — "
                                f"{mrow.get('CATEGORY')} / {mrow.get('PLAN_TIER')}"
                            )
                            d1, d2, d3, d4 = st.columns(4)
                            d1.metric("Monthly Premium",
                                      f"${float(premium):,.2f}" if premium is not None else "Not listed")
                            d2.metric("Coverage Limit",
                                      f"${float(coverage):,.0f}" if coverage is not None else "Not listed")
                            d3.metric("Eligible Age",
                                      f"{mrow.get('MIN_AGE')}–{mrow.get('MAX_AGE')}"
                                      if mrow.get("MIN_AGE") is not None else "Not listed")
                            d4.metric("Min Income",
                                      f"${float(mrow['MIN_INCOME']):,.0f}"
                                      if mrow.get("MIN_INCOME") is not None else "Not listed")

                            feats = str(mrow.get("KEY_FEATURES") or "").strip()
                            if feats:
                                st.markdown("**Benefits**")
                                for f in [x.strip() for x in feats.split(",") if x.strip()]:
                                    st.markdown(f"- {f}")
                            else:
                                st.caption("No benefits recorded in PRODUCT_CATALOG for this plan.")

                            st.caption(
                                f"**Eligibility:** {mrow.get('ELIGIBILITY_CRITERIA') or 'Not specified'}  \n"
                                f"**Risk profile:** {mrow.get('RISK_LEVEL_MATCH') or '—'} &nbsp;·&nbsp; "
                                f"**Family friendly:** "
                                + ("Yes" if fam is True else ("No" if fam is False else "Not specified"))
                            )
                            if mrow.get("AI_REASONING"):
                                st.caption(f"**Why this matched:** {mrow['AI_REASONING']}")
                            st.divider()

                    def _plan_opt_label(m):
                        prem = m.get("MONTHLY_PREMIUM")
                        money = f" — ${float(prem):,.2f}/mo" if prem is not None else ""
                        return (f"#{m['MATCH_RANK']} {m['PRODUCT_NAME']} "
                                f"({m['CATEGORY']}/{m['PLAN_TIER']}){money}")

                    rate_label = {m["PRODUCT_ID"]: _plan_opt_label(m) for m in matches}
                    r_col1, r_col2 = st.columns([5, 2])
                    with r_col1:
                        sel_product = st.selectbox(
                            "Plan to rate",
                            options=list(rate_label.keys()),
                            format_func=lambda pid: rate_label.get(pid, pid),
                            key="exp_sel_product",
                        )
                    with r_col2:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        open_dialog = st.button("⭐ Rate This Plan", key="exp_open_rating",
                                                type="primary", use_container_width=True)

                    # The form lives in a dialog so submitting it redraws the modal rather
                    # than every sibling tab.
                    @st.dialog("Rate Plan")
                    def _rating_dialog(customer_id: str, product_id: str, product_label: str):
                        st.markdown(f"**Customer:** `{customer_id}`")
                        st.markdown(f"**Plan:** {product_label}")
                        st.divider()

                        stars = st.feedback("stars", key="exp_rating_stars")
                        review = st.text_area(
                            "Review (optional)", key="exp_rating_review",
                            placeholder="What did the customer say about this plan?",
                            height=110,
                        )
                        st.caption("Ratings are 1–5 stars and update the plan's average immediately.")

                        if st.button("Submit Rating", type="primary", use_container_width=True,
                                     key="exp_rating_submit"):
                            if stars is None:
                                st.warning("Select a star rating before submitting.")
                            else:
                                # st.feedback returns 0-4; SP_RATE_PLAN expects 1.0-5.0.
                                value = float(stars) + 1.0
                                with st.spinner("Submitting via SP_RATE_PLAN..."):
                                    res = backend_service.submit_plan_rating(
                                        customer_id=customer_id,
                                        product_id=product_id,
                                        rating=value,
                                        review_text=review or None,
                                        mgr=cached_sf_mgr,
                                    )
                                if res.get("status") == "success":
                                    out = res.get("result", {})
                                    clear_rating_caches()
                                    toast_now(
                                        f"{value:.1f}★ recorded — average now "
                                        f"{out.get('new_avg_rating', '—')}",
                                        "success",
                                    )
                                    st.success(
                                        f"✅ Recorded **{value:.1f}★** as `{out.get('rating_id', '—')}`. "
                                        f"Average moved {out.get('old_avg_rating', '—')} → "
                                        f"**{out.get('new_avg_rating', '—')}** "
                                        f"across {out.get('total_reviews', '—')} review(s)."
                                    )
                                    st.button("Close", key="exp_rating_close")
                                else:
                                    st.error(f"❌ {res.get('message')}")
                                    toast_now("Rating could not be saved", "error")

                    if open_dialog:
                        _rating_dialog(sel_customer, sel_product, rate_label.get(sel_product, sel_product))

        with ratings_tab:
            st.markdown("### Plan Rating Analytics")
            ratings = fetch_plan_ratings_summary()

            if ratings.get("status") != "success":
                st.error(f"❌ Could not load rating summary: {ratings.get('message')}")
            else:
                products = ratings["products"]
                rt1, rt2, rt3 = st.columns(3)
                rt1.metric("Products", f"{ratings['product_count']}")
                rt2.metric("Total Reviews", f"{ratings['total_reviews']:,}")
                rt3.metric("Products with Reviews", f"{ratings['rated_products']}")

                if ratings["total_reviews"] < ratings["product_count"]:
                    # Be explicit: the displayed average is seeded catalog data, not
                    # aggregated customer feedback.
                    st.info(
                        "ℹ️ Most products show a **seeded baseline rating** from "
                        "`PRODUCT_CATALOG` with zero customer reviews behind it. Averages only "
                        "reflect real feedback once reviews are submitted."
                    )

                df_r = pd.DataFrame(products)
                st.dataframe(
                    df_r[["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PLAN_TIER",
                          "CURRENT_AVG_RATING", "TOTAL_REVIEWS", "FIVE_STAR", "FOUR_STAR",
                          "THREE_STAR", "TWO_STAR", "ONE_STAR"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "CURRENT_AVG_RATING": st.column_config.NumberColumn("Avg ★", format="%.1f"),
                        "TOTAL_REVIEWS": st.column_config.NumberColumn("Reviews", width="small"),
                    },
                )

                st.markdown("##### Average Rating by Category")
                df_cat = (
                    df_r.groupby("CATEGORY", as_index=False)["CURRENT_AVG_RATING"]
                    .mean().round(2).sort_values("CURRENT_AVG_RATING", ascending=False)
                )
                st.bar_chart(df_cat.set_index("CATEGORY"), use_container_width=True, height=260)

    # ------------------------------------------------------------------
    # GROUP 3: STRATEGY & MARKET
    # ------------------------------------------------------------------
    else:
        strat_tab, market_tab = st.tabs(["💡 Strategic Recommendations", "📈 Market & Pricing"])

        with strat_tab:
            recs = fetch_strategic_recommendations()

            if recs.get("status") != "success":
                st.error(f"❌ Could not load recommendations: {recs.get('message')}")
            else:
                rec_rows = recs["recommendations"]
                head_l, head_r = st.columns([6, 2])
                with head_l:
                    st.markdown("### Strategic Recommendation Engine")
                    gen_at = str(recs.get("generated_at") or "")[:19].replace("T", " ")
                    st.caption(
                        f"AI-generated from live pricing, churn and loss-ratio signals • "
                        f"batch `{recs.get('batch_id') or '—'}` • generated **{gen_at or 'unknown'}**"
                    )
                with head_r:
                    st.markdown("<div style='height: 26px;'></div>", unsafe_allow_html=True)
                    if st.button("🔄 Regenerate", key="exp_regen_recs", use_container_width=True):
                        with st.spinner("Generating recommendations with INSIGHT AI..."):
                            out = backend_service.regenerate_strategic_recommendations(mgr=cached_sf_mgr)
                        if out.get("status") == "success":
                            fetch_strategic_recommendations.clear()
                            queue_toast("Strategic recommendations regenerated", "success")
                            st.rerun()
                        else:
                            st.error(f"❌ Regeneration failed: {out.get('message')}")
                            toast_now("Regeneration failed", "error")

                pc = recs["priority_counts"]
                k1, k2, k3 = st.columns(3)
                k1.metric("🔴 High Priority", pc.get("HIGH", 0))
                k2.metric("🟠 Medium", pc.get("MEDIUM", 0))
                k3.metric("🟢 Low", pc.get("LOW", 0))

                prio_filter = st.multiselect(
                    "Filter by priority",
                    options=["HIGH", "MEDIUM", "LOW"],
                    default=["HIGH", "MEDIUM", "LOW"],
                    key="exp_rec_prio",
                )

                shown = [r for r in rec_rows if str(r.get("PRIORITY", "")).upper() in prio_filter]
                if not shown:
                    st.info("No recommendations match the selected priorities.")

                prio_style = {
                    "HIGH": ("#F87171", "rgba(239, 68, 68, 0.35)"),
                    "MEDIUM": ("#FBBF24", "rgba(245, 158, 11, 0.35)"),
                    "LOW": ("#34D399", "rgba(16, 185, 129, 0.30)"),
                }

                for rec in shown:
                    prio = str(rec.get("PRIORITY", "LOW")).upper()
                    colour, border = prio_style.get(prio, prio_style["LOW"])
                    st.markdown(f"""
                        <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid {border};
                                    border-left: 4px solid {colour}; border-radius: 10px;
                                    padding: 14px 18px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;
                                        margin-bottom: 8px;">
                                <span style="font-weight: 800; font-size: 1.0rem; color: #F1F5F9;">
                                    {html.escape(str(rec.get('HEADLINE') or '—'))}
                                </span>
                                <span style="font-size: 0.70rem; font-weight: 700; color: {colour};
                                             border: 1px solid {border}; border-radius: 10px;
                                             padding: 2px 9px; white-space: nowrap;">
                                    {html.escape(prio)} • {html.escape(str(rec.get('CATEGORY') or '—'))}
                                </span>
                            </div>
                            <div style="color: #CBD5E1; font-size: 0.86rem; line-height: 1.5;
                                        margin-bottom: 10px;">
                                {html.escape(str(rec.get('DETAILS') or ''))}
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
                                        font-size: 0.80rem;">
                                <div>
                                    <div style="color: #94A3B8; font-size: 0.68rem;
                                                text-transform: uppercase;">Action</div>
                                    <div style="color: #E2E8F0;">
                                        {html.escape(str(rec.get('ACTION_ITEM') or '—'))}
                                    </div>
                                </div>
                                <div>
                                    <div style="color: #94A3B8; font-size: 0.68rem;
                                                text-transform: uppercase;">Estimated Impact</div>
                                    <div style="color: #34D399; font-weight: 600;">
                                        {html.escape(str(rec.get('ESTIMATED_IMPACT') or '—'))}
                                    </div>
                                </div>
                            </div>
                            <div style="color: #64748B; font-size: 0.70rem; margin-top: 9px;">
                                Source: <code>{html.escape(str(rec.get('DATA_SOURCE') or '—'))}</code>
                                • {html.escape(str(rec.get('REC_ID') or ''))}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

        with market_tab:
            st.markdown("### Market Position & Competitor Pricing")
            market = fetch_market_pricing()

            if market.get("status") != "success":
                st.error(f"❌ Could not load market data: {market.get('message')}")
            else:
                comparison = market["comparison"]
                pos = market["position_counts"]
                trends = market["trend_counts"]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Products Benchmarked", len(comparison))
                m2.metric("Competitively Priced", pos.get("COMPETITIVE", 0))
                m3.metric("Underpriced", pos.get("UNDERPRICED", 0))
                m4.metric("Overpriced", pos.get("OVERPRICED", 0) + pos.get("SLIGHTLY HIGH", 0))

                st.caption(
                    "Market movement across competitor products: "
                    + " • ".join(f"**{k.title()}** {v}" for k, v in sorted(trends.items()))
                )

                df_cmp = pd.DataFrame(comparison)
                for col in ["OUR_PREMIUM", "COMP_AVG_PREMIUM", "PRICE_DIFF_PCT",
                            "OUR_RATING", "COMP_AVG_RATING"]:
                    if col in df_cmp.columns:
                        df_cmp[col] = pd.to_numeric(df_cmp[col], errors="coerce")

                st.markdown("##### Our Premium vs Competitor Average")
                scatter_spec = {
                    "mark": {"type": "circle", "size": 130, "opacity": 0.85},
                    "encoding": {
                        "x": {"field": "COMP_AVG_PREMIUM", "type": "quantitative",
                              "title": "Competitor Avg Premium ($)"},
                        "y": {"field": "OUR_PREMIUM", "type": "quantitative",
                              "title": "Our Premium ($)"},
                        "color": {
                            "field": "PRICE_POSITION", "type": "nominal",
                            "legend": {"title": None, "orient": "bottom",
                                       "labelColor": "#94A3B8", "symbolType": "circle"},
                        },
                        "tooltip": [
                            {"field": "OUR_PRODUCT", "type": "nominal", "title": "Product"},
                            {"field": "CATEGORY", "type": "nominal", "title": "Category"},
                            {"field": "PLAN_TIER", "type": "nominal", "title": "Tier"},
                            {"field": "OUR_PREMIUM", "type": "quantitative",
                             "title": "Our Premium", "format": "$,.2f"},
                            {"field": "COMP_AVG_PREMIUM", "type": "quantitative",
                             "title": "Competitor Avg", "format": "$,.2f"},
                            {"field": "PRICE_DIFF_PCT", "type": "quantitative",
                             "title": "Difference (%)", "format": ".2f"},
                            {"field": "OUR_RATING", "type": "quantitative",
                             "title": "Our Rating", "format": ".1f"},
                            {"field": "COMP_AVG_RATING", "type": "quantitative",
                             "title": "Competitor Rating", "format": ".1f"},
                            {"field": "COMPETITOR_COUNT", "type": "quantitative", "title": "Competitors"},
                            {"field": "NEW_ENTRANTS", "type": "quantitative", "title": "New Entrants"},
                            {"field": "EXITING", "type": "quantitative", "title": "Exiting"},
                            {"field": "PRICE_POSITION", "type": "nominal", "title": "Position"},
                        ],
                    },
                    "view": {"stroke": None},
                    "background": "transparent",
                }
                st.vega_lite_chart(df_cmp, scatter_spec, use_container_width=True, height=330)

                st.markdown("##### Price Positioning Detail")

                pp_cols = [
                    "CATEGORY", "PLAN_TIER", "OUR_PRODUCT", "INDICATED_ACTION",
                    "OUR_PREMIUM", "COMP_AVG_PREMIUM", "PRICE_GAP_MONTHLY", "PRICE_DIFF_PCT",
                    "SUGGESTED_LOW", "SUGGESTED_HIGH",
                    "COVERAGE_ADVANTAGE_PCT", "FEATURE_GAP", "RATING_EDGE",
                    "COMPETITIVE_PRESSURE", "POLICIES_IN_FORCE",
                    "ANNUAL_REVENUE_EXPOSED", "ANNUAL_REVENUE_DELTA_IF_REPRICED",
                    "AVG_LOSS_RATIO_PCT", "PRICE_POSITION",
                ]
                # One config for every column, shared across the sub-tabs so a field is
                # formatted identically wherever it appears.
                PP_CONFIG = {
                    "CATEGORY": st.column_config.TextColumn("Category", width="small"),
                    "PLAN_TIER": st.column_config.TextColumn("Tier", width="small"),
                    "OUR_PRODUCT": st.column_config.TextColumn("Plan", width="medium"),
                    "INDICATED_ACTION": st.column_config.TextColumn("Indicated Action", width="small"),
                    "PRICE_POSITION": st.column_config.TextColumn("Position", width="small"),

                    "OUR_PREMIUM": st.column_config.NumberColumn("Our Premium", format="$%.2f"),
                    "COMP_AVG_PREMIUM": st.column_config.NumberColumn("Comp Avg", format="$%.2f"),
                    "PRICE_GAP_MONTHLY": st.column_config.NumberColumn("Gap $/mo", format="$%.2f"),
                    "PRICE_DIFF_PCT": st.column_config.NumberColumn("Diff %", format="%.2f%%"),
                    "SUGGESTED_LOW": st.column_config.NumberColumn("Suggest Low", format="$%.2f"),
                    "SUGGESTED_HIGH": st.column_config.NumberColumn("Suggest High", format="$%.2f"),

                    "OUR_COVERAGE": st.column_config.NumberColumn("Our Coverage", format="$%.0f"),
                    "COMP_AVG_COVERAGE": st.column_config.NumberColumn("Comp Avg Coverage", format="$%.0f"),
                    "COVERAGE_ADVANTAGE_PCT": st.column_config.NumberColumn(
                        "Coverage Adv %", format="%.1f%%",
                        help="How much more coverage we give than the market average"),
                    "COVERAGE_PER_DOLLAR": st.column_config.NumberColumn(
                        "Our Cover / $", format="%.0f",
                        help="Coverage bought per dollar of monthly premium"),
                    "MARKET_COVERAGE_PER_DOLLAR": st.column_config.NumberColumn(
                        "Market Cover / $", format="%.0f",
                        help="Competitor average coverage per dollar of premium"),

                    "OUR_FEATURES": st.column_config.NumberColumn("Our Features", width="small"),
                    "COMP_AVG_FEATURES": st.column_config.NumberColumn("Comp Avg Features", format="%.1f"),
                    "FEATURE_GAP": st.column_config.NumberColumn(
                        "Feature Gap", format="%.1f",
                        help="Our feature count minus the competitor average"),

                    "OUR_RATING": st.column_config.NumberColumn("Our ★", format="%.1f"),
                    "COMP_AVG_RATING": st.column_config.NumberColumn("Comp ★", format="%.1f"),
                    "RATING_EDGE": st.column_config.NumberColumn(
                        "★ Edge", format="%.2f",
                        help="Our rating minus the competitor average"),

                    "COMPETITOR_COUNT": st.column_config.NumberColumn("Competitors", width="small"),
                    "NEW_ENTRANTS": st.column_config.NumberColumn("Entering", width="small"),
                    "EXITING": st.column_config.NumberColumn("Exiting", width="small"),
                    "NET_ENTRANTS": st.column_config.NumberColumn(
                        "Net", width="small", help="Entering minus exiting"),
                    "COMPETITIVE_PRESSURE": st.column_config.TextColumn("Pressure", width="small"),
                    "MARKET_SHARE_CONTESTED": st.column_config.NumberColumn(
                        "Share Contested %", format="%.1f%%",
                        help="Combined market share of competitors in this category and tier"),
                    "CHEAPEST_COMP_PREMIUM": st.column_config.NumberColumn("Cheapest Comp", format="$%.2f"),
                    "DEAREST_COMP_PREMIUM": st.column_config.NumberColumn("Dearest Comp", format="$%.2f"),

                    "POLICIES_IN_FORCE": st.column_config.NumberColumn("In Force", width="small"),
                    "ACTIVE_POLICIES": st.column_config.NumberColumn("Active", width="small"),
                    "AVG_LOSS_RATIO_PCT": st.column_config.NumberColumn("Loss Ratio %", format="%.1f%%"),
                    "ANNUAL_REVENUE_EXPOSED": st.column_config.NumberColumn(
                        "Revenue Exposed", format="$%.0f"),
                    "ANNUAL_REVENUE_DELTA_IF_REPRICED": st.column_config.NumberColumn(
                        "Δ If Repriced", format="$%.0f",
                        help="Annual revenue change if moved to the suggested price"),
                }

                # Category/tier/plan repeat in every group as row anchors. Between them the
                # four groups cover all 34 returned columns.
                ANCHOR = ["CATEGORY", "PLAN_TIER", "OUR_PRODUCT"]
                PP_GROUPS = [
                    ("💵 Pricing", ANCHOR + [
                        "INDICATED_ACTION", "OUR_PREMIUM", "COMP_AVG_PREMIUM",
                        "PRICE_GAP_MONTHLY", "PRICE_DIFF_PCT",
                        "SUGGESTED_LOW", "SUGGESTED_HIGH", "PRICE_POSITION",
                    ]),
                    ("🎁 Value & Features", ANCHOR + [
                        "OUR_PREMIUM", "OUR_COVERAGE", "COMP_AVG_COVERAGE",
                        "COVERAGE_ADVANTAGE_PCT", "COVERAGE_PER_DOLLAR",
                        "MARKET_COVERAGE_PER_DOLLAR",
                        "OUR_FEATURES", "COMP_AVG_FEATURES", "FEATURE_GAP",
                        "OUR_RATING", "COMP_AVG_RATING", "RATING_EDGE",
                    ]),
                    ("⚔ Competition", ANCHOR + [
                        "OUR_PREMIUM", "COMP_AVG_PREMIUM",
                        "COMPETITOR_COUNT", "NEW_ENTRANTS", "EXITING", "NET_ENTRANTS",
                        "COMPETITIVE_PRESSURE", "MARKET_SHARE_CONTESTED",
                        "CHEAPEST_COMP_PREMIUM", "DEAREST_COMP_PREMIUM",
                    ]),
                    ("💰 Revenue Impact", ANCHOR + [
                        "INDICATED_ACTION", "POLICIES_IN_FORCE", "ACTIVE_POLICIES",
                        "OUR_PREMIUM", "AVG_LOSS_RATIO_PCT",
                        "ANNUAL_REVENUE_EXPOSED", "ANNUAL_REVENUE_DELTA_IF_REPRICED",
                    ]),
                ]

                pp_tabs = st.tabs([g[0] for g in PP_GROUPS])
                for pp_tab, (_, group_cols) in zip(pp_tabs, PP_GROUPS):
                    with pp_tab:
                        shown = [c for c in group_cols if c in df_cmp.columns]
                        st.dataframe(
                            df_cmp[shown],
                            use_container_width=True,
                            hide_index=True,
                            height=320,
                            column_config={k: v for k, v in PP_CONFIG.items() if k in shown},
                        )

                missing_cols = sorted(
                    set(df_cmp.columns) - {c for _, g in PP_GROUPS for c in g}
                )
                if missing_cols:
                    st.caption(
                        "Columns returned but not shown in any group: "
                        + ", ".join(f"`{c}`" for c in missing_cols)
                    )

                no_book = int(len(df_cmp) - market.get("products_with_book", 0))
                if no_book:
                    st.caption(
                        f"⚠️ {no_book} of {len(df_cmp)} catalogue products have **no in-force "
                        "policies**, so repricing them moves no current revenue. "
                        "`In Force` and `Revenue Exposed` read 0 for those rows rather than "
                        "being hidden — a repricing recommendation on a product nobody holds "
                        "is a market-entry decision, not a pricing one."
                    )
                with st.expander("🏢 Competitor Product Detail", expanded=True):
                    st.caption(
                        f"All {len(market['competitors'])} competitor products from "
                        "`COMPETITOR_PRICING`, filterable by category."
                    )
                    df_comp = pd.DataFrame(market["competitors"])
                    cat_opts = ["All"] + sorted(df_comp["CATEGORY"].dropna().unique().tolist())
                    pick_cat = st.selectbox("Category", cat_opts, key="exp_comp_cat")
                    if pick_cat != "All":
                        df_comp = df_comp[df_comp["CATEGORY"] == pick_cat]
                    st.dataframe(
                        df_comp,
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                        column_config={
                            "MONTHLY_PREMIUM": st.column_config.NumberColumn("Premium", format="$%.2f"),
                            "COVERAGE_LIMIT": st.column_config.NumberColumn("Coverage", format="$%.0f"),
                            "CUSTOMER_RATING": st.column_config.NumberColumn("★", format="%.1f"),
                            "MARKET_SHARE_PCT": st.column_config.NumberColumn("Share %", format="%.2f%%"),
                        },
                    )


                # ---- 8-factor engine, on demand ----
                st.markdown("##### 🎯 8-Factor Price Optimization")
                st.caption(
                    "Runs `SP_PRICE_OPTIMIZE` — the same procedure the agent's PriceOptimize "
                    "tool calls, so this panel and the chat answer cannot disagree. One "
                    "procedure call per product, so it runs on request."
                )

                opt_labels = {
                    f"{r['CATEGORY']}|{r['PLAN_TIER']}":
                        f"{r['OUR_PRODUCT']} — {r['CATEGORY']}/{r['PLAN_TIER']} "
                        f"(${float(r['OUR_PREMIUM']):,.2f}/mo, {r['INDICATED_ACTION']})"
                    for r in market["comparison"]
                }
                o_c1, o_c2 = st.columns([5, 2])
                with o_c1:
                    sel_opt = st.selectbox(
                        "Plan to optimize", options=list(opt_labels.keys()),
                        format_func=lambda k: opt_labels[k], key="exp_opt_plan",
                    )
                with o_c2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    run_opt = st.button("⚙ Run Optimization", key="exp_run_opt",
                                        type="primary", use_container_width=True)

                if run_opt:
                    o_cat, o_tier = sel_opt.split("|")
                    with st.spinner(f"Running 8-factor engine for {o_cat}/{o_tier}..."):
                        st.session_state.price_opt_result = backend_service.run_price_optimization(
                            category=o_cat, plan_tier=o_tier, mgr=cached_sf_mgr
                        )
                    # No rerun follows, so this is emitted immediately.
                    _opt_res = st.session_state.price_opt_result or {}
                    if _opt_res.get("status") == "success":
                        toast_now(
                            f"{o_cat}/{o_tier} scored "
                            f"{_opt_res.get('overall_score')}/100",
                            "chart",
                        )
                    else:
                        toast_now("Optimization failed", "error")

                opt = st.session_state.get("price_opt_result")
                if opt and opt.get("status") != "success":
                    st.error(f"❌ Optimization failed: {opt.get('message')}")
                elif opt:
                    prod = opt.get("our_product", {})
                    rng = opt.get("suggested_price_range", {})
                    mkt = opt.get("market_analysis", {})
                    internal = opt.get("internal_metrics", {})
                    score = opt.get("overall_score")
                    rec = str(opt.get("recommendation") or "")

                    band = ("#FB7185" if score is not None and score < 50
                            else "#FBBF24" if score is not None and score < 70 else "#34D399")
                    st.markdown(
                        f"""
                        <div style="background: rgba(15,23,42,0.75); border-left: 4px solid {band};
                                    border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                          <div style="color:#E2E8F0; font-weight:700; font-size:1.02rem;">
                            {html.escape(str(prod.get('product_name') or ''))}
                            <span style="color:#64748B; font-size:0.8rem;">
                              {html.escape(str(prod.get('product_id') or ''))}</span>
                          </div>
                          <div style="color:{band}; font-weight:700; margin-top:4px;">
                            {html.escape(rec)}
                          </div>
                          <div style="color:#94A3B8; font-size:0.78rem; margin-top:4px;">
                            Overall score {score} / 100
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                    g1, g2, g3, g4 = st.columns(4)
                    g1.metric("Current Premium", f"${float(rng.get('current', 0)):,.2f}")
                    g2.metric("Suggested Range",
                              f"${float(rng.get('low', 0)):,.2f}–${float(rng.get('high', 0)):,.2f}")
                    g3.metric("Market Average", f"${float(rng.get('market_avg', 0)):,.2f}",
                              f"{mkt.get('price_diff_pct')}% vs market", delta_color="off")
                    g4.metric("Retention Rate",
                              f"{internal.get('retention_rate')}%" if internal.get("retention_rate") is not None else "n/a",
                              f"Loss ratio {internal.get('loss_ratio')}%", delta_color="off")

                    weakest = opt.get("weakest_factor")
                    if weakest:
                        st.markdown(
                            f"**Largest drag:** {weakest['Factor']} "
                            f"(score {weakest['Score']}, {weakest['Weight %']}% weight)"
                        )

                    f_left, f_right = st.columns([3, 4])
                    with f_left:
                        st.caption("Factor scores, weakest first")
                        st.dataframe(
                            pd.DataFrame(opt.get("factors", [])),
                            width="stretch", hide_index=True,
                            column_config={
                                "Score": st.column_config.ProgressColumn(
                                    "Score", min_value=0, max_value=100, format="%d"),
                            },
                        )
                    with f_right:
                        st.caption("Competitive landscape")
                        comp_rows = opt.get("competitors", [])
                        if comp_rows:
                            df_land = pd.DataFrame(comp_rows)
                            st.dataframe(
                                df_land, width="stretch", hide_index=True,
                                column_config={
                                    "monthly_premium": st.column_config.NumberColumn("Premium", format="$%.2f"),
                                    "coverage_limit": st.column_config.NumberColumn("Coverage", format="$%.0f"),
                                    "rating": st.column_config.NumberColumn("★", format="%.1f"),
                                    "market_share": st.column_config.NumberColumn("Share %", format="%.1f%%"),
                                    "differentiator": st.column_config.TextColumn("Differentiator", width="medium"),
                                },
                            )
                        else:
                            st.info("No competitor rows returned for this category and tier.")



# ---------------------------------------------------------
# VIEW 4: 📊 DATA (Snowflake Catalog & Multi-Schema Table Browser)
# ---------------------------------------------------------
elif st.session_state.current_nav in ["📊 Data", "Data"]:
    st.markdown("## 📊 Snowflake Multi-Schema Data Catalog")
    st.caption("Live enterprise catalog metadata, schema distribution, and interactive table browser across all database schemas.")

    c_cat_schema, c_cat_stats = st.columns([2, 2])
    with c_cat_schema:
        catalog_schema_filter = st.selectbox(
            "Filter Catalog by Schema",
            ["All Schemas", "CORE", "ANALYTICS", "RISK", "PREMIUM", "UNIFIEDAI_SH"],
            index=0,
            key="catalog_schema_selector"
        )
    
    schema_clause = f"AND TABLE_SCHEMA = '{catalog_schema_filter}'" if catalog_schema_filter != "All Schemas" else ""
    sql_tables = f"""SELECT 
        TABLE_SCHEMA AS "Schema",
        TABLE_NAME AS "Table Name", 
        ROW_COUNT AS "Rows", 
        BYTES AS "Bytes", 
        TABLE_TYPE AS "Table Type" 
    FROM {current_db}.INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA') {schema_clause}
    ORDER BY TABLE_SCHEMA, TABLE_NAME;"""
    table_rows, _ = cached_sf_mgr.execute_query(sql_tables)
    df_catalog = pd.DataFrame(table_rows or [])
    
    with c_cat_stats:
        total_tbls = len(df_catalog)
        total_rows_sum = int(df_catalog["Rows"].sum()) if not df_catalog.empty and "Rows" in df_catalog else 0
        st.markdown(f"""
            <div style="background: rgba(30,41,59,0.7); padding: 12px 16px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.15); margin-top: 4px;">
                <span style="color:#94A3B8; font-size:0.8rem;">Catalog Scope:</span> 
                <b style="color:#38BDF8;">{catalog_schema_filter}</b> &nbsp;•&nbsp; 
                <span style="color:#94A3B8; font-size:0.8rem;">Tables:</span> <b style="color:#34D399;">{total_tbls}</b> &nbsp;•&nbsp; 
                <span style="color:#94A3B8; font-size:0.8rem;">Indexed Records:</span> <b style="color:#F1F5F9;">{total_rows_sum:,}</b>
            </div>
        """, unsafe_allow_html=True)

    st.dataframe(df_catalog, use_container_width=True)
    
    st.markdown("### 🔍 Live Multi-Schema Table Preview")
    preview_table_options = [
        ("CORE", "POLICIES"),
        ("CORE", "CLAIMS"),
        ("CORE", "CUSTOMERS"),
        ("CORE", "AGENTS"),
        ("ANALYTICS", "CLAIMS_KPI"),
        ("ANALYTICS", "POLICY_TRENDS"),
        ("ANALYTICS", "LOSS_RATIO_HISTORY"),
        ("RISK", "AT_RISK_POLICIES"),
        ("RISK", "CHURN_PREDICTIONS"),
        ("PREMIUM", "PLAN_TIERS"),
        ("PREMIUM", "PREMIUM_CALCULATIONS"),
        ("UNIFIEDAI_SH", "DQ_RULES"),
        ("UNIFIEDAI_SH", "DQ_VALIDATION_RESULTS")
    ]
    
    # Filter preview table list if a specific schema is chosen
    if catalog_schema_filter != "All Schemas":
        available_previews = [f"{s}.{t}" for s, t in preview_table_options if s == catalog_schema_filter]
    else:
        available_previews = [f"{s}.{t}" for s, t in preview_table_options]
        
    selected_preview = st.selectbox(
        "Select Table to Preview Live Rows",
        available_previews if available_previews else ["CORE.POLICIES"],
        index=0,
        key="table_preview_selector"
    )
    
    p_schema, p_table = selected_preview.split(".")
    sql_preview = f"SELECT * FROM {current_db}.{p_schema}.{p_table} LIMIT 8;"
    preview_rows, _ = cached_sf_mgr.execute_query(sql_preview)
    st.dataframe(pd.DataFrame(preview_rows or []), use_container_width=True)


# ---------------------------------------------------------
# VIEW 5: 📄 DOCS (Semantic Layer & Dictionary)
# ---------------------------------------------------------
elif st.session_state.current_nav == "📄 Docs":
    st.markdown("## 📄 Semantic Views & Data Dictionary")
    st.caption("Enterprise insurance semantic data model and entity definitions across all UNIFIEDAI_DB schemas.")

    st.markdown("""
    ### 🏛️ Unified Enterprise Data Architecture: `UNIFIEDAI_DB`
    
    | Schema | Tables | Description |
    | :--- | :--- | :--- |
    | **`CORE`** | `POLICIES`, `CUSTOMERS`, `CLAIMS`, `AGENTS` | Primary transactional and policyholder master entities. |
    | **`ANALYTICS`** | `CLAIMS_KPI`, `POLICY_TRENDS`, `LOSS_RATIO_HISTORY`, `FRAUD_ALERTS`, `WHATIF_SIMULATION_LOG` | Curated KPI time series, aggregated financial trends, and loss trajectories. |
    | **`RISK`** | `AT_RISK_POLICIES`, `CHURN_PREDICTIONS`, `RISK_FACTORS`, `V_RISK_CHURN` | AI/ML risk scoring, attrition forecasting, and churn risk drivers. |
    | **`PREMIUM`** | `PLAN_TIERS`, `PREMIUM_CALCULATIONS`, `PREMIUM_FACTORS` | Underwriting risk adjustments, actuarial factors, and plan configurations. |
    | **`UNIFIEDAI_SH`** | `DQ_RULES`, `DQ_VALIDATION_RESULTS`, `DQ_COLUMN_LINEAGE`, `DOCUMENT_CHUNKS` | Enterprise Data Trust Score (DTS) rules, lineage, and document knowledge embeddings. |

    ---
    ### 🔑 Key Dimensions & Metrics
    - **Key Dimensions**: `CUSTOMER_ID`, `POLICY_ID`, `AGENT_ID`, `CLAIM_TYPE`, `STATE`, `PLAN_TIER`
    - **Measures**: `PREMIUM_AMOUNT`, `CLAIM_AMOUNT`, `DAYS_TO_RESOLVE`, `FRAUD_SCORE`, `CHURN_PROBABILITY`
    - **Loss Ratio Formula**: `LOSS_RATIO = CLAIM_AMOUNT / PREMIUM_AMOUNT`
    - **Data Quality**: Field completeness and row validity measured directly on `CORE.POLICIES`, `CORE.CLAIMS` and `CORE.CUSTOMERS`. Rule-based dimensions appear only when `UNIFIEDAI_SH.DQ_RULES` is populated.
    """)


# ---------------------------------------------------------
# VIEW 6: 🛡 QUALITY (Data Trust & Integrity Scorecard)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🛡 Quality":
    st.markdown("## 🛡 Data Trust & Integrity Scorecard")
    st.caption("Real-time data quality validation checks, rule categories, and pass thresholds from UNIFIEDAI_SH.DQ_RULES.")

    sql_dq_scorecard = f"""SELECT 
        RULE_NAME AS "Rule Name", 
        RULE_CATEGORY AS "Dimension", 
        TARGET_TABLE AS "Target Table", 
        THRESHOLD_PASS AS "Pass Threshold (%)", 
        SEVERITY AS "Severity", 
        ACTIVE_FLAG AS "Active", 
        DESCRIPTION AS "Description" 
    FROM {current_db}.UNIFIEDAI_SH.DQ_RULES 
    ORDER BY RULE_CATEGORY, RULE_NAME;"""
    dq_rows, _ = cached_sf_mgr.execute_query(sql_dq_scorecard)
    st.dataframe(pd.DataFrame(dq_rows or []), use_container_width=True)


# ---------------------------------------------------------
# VIEW 7: 🚨 INCIDENTS (Fraud & High Risk Alerts)
# ---------------------------------------------------------
elif st.session_state.current_nav == "🚨 Incidents":
    st.markdown("## 🚨 Incident & High Risk Alert Center")
    st.caption("Flagged claims, potential fraud indicators, and priority escalations from CORE.CLAIMS.")

    st.markdown("### ⚠️ Active High-Risk Claims (Fraud Score >= 0.75 OR Fraud Flag = TRUE)")
    sql_incidents = f"""SELECT 
        CLAIM_ID AS "Claim ID", 
        POLICY_ID AS "Policy ID", 
        CLAIM_TYPE AS "Claim Type", 
        CONCAT('$', TO_VARCHAR(ROUND(CLAIM_AMOUNT, 2), '999,999,990.00')) AS "Claim Amount", 
        ROUND(FRAUD_SCORE, 2) AS "Fraud Score", 
        PRIORITY AS "Priority", 
        CLAIM_STATUS AS "Status", 
        COALESCE(FRAUD_REASON, 'Suspicious claim pattern') AS "Fraud Reason" 
    FROM {current_db}.CORE.CLAIMS 
    WHERE FRAUD_FLAG = TRUE OR FRAUD_SCORE >= 0.75 
    ORDER BY FRAUD_SCORE DESC, CLAIM_AMOUNT DESC 
    LIMIT 25;"""
    inc_rows, _ = cached_sf_mgr.execute_query(sql_incidents)
    st.dataframe(pd.DataFrame(inc_rows or []), use_container_width=True)


# ---------------------------------------------------------
# VIEW 8: ⚙ SETTINGS (Connection & Configuration)
# ---------------------------------------------------------
elif st.session_state.current_nav == "⚙ Settings":
    st.markdown("## ⚙ Configuration & Connection Settings")
    st.caption("Active connection parameters and system environment variables.")

    st.json({
        "current_user": current_user,
        "role": current_role,
        "warehouse": current_wh,
        "database": current_db,
        "schema": current_sh,
        "agent": current_agent,
        "persistent_connection": True
    })
