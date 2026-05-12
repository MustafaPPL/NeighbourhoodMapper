from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import os
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from branca.colormap import linear
from streamlit_folium import st_folium

from scripts.analysis.build_weighted_priority_map import (
    PARKS_GARDENS_FS_BASE,
    arcgis_query_to_gdf,
    load_community_pharmacies,
    load_family_hubs,
    load_gp_practices,
    load_nhs_trusts,
)
from webapp.analysis import (
    DEFAULT_CATCHMENT_RADIUS_M,
    DEFAULT_HUB_SCORE_WEIGHTS,
    DEFAULT_SUGGESTION_COUNT,
    DEFAULT_SUGGESTION_MIN_SPACING_M,
    INDEX_DEFINITIONS,
    AnalysisResult,
    run_analysis,
)
from webapp.config import AppConfig, ICB_CHOICES
from webapp.data_access import geocode_candidate_postcodes, load_asset_counts, load_neighbourhoods
from webapp.data_validation import ValidationReport, validate_config


st.set_page_config(page_title="Neighbourhood Hub Ranker", layout="wide")

APP_ROOT = Path(__file__).resolve().parent
LOGO_PATH = APP_ROOT / "data" / "logos" / "PPL Logo_RGB.png"
BRAND_PURPLE = "#490E6F"
BRAND_PURPLE_DARK = "#350355"
BRAND_PURPLE_SOFT = "#FAF6FD"
BRAND_PURPLE_MID = "#EAE3F0"
BRAND_TEXT = "#0D0517"
PAGES = ["Introduction", "Configure Inputs", "Outputs", "Methodology"]
METHODOLOGY_PATH = APP_ROOT / "docs" / "METHODOLOGY.md"
AUTH_USERNAME_ENV = "APP_LOGIN_USERNAME"
AUTH_PASSWORD_ENV = "APP_LOGIN_PASSWORD"
AUTH_PASSWORD_SHA256_ENV = "APP_LOGIN_PASSWORD_SHA256"
ICB_CODE_BY_NAME = {
    "NHS North Central London ICB": "NCL",
    "NHS North East London ICB": "NEL",
    "NHS North West London ICB": "NWL",
    "NHS South East London ICB": "SEL",
    "NHS South West London ICB": "SWL",
}
PARKS_AND_GARDENS_OVERLAY = "Parks and gardens"


def _load_acute_hospitals() -> gpd.GeoDataFrame:
    trusts = load_nhs_trusts()
    return trusts[trusts["trust_type"].str.contains("Acute", case=False, na=False)].copy()


ASSET_OVERLAY_STYLES = {
    "GP practices": {"geometry_type": "point", "loader": load_gp_practices, "color": "#1565C0", "radius": 3},
    "Community pharmacies": {
        "geometry_type": "point",
        "loader": load_community_pharmacies,
        "color": "#E65100",
        "radius": 3,
    },
    "Family hubs": {"geometry_type": "point", "loader": load_family_hubs, "color": "#2E7D32", "radius": 3},
    PARKS_AND_GARDENS_OVERLAY: {
        "geometry_type": "polygon",
        "color": "#267300",
        "fill_color": "#D3FFBE",
        "weight": 1.0,
        "fill_opacity": 0.28,
    },
    "Acute hospitals": {
        "geometry_type": "point",
        "loader": _load_acute_hospitals,
        "color": "#1A3A5C",
        "marker_style": "triangle",
    },
}


@st.cache_data(show_spinner=False)
def load_image_data_uri(path_str: str) -> str | None:
    path = Path(path_str)
    if not path.exists():
        return None

    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower())
    if mime_type is None:
        return None

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def render_logo_markup(class_name: str) -> str:
    logo_uri = load_image_data_uri(str(LOGO_PATH))
    if logo_uri is None:
        return '<div class="brand-fallback">PPL</div>'
    return f'<img src="{logo_uri}" alt="Private Public Ltd" class="{class_name}">'


def switch_page(page_name: str) -> None:
    st.query_params.clear()
    st.query_params["page"] = page_name
    st.rerun()


def _persistent_state_key(name: str) -> str:
    return f"persistent__{name}"


def _widget_state_key(name: str) -> str:
    return f"widget__{name}"


def prepare_persisted_widget(name: str, default, normalize=None) -> str:
    widget_key = _widget_state_key(name)
    persistent_key = _persistent_state_key(name)
    value = st.session_state.get(widget_key, st.session_state.get(persistent_key, default))
    if normalize is not None:
        value = normalize(value)
    st.session_state[persistent_key] = value
    st.session_state[widget_key] = value
    return widget_key


def remember_persisted_widget(name: str) -> None:
    widget_key = _widget_state_key(name)
    persistent_key = _persistent_state_key(name)
    if widget_key in st.session_state:
        st.session_state[persistent_key] = st.session_state[widget_key]


def _get_shared_login_settings() -> tuple[str | None, str | None, bool]:
    username = os.getenv(AUTH_USERNAME_ENV, "").strip()
    password_hash = os.getenv(AUTH_PASSWORD_SHA256_ENV, "").strip().lower()
    password = os.getenv(AUTH_PASSWORD_ENV, "")

    if username and password_hash:
        return username, password_hash, True
    if username and password:
        return username, password, False
    return None, None, False


def _hash_password(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _shared_login_is_enabled() -> bool:
    username, secret, _ = _get_shared_login_settings()
    return bool(username and secret)


def _password_matches(submitted_password: str, configured_secret: str, uses_hash: bool) -> bool:
    candidate = _hash_password(submitted_password) if uses_hash else submitted_password
    return hmac.compare_digest(candidate, configured_secret)


def require_authentication() -> None:
    configured_username, configured_secret, uses_hash = _get_shared_login_settings()
    if not configured_username or not configured_secret:
        return

    if st.session_state.get("authenticated_username") == configured_username:
        return

    st.html("""
    <style>
    .stApp { background: #350355 !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    .block-container {
        padding: 6vh 1rem 2rem !important;
        max-width: 420px !important;
        margin: 0 auto !important;
    }
    div[data-testid="stForm"] {
        background: #FFFFFF !important;
        border-radius: 0 0 14px 14px !important;
        border: 1px solid rgba(73,14,111,0.18) !important;
        border-top: none !important;
        padding: 20px 24px 16px !important;
    }
    div[data-testid="stForm"] label { color: #3B2F48 !important; font-size: 0.8rem !important; }
    div[data-testid="stForm"] input {
        background: #FAF6FD !important;
        border-color: #D9CFE3 !important;
        color: #0D0517 !important;
    }
    </style>
    """)

    st.html("""
    <div style="background:linear-gradient(150deg,#5B1A8A 0%,#490E6F 55%,#350355 100%);
                border-radius:14px 14px 0 0;padding:40px 28px 32px;text-align:center">
        <div style="color:white;font-size:3rem;font-weight:800;letter-spacing:-0.03em;
                    font-family:'Poppins',Inter,sans-serif;line-height:1;margin-bottom:20px">
            PPL
        </div>
        <div style="color:rgba(255,255,255,0.45);font-size:0.58rem;font-weight:700;
                    letter-spacing:0.16em;text-transform:uppercase;font-family:'Poppins',Inter,sans-serif;
                    margin-bottom:6px">
            NHS · ICB Decision Support
        </div>
        <div style="color:white;font-size:1.05rem;font-weight:700;line-height:1.3;
                    font-family:'Poppins',Inter,sans-serif;margin-bottom:12px">
            Neighbourhood Hub<br>Decision Explorer
        </div>
        <div style="color:rgba(255,255,255,0.45);font-size:0.75rem;line-height:1.5;
                    font-family:'Poppins',Inter,sans-serif">
            Sign in to access the workspace
        </div>
    </div>
    """)

    with st.form("shared_login_form", clear_on_submit=False):
        submitted_username = st.text_input("Username", autocomplete="username")
        submitted_password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        username_matches = hmac.compare_digest(submitted_username.strip(), configured_username)
        password_matches = _password_matches(submitted_password, configured_secret, uses_hash)
        if username_matches and password_matches:
            st.session_state["authenticated_username"] = configured_username
            st.session_state.pop("auth_error", None)
            st.rerun()
        else:
            st.session_state["auth_error"] = "Incorrect username or password."

    if st.session_state.get("auth_error"):
        st.error(st.session_state["auth_error"])

    st.stop()



def inject_styles() -> None:
    st.html(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');
        :root {
            --ppl-purple: #490E6F;
            --ppl-deep: #350355;
            --ppl-lilac: #9576FF;
            --ppl-ink: #0D0517;
            --ppl-ink2: #3B2F48;
            --ppl-muted: #6B6078;
            --ppl-line: #EAE3F0;
            --ppl-line-strong: #D9CFE3;
            --ppl-paper: #FFFFFF;
            --ppl-cream: #FAF6FD;
            --shadow-sm: 0 1px 2px rgba(73,14,111,.06), 0 2px 8px rgba(73,14,111,.04);
            --shadow-md: 0 4px 14px rgba(73,14,111,.08), 0 10px 30px rgba(73,14,111,.06);
        }

        /* -- Global -- */
        html, body {
            font-family: 'Poppins', Inter, system-ui, sans-serif !important;
            font-size: 15px;
        }
        .stApp { background: var(--ppl-cream); }

        /* Hide Streamlit chrome */
        header[data-testid="stHeader"] { display: none !important; }
        footer { display: none !important; }
        #MainMenu { display: none !important; }
        .stDeployButton { display: none !important; }

        /* Hide sidebar — navigation lives in top bar */
        section[data-testid="stSidebar"] { display: none !important; }
        section[data-testid="stMain"] { margin-left: 0 !important; }

        /* Main content block */
        .block-container {
            padding: 28px 2.5rem 3rem !important;
            max-width: 1100px;
            margin: 0 auto !important;
        }

        /* -- Top app banner -- */
        .ppl-topbar-banner {
            background: linear-gradient(135deg, #5B1A8A 0%, #490E6F 60%, #350355 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 14px 18px;
            box-shadow: 0 2px 16px rgba(53,3,85,0.40);
            margin-bottom: 12px;
        }
        .ppl-topbar-banner-inner {
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
        }
        .ppl-topnav-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
        }
        .ppl-topnav-logo {
            height: 26px;
            width: auto;
            object-fit: contain;
            filter: brightness(0) invert(1);
        }
        .ppl-topnav-wordmark {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .ppl-topnav-name {
            font-size: 0.75rem;
            font-weight: 700;
            color: #FFFFFF;
            letter-spacing: -0.01em;
            line-height: 1.15;
        }
        .ppl-topnav-sub {
            font-size: 0.57rem;
            color: rgba(255,255,255,0.55);
            font-weight: 400;
            letter-spacing: 0.02em;
        }
        .ppl-topnav-right {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .ppl-topnav-user {
            font-size: 0.75rem;
            color: rgba(255,255,255,0.6);
        }

        /* -- Intro page hero -- */
        .intro-hero {
            background: linear-gradient(135deg, #5B1A8A 0%, #490E6F 50%, #350355 100%);
            border-radius: 18px;
            padding: 52px 48px 48px;
            margin-bottom: 20px;
        }
        .intro-hero-eyebrow {
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: rgba(255,255,255,0.55);
            margin-bottom: 12px;
        }
        .intro-hero-title {
            font-size: 2.2rem;
            font-weight: 800;
            color: white;
            line-height: 1.08;
            letter-spacing: -0.02em;
            margin-bottom: 14px;
        }
        .intro-hero-subtitle {
            font-size: 0.95rem;
            color: rgba(255,255,255,0.75);
            line-height: 1.65;
            max-width: 560px;
            margin-bottom: 28px;
        }
        /* -- Intro how-it-works steps -- */
        .intro-section-label {
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            color: var(--ppl-purple);
            margin-bottom: 14px;
        }
        .intro-steps-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-bottom: 32px;
        }
        .intro-step {
            background: white;
            border: 1px solid var(--ppl-line);
            border-radius: 14px;
            padding: 20px 22px;
            box-shadow: var(--shadow-sm);
        }
        .intro-step-num {
            width: 28px;
            height: 28px;
            background: rgba(73,14,111,0.08);
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--ppl-purple);
            margin-bottom: 10px;
        }
        .intro-step-title {
            font-size: 0.88rem;
            font-weight: 700;
            color: var(--ppl-ink);
            margin-bottom: 6px;
        }
        .intro-step-body {
            font-size: 0.78rem;
            color: var(--ppl-muted);
            line-height: 1.6;
        }

        /* -- Intro scoring section -- */
        .intro-scoring-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin-bottom: 32px;
            align-items: start;
        }
        .intro-scoring-copy {
            font-size: 0.85rem;
            color: var(--ppl-ink2);
            line-height: 1.7;
        }
        .intro-formula-block {
            background: var(--ppl-cream);
            border-left: 3px solid var(--ppl-purple);
            border-radius: 0 10px 10px 0;
            padding: 14px 18px;
            font-family: ui-monospace, SFMono-Regular, 'Courier New', monospace;
            font-size: 0.78rem;
            color: var(--ppl-ink);
            line-height: 2.0;
        }
        .intro-callout {
            background: #FFF8EC;
            border: 1px solid #E0A030;
            border-radius: 10px;
            padding: 13px 17px;
            font-size: 0.8rem;
            color: var(--ppl-ink2);
            line-height: 1.6;
            margin-bottom: 8px;
        }

        /* -- Hero shells (Configure Inputs, Methodology pages) -- */
        .hero-shell {
            border: 1px solid var(--ppl-line);
            border-radius: 18px;
            padding: 22px 24px;
            background: linear-gradient(135deg, #FFFFFF 0%, #FBF8FE 60%, #F2ECF9 100%);
            box-shadow: var(--shadow-md);
            margin-bottom: 20px;
        }
        .hero-brand {
            color: var(--ppl-purple);
            font-weight: 700;
            letter-spacing: 0.12em;
            font-size: 0.62rem;
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .hero-title {
            color: var(--ppl-ink);
            font-size: 1.65rem;
            font-weight: 700;
            line-height: 1.1;
            margin-bottom: 6px;
        }
        .hero-subtitle {
            color: var(--ppl-ink2);
            font-size: 0.875rem;
            max-width: 860px;
            line-height: 1.55;
        }
        .hero-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }
        .hero-chip {
            border: 1px solid rgba(73,14,111,.12);
            border-radius: 999px;
            padding: 8px 12px;
            background: rgba(255,255,255,.78);
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .hero-chip-label {
            color: var(--ppl-muted);
            font-size: 0.72rem;
        }
        .hero-chip-value {
            color: var(--ppl-ink);
            font-size: 0.76rem;
            font-weight: 700;
        }

        /* -- Section shells -- */
        .section-shell {
            border: 1px solid var(--ppl-line);
            border-radius: 12px;
            padding: 14px 16px;
            background: var(--ppl-paper);
            box-shadow: var(--shadow-sm);
            margin-bottom: 14px;
        }
        .section-title {
            color: var(--ppl-ink);
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .section-copy {
            color: var(--ppl-muted);
            font-size: 0.8rem;
            margin-bottom: 10px;
            line-height: 1.5;
        }
        .mini-label {
            color: var(--ppl-purple);
            font-size: 0.62rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 5px;
        }

        /* -- Buttons (primary) -- */
        .stButton > button,
        div[data-testid="stDownloadButton"] > button {
            background: var(--ppl-purple);
            color: white;
            border: 2px solid var(--ppl-purple);
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.8rem;
            font-family: 'Poppins', Inter, system-ui, sans-serif;
            padding: 0.35rem 1.1rem;
            transition: background 150ms cubic-bezier(.2,.7,.2,1),
                        border-color 150ms cubic-bezier(.2,.7,.2,1);
        }
        .stButton > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            background: var(--ppl-deep);
            border-color: var(--ppl-deep);
            color: white;
        }

        /* -- Buttons (secondary / outlined) -- */
        .stButton > button[data-testid="baseButton-secondary"] {
            background: white !important;
            color: var(--ppl-purple) !important;
            border: 2px solid var(--ppl-line-strong) !important;
        }
        .stButton > button[data-testid="baseButton-secondary"]:hover {
            background: var(--ppl-cream) !important;
            border-color: var(--ppl-purple) !important;
            color: var(--ppl-purple) !important;
        }

        /* -- Segmented control (mode selector) -- */
        div[data-testid="stSegmentedControl"] {
            width: 100%;
        }
        div[data-testid="stSegmentedControl"] > div {
            width: 100%;
            gap: 6px !important;
        }
        div[data-testid="stSegmentedControl"] button {
            flex: 1 !important;
            min-height: 48px !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
        }

        /* -- Metrics -- */
        div[data-testid="stMetric"] {
            background: var(--ppl-paper);
            border: 1px solid var(--ppl-line);
            padding: 10px 12px;
            border-radius: 12px;
            box-shadow: var(--shadow-sm);
        }
        div[data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
        div[data-testid="stMetricValue"] { font-size: 1.3rem !important; }

        /* -- Misc Streamlit overrides -- */
        input[type="radio"] { accent-color: var(--ppl-purple); }
        input[type="checkbox"] { accent-color: var(--ppl-purple) !important; }
        input[type="range"] { accent-color: var(--ppl-purple) !important; }
        div[role="radiogroup"] label[data-baseweb="radio"] { align-items: center; }
        .stAlert { font-size: 0.8rem; }
        .stDataFrame { font-size: 0.8rem; }
        h1, h2, h3 { font-size: 1.1rem !important; font-weight: 700 !important; }
        p, li, label { font-size: 0.875rem; }

        /* -- Force BaseWeb slider and toggle to PPL purple -- */
        [data-baseweb="slider"] [role="slider"] {
            background-color: var(--ppl-purple) !important;
            border-color: var(--ppl-purple) !important;
        }
        [data-baseweb="slider"] [data-testid="stSliderThumb"] {
            background-color: var(--ppl-purple) !important;
            border-color: var(--ppl-purple) !important;
        }
        [data-testid="stSlider"] div[role="slider"] {
            background-color: var(--ppl-purple) !important;
            border-color: var(--ppl-purple) !important;
        }

        @media (max-width: 900px) {
            .block-container { padding: 20px 1.2rem 2rem !important; }
            .intro-steps-grid { grid-template-columns: 1fr; }
            .intro-scoring-grid { grid-template-columns: 1fr; }
            .intro-hero { padding: 36px 24px 32px; }
            .intro-hero-title { font-size: 1.7rem; }
            .ppl-topbar-banner-inner { align-items: flex-start; gap: 10px; }
            .ppl-topnav-right { justify-content: flex-end; }
        }
        </style>
        """
    )


def render_topnav(current_page: str) -> None:
    logo_uri = load_image_data_uri(str(LOGO_PATH))
    logo_html = (
        f'<img src="{logo_uri}" class="ppl-topnav-logo" alt="Private Public Ltd">'
        if logo_uri
        else '<span style="font-weight:800;color:#490E6F;font-size:1.1rem;line-height:1">PPL</span>'
    )
    nav_labels = {
        "Introduction": "Introduction",
        "Configure Inputs": "Inputs",
        "Outputs": "Outputs",
        "Methodology": "Methodology",
    }
    banner_right_html = ""
    if _shared_login_is_enabled() and st.session_state.get("authenticated_username"):
        username = st.session_state["authenticated_username"]
        banner_right_html = (
            f'<div class="ppl-topnav-right">'
            f'<span class="ppl-topnav-user">{username}</span>'
            f"</div>"
        )

    st.html(
        f"""
<div class="ppl-topbar-banner">
    <div class="ppl-topbar-banner-inner">
        <div class="ppl-topnav-brand">
            {logo_html}
            <div class="ppl-topnav-wordmark">
                <span class="ppl-topnav-name">Neighbourhood Hub Explorer</span>
                <span class="ppl-topnav-sub">NHS · ICB Decision Support · Private Public Ltd</span>
            </div>
        </div>
        {banner_right_html}
    </div>
</div>
        """
    )

    label_to_page = {label: page for page, label in nav_labels.items()}
    nav_widget_key = "topnav_page"
    nav_synced_page_key = "topnav_page_synced"
    current_label = nav_labels[current_page]

    if st.session_state.get(nav_synced_page_key) != current_page:
        st.session_state[nav_widget_key] = current_label
        st.session_state[nav_synced_page_key] = current_page

    nav_col, action_col = st.columns([5.2, 1.2], gap="small", vertical_alignment="center")
    with nav_col:
        selected_label = st.segmented_control(
            "Navigation",
            options=list(nav_labels.values()),
            key=nav_widget_key,
            label_visibility="collapsed",
        )
    with action_col:
        if _shared_login_is_enabled() and st.session_state.get("authenticated_username"):
            if st.button("Sign out", key="topnav_signout", use_container_width=True):
                st.session_state.pop("authenticated_username", None)
                st.session_state.pop("auth_error", None)
                st.query_params.clear()
                st.rerun()

    if selected_label and label_to_page[selected_label] != current_page:
        target_page = label_to_page[selected_label]
        st.session_state[nav_synced_page_key] = target_page
        switch_page(target_page)




def _sidebar_header() -> None:
    st.html(
        """
        <div style="margin:-2rem -2rem 0 -2rem;overflow:hidden;line-height:0">
            <svg viewBox="0 0 1000 300" preserveAspectRatio="none"
                 style="display:block;width:calc(100% + 4rem);height:116px;max-width:none">
                <path d="M0,0 L1000,0 L1000,140 C820,95 680,260 460,250 C280,242 140,150 0,210 Z"
                      fill="#D2C4DC"></path>
                <path d="M0,0 L1000,0 L1000,100 C820,55 680,220 460,210 C280,202 140,110 0,170 Z"
                      fill="#724CBF" opacity="0.75"></path>
            </svg>
        </div>
        <div style="padding:12px 0 14px;border-bottom:1px solid rgba(255,255,255,.14);
                    margin:0 0 12px;font-family:Poppins,Inter,sans-serif">
            <div style="color:rgba(255,255,255,.55);font-size:0.6rem;font-weight:700;
                        letter-spacing:.1em;text-transform:uppercase;line-height:1">
                Decision Support
            </div>
            <div style="color:white;font-size:0.88rem;font-weight:700;
                        line-height:1.3;margin-top:3px">
                Neighbourhood Hub<br>Explorer
            </div>
        </div>
        """
    )


def build_config() -> AppConfig:
    with st.sidebar:
        _sidebar_header()
        st.header("Configuration")
        with st.expander("Data Sources", expanded=False):
            deprivation_csv = Path(st.text_input("Deprivation CSV", value="data/core20_lsoa_latest.csv"))
            population_csv = Path(st.text_input("Population CSV", value="data/LSOA Population.csv"))
            older_people_csv = Path(
                st.text_input("65+ population CSV", value="data/older_people/65+ Population London LSOA.csv")
            )
            neighbourhoods_path = Path(
                st.text_input("Neighbourhood polygons", value="data/older_people/neighbourhoods_shapefile.shp")
            )
            gp_geocoded_csv = Path(st.text_input("GP geocoded CSV", value="data/older_people/combined_gps_geocoded.csv"))
            pharmacy_csv = Path(st.text_input("Pharmacy source CSV", value="data/older_people/Pharmacy List.csv"))
            pharmacy_geocoded_csv = Path(
                st.text_input("Pharmacy geocoded CSV", value="data/older_people/pharmacy_geocoded.csv")
            )
            family_hub_csv = Path(st.text_input("Family hub source CSV", value="data/older_people/Family Hub Sites.csv"))
            family_hub_geocoded_csv = Path(
                st.text_input("Family hub geocoded CSV", value="data/older_people/family_hub_geocoded.csv")
            )
            lsoa_source = st.selectbox(
                "LSOA boundary source",
                options=["live_arcgis", "local_file"],
                format_func=lambda value: "Live ArcGIS service" if value == "live_arcgis" else "Local file",
            )
            local_lsoa_raw = st.text_input("Local LSOA boundary file", value="")
            postcode_lsoa_lookup_raw = st.text_input("Postcode to LSOA lookup", value="data/london_postcode_to_lsoa.csv")
            postcode_source = st.selectbox(
                "Candidate postcode coordinate source",
                options=["postcodes_io", "local_lookup", "none"],
                format_func=lambda value: {
                    "none": "Not configured",
                    "postcodes_io": "Postcodes.io API",
                    "local_lookup": "Local coordinate lookup file",
                }[value],
            )
            postcode_lookup_raw = st.text_input("Local postcode coordinate lookup file", value="")
            postcode_api_base_url = st.text_input(
                "Postcodes.io base URL",
                value="https://api.postcodes.io/postcodes",
                disabled=postcode_source != "postcodes_io",
            )
        with st.expander("Optional Data Sources", expanded=False):
            qof_lsoa_raw = st.text_input(
                "QOF LSOA prevalence CSV (optional)",
                value="",
                help=(
                    "Path to the QOF LSOA-level prevalence cache generated by "
                    "scripts/analysis/build_qof_lsoa.py. "
                    "Required columns: LSOA_code, qof_chd_prevalence, qof_copd_prevalence, "
                    "qof_diabetes_prevalence, qof_depression_prevalence. "
                    "Leave blank to disable QOF disease indices."
                ),
            )
            ethnicity_lsoa_raw = st.text_input(
                "Ethnicity LSOA proportions CSV (optional)",
                value="",
                help=(
                    "Path to the Census 2021 ethnicity proportions cache generated by "
                    "scripts/analysis/build_ethnicity_lsoa.py. "
                    "Required columns: LSOA_code, pct_asian_residents, pct_black_residents, "
                    "pct_mixed_residents, pct_other_ethnic_group_residents, pct_white_other_residents. "
                    "Leave blank to disable ethnicity equity indices."
                ),
            )
            walking_matrix_raw = st.text_input(
                "Walking travel-time matrix parquet (optional)",
                value="",
                help=(
                    "Path to the pre-computed LSOA walking travel-time matrix generated by "
                    "scripts/analysis/build_travel_time_matrix.py --mode walking. "
                    "Required columns: origin_lsoa, destination_lsoa, travel_time_minutes. "
                    "Leave blank to use straight-line distance."
                ),
            )
            transit_matrix_raw = st.text_input(
                "Transit travel-time matrix parquet (optional)",
                value="",
                help=(
                    "Path to the pre-computed LSOA public transport travel-time matrix generated by "
                    "the R5 Docker container in scripts/analysis/r5/. "
                    "Required columns: origin_lsoa, destination_lsoa, travel_time_minutes. "
                    "Leave blank to use straight-line distance."
                ),
            )
            eric_geocoded_raw = st.text_input(
                "ERIC estate sites geocoded CSV (optional)",
                value="",
                help=(
                    "Path to the ERIC 2024/25 geocoded NHS estate sites generated by "
                    "scripts/analysis/build_eric_geocoded.py. "
                    "Required columns: site_name, latitude, longitude. "
                    "Leave blank to disable estate proximity flags."
                ),
            )
            estate_search_radius_m = st.slider(
                "Estate proximity search radius",
                min_value=500,
                max_value=2000,
                value=1000,
                step=100,
                format="%d m",
                disabled=not eric_geocoded_raw.strip(),
                help="Candidates within this radius of an NHS estate site are flagged as having nearby estate.",
            )

    return AppConfig(
        deprivation_csv=deprivation_csv,
        population_csv=population_csv,
        older_people_csv=older_people_csv,
        gp_geocoded_csv=gp_geocoded_csv,
        pharmacy_csv=pharmacy_csv,
        pharmacy_geocoded_csv=pharmacy_geocoded_csv,
        family_hub_csv=family_hub_csv,
        family_hub_geocoded_csv=family_hub_geocoded_csv,
        neighbourhoods_path=neighbourhoods_path,
        lsoa_source=lsoa_source,
        local_lsoa_path=Path(local_lsoa_raw) if local_lsoa_raw.strip() else None,
        postcode_lsoa_lookup_csv=Path(postcode_lsoa_lookup_raw),
        postcode_source=postcode_source,
        postcode_coordinate_lookup_csv=Path(postcode_lookup_raw) if postcode_lookup_raw.strip() else None,
        postcode_api_base_url=postcode_api_base_url,
        qof_lsoa_csv=Path(qof_lsoa_raw) if qof_lsoa_raw.strip() else None,
        ethnicity_lsoa_csv=Path(ethnicity_lsoa_raw) if ethnicity_lsoa_raw.strip() else None,
        walking_matrix_path=Path(walking_matrix_raw) if walking_matrix_raw.strip() else None,
        transit_matrix_path=Path(transit_matrix_raw) if transit_matrix_raw.strip() else None,
        eric_geocoded_csv=Path(eric_geocoded_raw) if eric_geocoded_raw.strip() else None,
        estate_search_radius_m=int(estate_search_radius_m),
    )


@st.cache_data(show_spinner=False)
def build_validation_report(config: AppConfig) -> ValidationReport:
    return validate_config(config)


@st.cache_data(show_spinner=False)
def build_inventory_summary(_config: AppConfig) -> dict[str, int]:
    try:
        return load_asset_counts()
    except Exception:
        return {"gp_practices": 0, "community_pharmacies": 0, "family_hubs": 0}


def render_validation_panel(report: ValidationReport) -> None:
    if report.blocking_issues:
        st.error("Required inputs are missing for the full hub-ranking workflow.")
        for issue in report.blocking_issues:
            st.write(f"- {issue.message} {issue.remediation}")
    if report.warnings:
        st.warning("External dependencies or non-local data sources are configured.")
        for issue in report.warnings:
            st.write(f"- {issue.message} {issue.remediation}")


def render_source_table(report: ValidationReport) -> None:
    source_frame = pd.DataFrame(
        [
            {
                "Source": source.label,
                "Path": source.path,
                "Exists": "Yes" if source.exists else "No",
                "Updated": source.updated_at,
                "Used for": source.required_for,
            }
            for source in report.sources
        ]
    )
    st.dataframe(source_frame, use_container_width=True, hide_index=True)


def render_audit_metrics(report: ValidationReport, inventory: dict[str, int]) -> None:
    total_assets = report.asset_count if report.asset_count is not None else sum(inventory.values())
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Indexed LSOAs", f"{report.index_lsoa_count or 0:,}")
    col2.metric("Assets", f"{total_assets:,}")
    col3.metric("GP practices", f"{inventory.get('gp_practices', 0):,}")
    combined_other_assets = inventory.get("community_pharmacies", 0) + inventory.get("family_hubs", 0)
    col4.metric("Pharmacies + family hubs", f"{combined_other_assets:,}")


def render_intro_page(report: ValidationReport, inventory: dict[str, int], current_page: str) -> None:
    st.markdown(
        """
<div class="intro-hero">
    <div class="intro-hero-eyebrow">NHS · ICB Decision Support</div>
    <div class="intro-hero-title">Neighbourhood Hub<br>Decision Explorer</div>
    <div class="intro-hero-subtitle">
        Rank candidate hub locations against population need across London.
        Compare sites using transparent, proximity-weighted scoring and
        export a full audit trail for every run.
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    cta_col1, cta_col2, _ = st.columns([1.4, 1.7, 3], gap="small")
    with cta_col1:
        if st.button("Get started →", key="intro_get_started", type="primary", use_container_width=True):
            switch_page("Configure Inputs")
    with cta_col2:
        if st.button("View methodology", key="intro_view_methodology", use_container_width=True):
            switch_page("Methodology")

    st.markdown('<div class="intro-section-label">How it works</div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="intro-steps-grid">
    <div class="intro-step">
        <div class="intro-step-num">1</div>
        <div class="intro-step-title">Configure your scope</div>
        <div class="intro-step-body">
            Choose an ICB or all of London. Select focus neighbourhoods and
            set need index weights that reflect your local priorities.
        </div>
    </div>
    <div class="intro-step">
        <div class="intro-step-num">2</div>
        <div class="intro-step-title">Score candidate locations</div>
        <div class="intro-step-body">
            Each LSOA is scored using deprivation, population, and other need indices.
            Candidate postcodes are ranked by nearby demand within a configurable catchment radius.
        </div>
    </div>
    <div class="intro-step">
        <div class="intro-step-num">3</div>
        <div class="intro-step-title">Review and export results</div>
        <div class="intro-step-body">
            Explore the choropleth map and ranked hub table. Download results
            with a full scoring audit trail for reporting and further analysis.
        </div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="intro-section-label">Scoring model</div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="intro-scoring-grid">
    <div class="intro-scoring-copy">
        Need scores are computed per LSOA by min-max scaling each selected index within
        the chosen geography, then applying user-defined weights summing to 100.
        Hub scores combine the need at the candidate site's own LSOA with a
        distance-weighted mean of surrounding LSOA need within the catchment radius.
        The balance between local and catchment need is controlled by a single slider.
    </div>
    <div class="intro-formula-block">
Hub Score =<br>
&nbsp;&nbsp;(host_lsoa_weight × host LSOA need score)<br>
+ (catchment_weight × distance-weighted mean<br>
&nbsp;&nbsp;&nbsp;need within catchment radius)
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="intro-callout">
    <strong>Important:</strong> Outputs are decision-support only. They do not replace local service planning,
    estate checks, or clinical judgement. Scores are scope-relative — results are not directly comparable
    across runs with different geographies or index weights.
</div>
        """,
        unsafe_allow_html=True,
    )


def selected_indices_controls(config: AppConfig) -> tuple[list[str], dict[str, float], float]:
    _INDEX_GUIDANCE: dict[str, str] = {
        "deprivation_inverse": (
            "Measures socioeconomic disadvantage using the Index of Multiple Deprivation (IMD). "
            "Higher values represent greater deprivation — targets communities with the most barriers to accessing services."
        ),
        "population": (
            "Total resident population of the area. Prioritises high-density neighbourhoods "
            "where a hub would serve the most people."
        ),
        "population_65_plus": (
            "Count of residents aged 65 and over. Reflects demand for services typically used by older populations, "
            "including preventive health, social care, and community support."
        ),
    }
    _DEFAULT_ENABLED = {"deprivation_inverse", "population", "population_65_plus"}
    _DEFAULT_WEIGHTS = {"deprivation_inverse": 40, "population": 35, "population_65_plus": 25}

    _QOF_UNAVAILABLE_TOOLTIP = (
        "Enable by supplying a QOF LSOA prevalence CSV in Optional Data Sources. "
        "Generate it with scripts/analysis/build_qof_lsoa.py."
    )
    _ETHNICITY_UNAVAILABLE_TOOLTIP = (
        "Enable by supplying an ethnicity LSOA proportions CSV in Optional Data Sources. "
        "Generate it with scripts/analysis/build_ethnicity_lsoa.py."
    )

    _ethnicity_entries = [name for name, defn in INDEX_DEFINITIONS.items() if defn.get("available_when") == "ethnicity"]
    _ethnicity_available = config.ethnicity_lsoa_csv is not None
    if _ethnicity_entries and _ethnicity_available:
        st.info(
            "**Ethnicity indices (Census 2021)** are an equity lens — they show where specific communities "
            "are concentrated, not where deprivation is highest. Select only those relevant to your "
            "planning question and weight them alongside deprivation and population indicators.",
            icon="ℹ️",
        )

    selected_indices: list[str] = []
    weights: dict[str, float] = {}

    for i, (index_name, defn) in enumerate(INDEX_DEFINITIONS.items()):
        available_when = defn.get("available_when")
        qof_unavailable = available_when == "qof" and config.qof_lsoa_csv is None
        ethnicity_unavailable = available_when == "ethnicity" and not _ethnicity_available

        if i > 0:
            st.markdown(
                '<div style="border-top:1px solid #EAE3F0;margin:2px 0 6px"></div>',
                unsafe_allow_html=True,
            )
        label_col, weight_col = st.columns([6, 4])
        unavailable = qof_unavailable or ethnicity_unavailable
        if unavailable:
            unavailable_tooltip = _QOF_UNAVAILABLE_TOOLTIP if qof_unavailable else _ETHNICITY_UNAVAILABLE_TOOLTIP
            unavailable_note = (
                "_Requires QOF LSOA CSV — configure in Optional Data Sources._"
                if qof_unavailable
                else "_Requires ethnicity LSOA CSV — configure in Optional Data Sources._"
            )
        enabled = False

        with label_col:
            if unavailable:
                st.checkbox(
                    defn["label"],
                    value=False,
                    disabled=True,
                    help=unavailable_tooltip,
                    key=f"idx_disabled_{index_name}",
                )
                st.caption(
                    _INDEX_GUIDANCE.get(index_name, defn.get("description", ""))
                    + f"  \n{unavailable_note}"
                )
            else:
                enabled_key = prepare_persisted_widget(
                    f"idx_enabled_{index_name}",
                    index_name in _DEFAULT_ENABLED,
                    normalize=lambda value: bool(value),
                )
                enabled = st.checkbox(
                    defn["label"],
                    key=enabled_key,
                )
                remember_persisted_widget(f"idx_enabled_{index_name}")
                st.caption(_INDEX_GUIDANCE.get(index_name, defn.get("description", "")))
        with weight_col:
            if unavailable:
                st.markdown(
                    '<div style="color:#9E9099;font-size:0.75rem;margin-top:0.4rem">Not available — data not configured</div>',
                    unsafe_allow_html=True,
                )
            elif enabled:
                weight_key = prepare_persisted_widget(
                    f"weight_{index_name}",
                    _DEFAULT_WEIGHTS.get(index_name, 0),
                    normalize=lambda value: int(value),
                )
                weight = float(
                    st.slider(
                        "Weight",
                        min_value=0,
                        max_value=100,
                        step=5,
                        key=weight_key,
                        format="%d%%",
                        label_visibility="collapsed",
                    )
                )
                remember_persisted_widget(f"weight_{index_name}")
                selected_indices.append(index_name)
                weights[index_name] = weight
            else:
                st.markdown(
                    '<div style="color:#9E9099;font-size:0.75rem;margin-top:0.4rem">Not included in scoring</div>',
                    unsafe_allow_html=True,
                )

    total_weight = sum(weights.values())

    st.markdown(
        '<div style="border-top:1px solid #EAE3F0;margin:8px 0 4px"></div>',
        unsafe_allow_html=True,
    )
    if total_weight == 100:
        total_color, total_suffix = "#1a7a3f", "Ready to run ✓"
    elif total_weight > 100:
        total_color, total_suffix = "#350355", f"Over by {int(total_weight - 100)} — reduce weights to continue"
    else:
        total_color, total_suffix = "#490E6F", f"{int(100 - total_weight)} remaining — allocate all 100 points to continue"
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0">'
        f'<span style="font-size:0.78rem;color:{total_color}">{total_suffix}</span>'
        f'<span style="font-size:1rem;font-weight:700;color:{total_color}">{int(total_weight)} / 100</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    return selected_indices, weights, total_weight


def hub_score_weight_controls() -> tuple[dict[str, float], float]:
    st.caption(
        "A hub's score is built from two components. "
        "The site area is the neighbourhood the candidate location sits directly within. "
        "The surrounding catchment is the distance-weighted average need of all areas within the catchment radius — "
        "nearby areas count more than distant ones."
    )
    left_col, right_col = st.columns(2)
    left_col.markdown(
        '<div style="font-size:0.74rem;color:#6B6078;margin-bottom:-12px">← Weight the site\'s own area more</div>',
        unsafe_allow_html=True,
    )
    right_col.markdown(
        '<div style="text-align:right;font-size:0.74rem;color:#6B6078;margin-bottom:-12px">Weight the surrounding catchment more →</div>',
        unsafe_allow_html=True,
    )
    balance_key = prepare_persisted_widget(
        "hub_weight_balance",
        int(DEFAULT_HUB_SCORE_WEIGHTS["host_lsoa"]),
        normalize=lambda value: int(value),
    )
    balance = st.slider(
        "Scoring balance",
        min_value=0,
        max_value=100,
        step=5,
        key=balance_key,
        label_visibility="collapsed",
    )
    remember_persisted_widget("hub_weight_balance")
    host_lsoa_weight = balance
    catchment_weight = 100 - balance
    st.markdown(
        f'<div style="margin-top:8px">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        f'<span style="min-width:140px;font-size:0.74rem;color:#6B6078">Site area</span>'
        f'<div style="flex:1;height:8px;background:#EAE3F0;border-radius:4px;overflow:hidden">'
        f'<div style="width:{host_lsoa_weight}%;height:100%;background:#490E6F;border-radius:4px"></div>'
        f'</div>'
        f'<span style="min-width:32px;text-align:right;font-size:0.8rem;font-weight:600;color:#0D0517">{host_lsoa_weight}%</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:10px">'
        f'<span style="min-width:140px;font-size:0.74rem;color:#6B6078">Surrounding catchment</span>'
        f'<div style="flex:1;height:8px;background:#EAE3F0;border-radius:4px;overflow:hidden">'
        f'<div style="width:{catchment_weight}%;height:100%;background:#9576FF;border-radius:4px"></div>'
        f'</div>'
        f'<span style="min-width:32px;text-align:right;font-size:0.8rem;font-weight:600;color:#0D0517">{catchment_weight}%</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    return {"host_lsoa": float(host_lsoa_weight), "catchment": float(catchment_weight)}, 100.0


def catchment_radius_control() -> float:
    st.caption(
        "The furthest distance from a candidate site that contributes to its hub score. "
        "Areas within this radius are included and weighted by proximity — nearer areas count more. "
        "A smaller radius focuses on immediate local need; a larger radius captures broader neighbourhood demand."
    )
    radius_key = prepare_persisted_widget(
        "catchment_radius_m",
        int(DEFAULT_CATCHMENT_RADIUS_M),
        normalize=lambda value: int(value),
    )
    radius = float(
        st.slider(
            "Catchment radius",
            min_value=250,
            max_value=5000,
            step=250,
            key=radius_key,
            format="%d m",
            label_visibility="collapsed",
        )
    )
    remember_persisted_widget("catchment_radius_m")
    walk_mins = round(radius / 83)
    if radius <= 500:
        scale_hint = "immediate surroundings only"
    elif radius <= 1000:
        scale_hint = "immediate neighbourhood scale"
    elif radius <= 2000:
        scale_hint = "local neighbourhood scale"
    elif radius <= 3000:
        scale_hint = "district-wide scale"
    else:
        scale_hint = "borough-wide scale"
    st.caption(
        f"**{radius:,.0f} m** · approx. **{walk_mins} min walk** · {scale_hint} · Range: 250 m – 5,000 m"
    )
    return radius


def parse_postcodes(raw_text: str) -> list[str]:
    lines = [line.strip() for line in raw_text.replace(",", "\n").splitlines()]
    return [line for line in lines if line]


@st.cache_data(show_spinner=False)
def load_neighbourhood_frame(config: AppConfig) -> pd.DataFrame:
    neighbourhoods = load_neighbourhoods(config)
    frame = neighbourhoods.drop(columns="geometry").drop_duplicates().copy()
    frame["borough"] = frame["borough"].astype(str)
    frame["nghbrhd"] = frame["nghbrhd"].astype(str)
    frame["ICB"] = frame["ICB"].astype(str)
    return frame


@st.cache_data(show_spinner=False)
def load_neighbourhood_geojson(config: AppConfig) -> str:
    neighbourhoods = load_neighbourhoods(config).to_crs(4326)
    return neighbourhoods.to_json()


_LONDON_BBOX = [[51.28, -0.52], [51.69, 0.34]]


def build_neighbourhood_preview_map(
    config: AppConfig,
    geography_mode: str,
    icb_name: str | None,
    selected_neighbourhoods: list[str],
) -> folium.Map:
    neighbourhoods = load_neighbourhoods(config).to_crs(4326)
    if geography_mode == "Specific ICB" and icb_name:
        icb_code = ICB_CODE_BY_NAME.get(icb_name)
        neighbourhoods = neighbourhoods[neighbourhoods["ICB"].astype(str).str.strip().eq(icb_code)].copy()

    fmap = folium.Map(
        location=[51.505, -0.09],
        zoom_start=10,
        tiles="CartoDB positron",
        max_bounds=True,
        min_lat=51.1,
        max_lat=51.9,
        min_lon=-0.7,
        max_lon=0.55,
        min_zoom=8,
    )

    if neighbourhoods.empty:
        fmap.fit_bounds(_LONDON_BBOX)
        return fmap

    selected_set = set(selected_neighbourhoods)

    # Zoom to: selected neighbourhoods > ICB area > all London
    if selected_neighbourhoods:
        zoom_target = neighbourhoods[neighbourhoods["nghbrhd"].isin(selected_set)]
        if zoom_target.empty:
            zoom_target = neighbourhoods
        b = zoom_target.total_bounds
        fmap.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    elif geography_mode == "Specific ICB":
        b = neighbourhoods.total_bounds
        fmap.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    else:
        fmap.fit_bounds(_LONDON_BBOX)

    def style_function(feature: dict[str, object]) -> dict[str, object]:
        properties = feature["properties"]
        selected = properties.get("nghbrhd") in selected_set
        return {
            "fillColor": "#724CBF" if selected else "#F2EFFF",
            "color": "#490E6F" if selected else "#D2C4DC",
            "weight": 2.0 if selected else 1.0,
            "fillOpacity": 0.78 if selected else 0.35,
        }

    folium.GeoJson(
        neighbourhoods.loc[:, ["nghbrhd", "borough", "ICB", "geometry"]].to_json(),
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["nghbrhd", "borough", "ICB"],
            aliases=["Neighbourhood", "Borough", "ICB"],
            sticky=False,
        ),
    ).add_to(fmap)
    return fmap


@st.cache_data(show_spinner=False)
def geocode_single_postcode(postcode: str, config: AppConfig) -> tuple[float, float] | None:
    result = geocode_candidate_postcodes([postcode], config)
    if result.candidates.empty:
        return None
    row = result.candidates.iloc[0]
    return (float(row.geometry.y), float(row.geometry.x))


def build_catchment_preview_map(lat: float, lon: float, radius_m: float) -> folium.Map:
    zoom = 16 if radius_m <= 300 else 15 if radius_m <= 600 else 14 if radius_m <= 1200 else 13 if radius_m <= 2000 else 12
    fmap = folium.Map(location=[lat, lon], zoom_start=zoom, tiles="CartoDB positron")
    folium.CircleMarker(
        location=[lat, lon],
        radius=8,
        color=BRAND_PURPLE_DARK,
        fill=True,
        fill_color=BRAND_PURPLE,
        fill_opacity=0.9,
        tooltip="Candidate location",
    ).add_to(fmap)
    folium.Circle(
        location=[lat, lon],
        radius=radius_m,
        color=BRAND_PURPLE,
        weight=2,
        fill=True,
        fill_color=BRAND_PURPLE,
        fill_opacity=0.12,
        tooltip=f"Catchment radius: {radius_m:,.0f} m",
    ).add_to(fmap)
    return fmap


@st.cache_data(show_spinner=False)
def load_asset_overlay_frame(asset_name: str) -> pd.DataFrame:
    overlay = ASSET_OVERLAY_STYLES[asset_name]["loader"]()
    overlay = overlay.to_crs(4326)
    label_column = None
    for candidate in ["Practice Name", "SiteName", "Family_Hub", "Trust Name", "Postcode", "hub_name"]:
        if candidate in overlay.columns:
            label_column = candidate
            break
    if label_column is None:
        labels = pd.Series([asset_name] * len(overlay))
    else:
        labels = overlay[label_column].astype(str)
    frame = pd.DataFrame(
        {
            "asset_name": asset_name,
            "label": labels,
            "latitude": overlay.geometry.y,
            "longitude": overlay.geometry.x,
        }
    )
    return frame.dropna(subset=["latitude", "longitude"])


@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def load_parks_and_gardens_overlay(bounds: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    parks = arcgis_query_to_gdf(
        PARKS_GARDENS_FS_BASE,
        out_fields="ListEntry,Name,Grade,RegDate,AmendDate,hyperlink,area_ha",
        out_sr=4326,
        geometry=bounds,
    )
    if parks.empty:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    if parks.crs is None:
        return parks.set_crs(4326)
    return parks.to_crs(4326)


def add_point_asset_overlay(
    fmap: folium.Map,
    asset_name: str,
    scope_union: object,
) -> None:
    style = ASSET_OVERLAY_STYLES[asset_name]
    asset_points = load_asset_overlay_frame(asset_name)
    if asset_points.empty:
        return
    asset_points = gpd.GeoDataFrame(
        asset_points,
        geometry=gpd.points_from_xy(asset_points["longitude"], asset_points["latitude"]),
        crs=4326,
    )
    asset_points = asset_points[asset_points.intersects(scope_union)].copy()
    if asset_points.empty:
        return
    layer = folium.FeatureGroup(name=asset_name, show=True)
    for _, row in asset_points.iterrows():
        loc = [float(row.geometry.y), float(row.geometry.x)]
        tip = f"{asset_name}: {row['label']}"
        if style.get("marker_style") == "triangle":
            folium.Marker(
                location=loc,
                icon=folium.DivIcon(
                    html=(
                        f'<div style="width:0;height:0;'
                        f'border-left:6px solid transparent;'
                        f'border-right:6px solid transparent;'
                        f'border-bottom:11px solid {style["color"]};'
                        f'filter:drop-shadow(0 1px 2px rgba(0,0,0,0.4))"></div>'
                    ),
                    icon_size=(12, 11),
                    icon_anchor=(6, 11),
                ),
                tooltip=tip,
            ).add_to(layer)
        else:
            folium.CircleMarker(
                location=loc,
                radius=style["radius"],
                color=style["color"],
                weight=1,
                fill=True,
                fill_color=style["color"],
                fill_opacity=0.85,
                tooltip=tip,
            ).add_to(layer)
    layer.add_to(fmap)


def add_parks_and_gardens_overlay(
    fmap: folium.Map,
    scope_union: object,
    bounds: tuple[float, float, float, float],
) -> None:
    style = ASSET_OVERLAY_STYLES[PARKS_AND_GARDENS_OVERLAY]
    parks = load_parks_and_gardens_overlay(bounds)
    if parks.empty:
        return
    parks = parks[parks.intersects(scope_union)].copy()
    if parks.empty:
        return
    parks["geometry"] = parks.geometry.intersection(scope_union)
    parks = parks[parks.geometry.notna() & (~parks.geometry.is_empty)].copy()
    if parks.empty:
        return

    tooltip_fields = [field for field in ["Name", "Grade", "ListEntry", "area_ha"] if field in parks.columns]
    tooltip_aliases = {
        "Name": "Name",
        "Grade": "Grade",
        "ListEntry": "NHLE entry",
        "area_ha": "Area (ha)",
    }
    folium.GeoJson(
        parks.loc[:, [*tooltip_fields, "geometry"]].to_json(),
        name=PARKS_AND_GARDENS_OVERLAY,
        style_function=lambda _: {
            "fillColor": style["fill_color"],
            "color": style["color"],
            "weight": style["weight"],
            "fillOpacity": style["fill_opacity"],
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=[tooltip_aliases[field] for field in tooltip_fields],
            sticky=False,
        )
        if tooltip_fields
        else None,
    ).add_to(fmap)


def add_asset_overlays(
    fmap: folium.Map,
    result: AnalysisResult,
    selected_overlays: list[str],
) -> folium.Map:
    if not selected_overlays:
        return fmap

    scope_union = result.need_scores.to_crs(4326).union_all()
    bounds = tuple(round(float(value), 6) for value in result.need_scores.to_crs(4326).total_bounds)
    for asset_name in selected_overlays:
        style = ASSET_OVERLAY_STYLES.get(asset_name)
        if style is None:
            continue
        try:
            if style["geometry_type"] == "polygon":
                add_parks_and_gardens_overlay(fmap, scope_union, bounds)
            else:
                add_point_asset_overlay(fmap, asset_name, scope_union)
        except Exception as exc:
            st.warning(f"Could not load {asset_name}: {exc}")

    return fmap


def _analysis_loading_html(candidate_mode: str) -> str:
    subtitle = (
        "Scoring need indicators across all candidate areas and surfacing the highest-need locations&hellip;"
        if candidate_mode == "suggested"
        else "Geocoding your candidates and computing hub scores across the selected area&hellip;"
    )
    dots = "".join(
        f'<div class="ld" style="animation-delay:{round((i * 0.14) % 2.2, 2)}s"></div>'
        for i in range(30)
    )
    return f"""
<style>
.lw {{
  background: linear-gradient(135deg, #2A0245 0%, #490E6F 50%, #5B1A8A 100%);
  border-radius: 18px;
  padding: 40px 36px 36px;
  text-align: center;
  font-family: 'Poppins', Inter, sans-serif;
  overflow: hidden;
  position: relative;
}}
/* subtle shimmer sweep */
.lw::after {{
  content: '';
  position: absolute;
  top: -40%;
  left: -60%;
  width: 40%;
  height: 180%;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.04) 50%, transparent 60%);
  animation: sweep 3.5s ease-in-out infinite;
}}
@keyframes sweep {{
  0% {{ left: -60%; }}
  100% {{ left: 140%; }}
}}
/* dot grid */
.lg {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  width: fit-content;
  margin: 0 auto 32px;
}}
.ld {{
  width: 9px;
  height: 9px;
  background: rgba(255,255,255,0.12);
  border-radius: 50%;
  animation: dp 2.4s ease-in-out infinite;
}}
@keyframes dp {{
  0%,100% {{ background: rgba(255,255,255,0.1); transform: scale(0.65); }}
  50% {{ background: #9576FF; transform: scale(1.2); box-shadow: 0 0 7px rgba(149,118,255,0.75); }}
}}
/* pulsing rings */
.rc {{
  position: relative;
  width: 64px;
  height: 64px;
  margin: 0 auto 24px;
}}
.rr {{
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  border: 1.5px solid rgba(149,118,255,0.65);
  border-radius: 50%;
  animation: re 2.4s ease-out infinite;
}}
.rr:nth-child(1) {{ animation-delay: 0s; }}
.rr:nth-child(2) {{ animation-delay: 0.8s; }}
.rr:nth-child(3) {{ animation-delay: 1.6s; }}
@keyframes re {{
  0%  {{ width: 12px; height: 12px; opacity: 1; }}
  100% {{ width: 66px; height: 66px; opacity: 0; }}
}}
.rb {{
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  width: 12px; height: 12px;
  background: #9576FF;
  border-radius: 50%;
  animation: bp 1.8s ease-in-out infinite;
}}
@keyframes bp {{
  0%,100% {{ box-shadow: 0 0 8px rgba(149,118,255,0.6); }}
  50%      {{ box-shadow: 0 0 20px rgba(149,118,255,1.0), 0 0 40px rgba(149,118,255,0.3); }}
}}
.lt {{
  color: white;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin-bottom: 6px;
}}
.ls {{
  color: rgba(255,255,255,0.5);
  font-size: 0.75rem;
  line-height: 1.55;
  max-width: 360px;
  margin: 0 auto 20px;
}}
/* progress bar */
.pb {{
  width: 200px;
  height: 3px;
  background: rgba(255,255,255,0.1);
  border-radius: 99px;
  margin: 0 auto;
  overflow: hidden;
}}
.pf {{
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, #9576FF, #C4B0FF);
  border-radius: 99px;
  animation: slide 1.8s ease-in-out infinite;
}}
@keyframes slide {{
  0%   {{ margin-left: -40%; }}
  100% {{ margin-left: 100%; }}
}}
</style>
<div class="lw">
  <div class="lg">{dots}</div>
  <div class="rc">
    <div class="rr"></div><div class="rr"></div><div class="rr"></div>
    <div class="rb"></div>
  </div>
  <div class="lt">Building the neighbourhood picture</div>
  <div class="ls">{subtitle}</div>
  <div class="pb"><div class="pf"></div></div>
</div>
"""


def render_configure_page(config: AppConfig, report: ValidationReport) -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-brand">Analysis Setup</div>
            <div class="hero-title">Inputs</div>
            <div class="hero-subtitle">
                Define the analysis area, select candidate hub locations, and configure the need model before running the analysis.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # — Analysis area ——————————————————————————————————————————————
    st.subheader("Analysis Area")
    st.caption(
        "Choose whether to analyse all of London or a specific Integrated Care Board (ICB). "
        "Narrowing to an ICB focuses scoring entirely within that area."
    )
    scope_options = ["All London"] + list(ICB_CHOICES)
    scope_key = prepare_persisted_widget(
        "selected_scope",
        "All London",
        normalize=lambda value: value if value in scope_options else "All London",
    )
    selected_scope = st.selectbox(
        "Scope",
        options=scope_options,
        key=scope_key,
        label_visibility="collapsed",
        help="All London includes all 32 London boroughs. Each ICB option covers the associated NHS Integrated Care Board area.",
    )
    remember_persisted_widget("selected_scope")
    geography_mode = "Specific ICB" if selected_scope != "All London" else "All London"
    icb_name = selected_scope if geography_mode == "Specific ICB" else None

    # — Neighbourhood focus ————————————————————————————————————————
    st.subheader("Neighbourhood Focus")
    st.caption(
        "Optionally narrow the analysis to specific named neighbourhoods within the selected area. "
        "Leave blank to include all neighbourhoods."
    )
    neighbourhood_frame = load_neighbourhood_frame(config)
    if geography_mode == "Specific ICB" and icb_name:
        icb_code = ICB_CODE_BY_NAME.get(icb_name)
        neighbourhood_frame = neighbourhood_frame[neighbourhood_frame["ICB"].eq(icb_code)].copy()

    filter_col, select_col = st.columns(2, gap="large")
    with filter_col:
        borough_options = sorted(neighbourhood_frame["borough"].dropna().unique().tolist())
        borough_key = prepare_persisted_widget(
            "selected_boroughs",
            [],
            normalize=lambda values: [value for value in list(values or []) if value in borough_options],
        )
        selected_boroughs = st.multiselect("Filter by borough", options=borough_options, key=borough_key)
        remember_persisted_widget("selected_boroughs")
    if selected_boroughs:
        filtered_neighbourhoods = neighbourhood_frame[neighbourhood_frame["borough"].isin(selected_boroughs)].copy()
    else:
        filtered_neighbourhoods = neighbourhood_frame.copy()
    with select_col:
        neighbourhood_options = sorted(filtered_neighbourhoods["nghbrhd"].dropna().unique().tolist())
        neighbourhood_key = prepare_persisted_widget(
            "selected_neighbourhoods",
            [],
            normalize=lambda values: [value for value in list(values or []) if value in neighbourhood_options],
        )
        selected_neighbourhoods = st.multiselect(
            "Select neighbourhoods",
            options=neighbourhood_options,
            key=neighbourhood_key,
            placeholder="Leave blank to include the full selected geography",
        )
        remember_persisted_widget("selected_neighbourhoods")
    st.caption(
        f"Coverage: {len(selected_neighbourhoods)} neighbourhood(s) selected of {len(neighbourhood_options)} available"
        if selected_neighbourhoods
        else f"Coverage: all {len(neighbourhood_options)} neighbourhood(s) in the selected area"
    )

    st.subheader("Footprint preview")
    st.caption("Confirm the geographic footprint before configuring scoring.")
    preview_map = build_neighbourhood_preview_map(config, geography_mode, icb_name, selected_neighbourhoods)
    st_folium(preview_map, use_container_width=True, height=440, returned_objects=[])

    # — Candidate hub locations ————————————————————————————————————
    st.subheader("Candidate Hub Locations")
    st.caption(
        "Provide specific postcodes to rank, or let the tool suggest the highest-need locations automatically. "
        "Suggested locations are starting points only — validate against local estate, engagement, and clinical context before acting on them."
    )
    workflow_key = prepare_persisted_widget(
        "candidate_workflow",
        "Suggest locations",
        normalize=lambda value: value if value in ["Suggest locations", "Rank provided postcodes"] else "Suggest locations",
    )
    candidate_workflow = st.segmented_control(
        "Candidate workflow",
        options=["Suggest locations", "Rank provided postcodes"],
        key=workflow_key,
        label_visibility="collapsed",
    )
    remember_persisted_widget("candidate_workflow")
    candidate_mode = "suggested" if candidate_workflow == "Suggest locations" else "manual"
    candidate_postcodes: list[str] = []
    suggestion_count = DEFAULT_SUGGESTION_COUNT
    suggestion_min_spacing_m = float(DEFAULT_SUGGESTION_MIN_SPACING_M)
    suggestion_one_per_neighbourhood = True

    if candidate_mode == "manual":
        candidate_postcodes_key = prepare_persisted_widget(
            "candidate_postcodes_raw",
            "",
            normalize=lambda value: str(value or ""),
        )
        candidate_postcodes_raw = st.text_area(
            "Enter one postcode per line",
            height=140,
            key=candidate_postcodes_key,
            placeholder="E1 4DG\nSE1 2QH\nN15 4RX",
            help="Enter London postcodes, one per line or comma-separated. Each is geocoded and scored against the need model.",
        )
        remember_persisted_widget("candidate_postcodes_raw")
        candidate_postcodes = parse_postcodes(candidate_postcodes_raw)
    else:
        _suggestion_options = [3, 5, 10, 15, 20]
        sug_col, spacing_col, toggle_col = st.columns([1, 2.5, 1.5], gap="large")
        with sug_col:
            suggestion_count_key = prepare_persisted_widget(
                "suggestion_count",
                DEFAULT_SUGGESTION_COUNT,
                normalize=lambda value: int(value) if int(value) in _suggestion_options else DEFAULT_SUGGESTION_COUNT,
            )
            suggestion_count = int(
                st.selectbox(
                    "Locations",
                    options=_suggestion_options,
                    key=suggestion_count_key,
                    help="The tool scores all LSOA-centroid candidates in the selected area and returns the top N by hub score.",
                )
            )
            remember_persisted_widget("suggestion_count")
        with spacing_col:
            suggestion_spacing_key = prepare_persisted_widget(
                "suggestion_min_spacing_m",
                DEFAULT_SUGGESTION_MIN_SPACING_M,
                normalize=lambda value: int(value),
            )
            suggestion_min_spacing_m = float(
                st.slider(
                    "Min. spacing between suggestions",
                    min_value=0,
                    max_value=5000,
                    step=250,
                    key=suggestion_spacing_key,
                    format="%d m",
                    help="Prevents clustering — any two suggestions will be at least this far apart. Set to 0 to allow any spacing.",
                )
            )
            remember_persisted_widget("suggestion_min_spacing_m")
        with toggle_col:
            suggestion_toggle_key = prepare_persisted_widget(
                "suggestion_one_per_neighbourhood",
                True,
                normalize=lambda value: bool(value),
            )
            suggestion_one_per_neighbourhood = st.toggle(
                "One per neighbourhood",
                key=suggestion_toggle_key,
                help=(
                    "When enabled, no two suggestions will fall within the same named neighbourhood. "
                    "This spreads coverage more evenly across the area rather than clustering results in one high-need zone."
                ),
            )
            remember_persisted_widget("suggestion_one_per_neighbourhood")

    # — Need model —————————————————————————————————————————————————
    st.subheader("Need Model")
    st.caption(
        "Select which indicators to include and set their weighting. "
        "Weights must sum to exactly 100. Each indicator is min-max scaled within the selected geography before weighting."
    )
    selected_indices, weights, total_weight = selected_indices_controls(config)

    # — Hub scoring ————————————————————————————————————————————————
    st.subheader("Hub Scoring")
    hub_score_weights, _ = hub_score_weight_controls()

    # — Travel access mode ————————————————————————————————————————
    st.subheader("Travel Access Mode")
    st.caption(
        "Choose how catchment areas are defined. "
        "Walking and transit modes use pre-computed travel-time matrices and replace the straight-line radius."
    )
    _walking_available = config.walking_matrix_path is not None
    _transit_available = config.transit_matrix_path is not None
    _travel_mode_options = ["straight_line", "walking", "transit"]
    _travel_mode_labels = {
        "straight_line": "Straight-line radius (default)",
        "walking": "Walking travel time (OSRM)",
        "transit": "Public transport travel time (R5 / TfL GTFS)",
    }
    travel_mode_key = prepare_persisted_widget(
        "travel_mode",
        "straight_line",
        normalize=lambda value: value if value in _travel_mode_options else "straight_line",
    )
    _saved_travel_mode = st.session_state.get(travel_mode_key, "straight_line")
    if _saved_travel_mode == "walking" and not _walking_available:
        st.session_state[travel_mode_key] = "straight_line"
    if _saved_travel_mode == "transit" and not _transit_available:
        st.session_state[travel_mode_key] = "straight_line"
    travel_mode = st.radio(
        "Travel access mode",
        options=_travel_mode_options,
        format_func=lambda v: _travel_mode_labels[v],
        key=travel_mode_key,
        label_visibility="collapsed",
        help=(
            "Walking and transit options require pre-computed travel-time matrices. "
            "Run the batch scripts and set the matrix paths in Settings to enable them."
        ),
    )
    remember_persisted_widget("travel_mode")
    if not _walking_available and travel_mode == "walking":
        travel_mode = "straight_line"
        st.caption(":grey[Walking matrix not configured — configure the path in Settings to enable.]")
    elif not _transit_available and travel_mode == "transit":
        travel_mode = "straight_line"
        st.caption(":grey[Transit matrix not configured — configure the path in Settings to enable.]")
    config = dataclasses.replace(config, travel_mode=travel_mode)

    # — Catchment radius (straight-line only) —————————————————————
    catchment_radius_m = float(DEFAULT_CATCHMENT_RADIUS_M)
    if travel_mode == "straight_line":
        st.subheader("Catchment Radius")
        catchment_radius_m = catchment_radius_control()

    # — Catchment preview (manual mode only, straight-line only) ——
    if candidate_mode == "manual" and candidate_postcodes and travel_mode == "straight_line":
        st.markdown("#### Catchment preview")
        st.caption("Select a candidate postcode to visualise how the catchment radius looks on the map.")
        preview_key = prepare_persisted_widget(
            "catchment_preview_postcode",
            candidate_postcodes[0],
            normalize=lambda value: value if value in candidate_postcodes else candidate_postcodes[0],
        )
        preview_postcode = st.selectbox(
            "Preview postcode",
            options=candidate_postcodes,
            key=preview_key,
            label_visibility="collapsed",
        )
        remember_persisted_widget("catchment_preview_postcode")
        if preview_postcode:
            coords = geocode_single_postcode(preview_postcode, config)
            if coords:
                lat, lon = coords
                preview_map = build_catchment_preview_map(lat, lon, catchment_radius_m)
                st_folium(preview_map, use_container_width=True, height=420, returned_objects=[])
            else:
                st.caption(f"Could not geocode {preview_postcode} — check that the postcode is valid.")

    # — Validation and run —————————————————————————————————————————
    report_can_run = report.can_run_analysis if candidate_mode == "manual" else report.can_run_candidate_discovery
    can_run = (
        bool(selected_indices)
        and total_weight == 100
        and report_can_run
        and (candidate_mode == "suggested" or bool(candidate_postcodes))
    )
    if total_weight != 100:
        st.error("Weights must sum to 100 before analysis can run.")
    if not selected_indices:
        st.error("Select at least one index.")
    if candidate_mode == "manual" and not candidate_postcodes:
        st.error("Enter at least one candidate postcode.")
    if not report_can_run:
        st.error("Fix the blocking input issues shown on the Introduction page before running analysis.")

    loading_ph = st.empty()

    if st.button("Run analysis", type="primary", disabled=not can_run, use_container_width=True):
        try:
            loading_ph.html(_analysis_loading_html(candidate_mode))
            result = run_analysis(
                config=config,
                geography_mode=geography_mode,
                icb_name=icb_name,
                index_weights=weights,
                hub_score_weights=hub_score_weights,
                catchment_radius_m=catchment_radius_m,
                candidate_postcodes=candidate_postcodes,
                selected_neighbourhoods=selected_neighbourhoods,
                candidate_mode=candidate_mode,
                suggestion_count=suggestion_count,
                suggestion_min_spacing_m=suggestion_min_spacing_m,
                suggestion_one_per_neighbourhood=suggestion_one_per_neighbourhood,
            )
            loading_ph.empty()
            st.session_state["analysis_result"] = result
            st.query_params["page"] = "Outputs"
            st.rerun()
        except Exception as exc:
            loading_ph.empty()
            st.session_state.pop("analysis_result", None)
            st.error(str(exc))


_BAND_FILL = {
    "inner": "#22c55e",
    "middle": "#f59e0b",
    "outer": "#ef4444",
    "beyond": "#9ca3af",
}
_BAND_LABEL = {
    "inner": "Inner (0–10 min)",
    "middle": "Middle (10–20 min)",
    "outer": "Outer (20–30 min)",
    "beyond": "Beyond 30 min / no route",
}


def build_output_map(result: AnalysisResult, selected_overlays: list[str] | None = None) -> folium.Map:
    need_scores = result.need_scores.to_crs(4326)
    candidates = result.candidate_scores.to_crs(4326)
    valid_need_scores = need_scores[need_scores.geometry.notna() & (~need_scores.geometry.is_empty)].copy()
    valid_candidates = candidates[candidates.geometry.notna() & (~candidates.geometry.is_empty)].copy()

    travel_band_mode = "travel_time_band" in valid_need_scores.columns

    if valid_need_scores.empty:
        return folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles="CartoDB positron")

    centre_geom = valid_need_scores.to_crs(27700).union_all().centroid
    centre_geom = pd.Series([centre_geom], dtype="object")
    centre = gpd.GeoSeries(centre_geom, crs=27700).to_crs(4326).iloc[0]
    fmap = folium.Map(location=[float(centre.y), float(centre.x)], zoom_start=10, tiles="CartoDB positron")

    if travel_band_mode:
        valid_need_scores["_band_fill"] = valid_need_scores["travel_time_band"].map(
            lambda b: _BAND_FILL.get(str(b), _BAND_FILL["beyond"])
        )
        valid_need_scores["_band_label"] = valid_need_scores["travel_time_band"].map(
            lambda b: _BAND_LABEL.get(str(b), _BAND_LABEL["beyond"])
        )
        folium.GeoJson(
            valid_need_scores.loc[
                :, ["LSOA_code", "need_score_pct", "travel_time_band", "_band_fill", "_band_label", "geometry"]
            ].to_json(),
            style_function=lambda feature: {
                "fillColor": feature["properties"]["_band_fill"] or _BAND_FILL["beyond"],
                "color": "#666666",
                "weight": 0.3,
                "fillOpacity": 0.65,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["LSOA_code", "_band_label", "need_score_pct"],
                aliases=["LSOA", "Travel time band", "Need Score"],
                localize=True,
            ),
        ).add_to(fmap)
        legend_html = (
            '<div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:#fff;'
            'padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.18);font-family:sans-serif;font-size:13px">'
            "<b>Travel time from hub</b><br>"
            + "".join(
                f'<span style="display:inline-block;width:14px;height:14px;background:{color};'
                f'border-radius:3px;margin-right:6px;vertical-align:middle"></span>{label}<br>'
                for color, label in [
                    (_BAND_FILL["inner"], _BAND_LABEL["inner"]),
                    (_BAND_FILL["middle"], _BAND_LABEL["middle"]),
                    (_BAND_FILL["outer"], _BAND_LABEL["outer"]),
                    (_BAND_FILL["beyond"], _BAND_LABEL["beyond"]),
                ]
            )
            + "</div>"
        )
        fmap.get_root().html.add_child(folium.Element(legend_html))
    else:
        colormap = linear.YlOrRd_09.scale(
            float(valid_need_scores["need_score_pct"].min()),
            float(valid_need_scores["need_score_pct"].max()),
        )
        colormap.caption = "Need Score"
        colormap.add_to(fmap)
        folium.GeoJson(
            valid_need_scores.loc[:, ["LSOA_code", "need_score_pct", "geometry"]].to_json(),
            style_function=lambda feature: {
                "fillColor": colormap(feature["properties"]["need_score_pct"])
                if feature["properties"]["need_score_pct"] is not None
                else "#cccccc",
                "color": "#666666",
                "weight": 0.3,
                "fillOpacity": 0.7 if feature["properties"]["need_score_pct"] is not None else 0.0,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["LSOA_code", "need_score_pct"],
                aliases=["LSOA", "Need Score"],
                localize=True,
            ),
        ).add_to(fmap)

    if "nghbrhd" in valid_need_scores.columns:
        neighbourhood_boundaries = (
            valid_need_scores[valid_need_scores["nghbrhd"].notna()]
            .dissolve(by="nghbrhd")
            .reset_index()[["nghbrhd", "geometry"]]
        )
        if not neighbourhood_boundaries.empty:
            folium.GeoJson(
                neighbourhood_boundaries.to_json(),
                name="Neighbourhood boundaries",
                style_function=lambda _: {
                    "fillColor": "none",
                    "color": "#490E6F",
                    "weight": 0.8,
                    "fillOpacity": 0,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["nghbrhd"],
                    aliases=["Neighbourhood"],
                    sticky=False,
                ),
            ).add_to(fmap)

    for _, row in valid_candidates.iterrows():
        hub_score_pct = pd.to_numeric(pd.Series([row.get("hub_score_pct")]), errors="coerce").iloc[0]
        hub_score_label = f"{hub_score_pct:.1f}" if pd.notna(hub_score_pct) else "N/A"
        catchment_radius_val = pd.to_numeric(pd.Series([row.get("catchment_radius_m")]), errors="coerce").iloc[0]
        candidate_source = row.get("candidate_source", "Candidate postcode")
        rank_val = int(row["rank"]) if pd.notna(row.get("rank")) else 999
        estate_flag = row.get("nearby_nhs_estate_flag")
        estate_line = ""
        if estate_flag is True:
            nearest_name = row.get("nearest_estate_name") or ""
            nearest_dist = row.get("nearest_estate_distance_m")
            dist_str = f" ({nearest_dist:.0f} m)" if nearest_dist is not None else ""
            estate_line = f"<br>NHS estate nearby: {nearest_name}{dist_str}"
        elif estate_flag is False:
            estate_line = "<br>No NHS estate within search radius"
        popup = folium.Popup(
            html=(
                f"<strong>#{rank_val} — {row['postcode']}</strong><br>"
                f"{candidate_source}<br>"
                f"Hub Score: {hub_score_label}<br>"
                f"Host LSOA: {row['LSOA_code']}"
                f"{estate_line}"
            ),
            max_width=300,
        )
        if not travel_band_mode and pd.notna(catchment_radius_val) and catchment_radius_val > 0:
            folium.Circle(
                location=[row.geometry.y, row.geometry.x],
                radius=float(catchment_radius_val),
                color="#724CBF",
                weight=1,
                fill=True,
                fill_color="#9576FF",
                fill_opacity=0.07,
                opacity=0.35,
            ).add_to(fmap)
        if rank_val == 1:
            bg, border, sz = "#D97706", "#B45309", 28
        elif rank_val <= 3:
            bg, border, sz = "#EA580C", "#C2410C", 26
        elif rank_val <= 5:
            bg, border, sz = "#7C3AED", "#6D28D9", 24
        else:
            bg, border, sz = "#490E6F", "#350355", 22
        font_size = "11px" if rank_val == 1 else "10px"
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=folium.DivIcon(
                html=(
                    f'<div style="width:{sz}px;height:{sz}px;background:{bg};border:2.5px solid {border};'
                    f'border-radius:50%;display:flex;align-items:center;justify-content:center;'
                    f'color:#fff;font-family:Inter,system-ui,sans-serif;font-weight:700;font-size:{font_size};'
                    f'box-shadow:0 2px 8px rgba(0,0,0,0.35);line-height:1">{rank_val}</div>'
                ),
                icon_size=(sz, sz),
                icon_anchor=(sz // 2, sz // 2),
            ),
            popup=popup,
            tooltip=f"#{rank_val} · {row['postcode']} · Score: {hub_score_label}",
        ).add_to(fmap)

    fmap = add_asset_overlays(fmap, result, selected_overlays or [])
    return fmap


def render_outputs_page() -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-brand">Analysis Results</div>
            <div class="hero-title">Outputs</div>
            <div class="hero-subtitle">
                Ranked hub locations plotted against population need. Toggle overlays below to layer existing services onto the map.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    result: AnalysisResult | None = st.session_state.get("analysis_result")
    if result is None:
        st.info("Run an analysis from the Configure Inputs page first.")
        return

    if result.invalid_postcodes:
        st.warning(f"Invalid or ungeocoded postcodes: {', '.join(result.invalid_postcodes)}")
    if result.unresolved_postcodes:
        st.warning(f"Postcodes that could not be assigned to an LSOA: {', '.join(result.unresolved_postcodes)}")
    if result.metadata.get("lsoa_count", 0) == 0:
        st.error("No LSOAs were analysed for this run, so the output is not valid.")
        return
    if result.metadata.get("valid_hub_score_count", 0) == 0:
        st.error(
            "No valid Hub Scores were generated. Check whether the candidate postcodes are "
            "inside the selected geography and neighbourhood footprint."
        )
        return

    candidate_mode = str(result.metadata.get("candidate_mode", "manual"))

    _OVERLAY_OPTIONS = {
        "🏥  GP Practices": "GP practices",
        "💊  Pharmacies": "Community pharmacies",
        "👪  Family Hubs": "Family hubs",
        "🌿  Parks": "Parks and gardens",
        "🔺  Acute Hospitals": "Acute hospitals",
    }
    selected_overlay_labels = st.segmented_control(
        "Estates",
        options=list(_OVERLAY_OPTIONS.keys()),
        selection_mode="multi",
        default=[],
    )
    selected_overlays = [_OVERLAY_OPTIONS[label] for label in (selected_overlay_labels or [])]

    st_folium(build_output_map(result, selected_overlays), use_container_width=True, height=640, returned_objects=[])

    st.subheader("Suggested Locations" if candidate_mode == "suggested" else "Ranked Hubs")
    if candidate_mode == "suggested":
        note = str(result.metadata.get("candidate_location_note", ""))
        if note:
            st.caption(note)

    table = result.candidate_scores.drop(columns="geometry").copy()
    estate_configured = "nearby_nhs_estate_flag" in table.columns
    display_columns = ["rank", "postcode", "hub_score_pct", "borough", "nghbrhd"]
    if estate_configured:
        display_columns += ["nearby_nhs_estate_flag", "nearest_estate_name", "nearest_estate_distance_m"]
    available_columns = [c for c in display_columns if c in table.columns]
    st.dataframe(
        table.loc[:, available_columns].sort_values("rank") if "rank" in table.columns else table.loc[:, available_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "postcode": st.column_config.TextColumn("Postcode"),
            "hub_score_pct": st.column_config.NumberColumn("Hub Score", format="%.1f"),
            "borough": st.column_config.TextColumn("Borough"),
            "nghbrhd": st.column_config.TextColumn("Neighbourhood"),
            "nearby_nhs_estate_flag": st.column_config.CheckboxColumn("NHS Estate nearby"),
            "nearest_estate_name": st.column_config.TextColumn("Nearest estate site"),
            "nearest_estate_distance_m": st.column_config.NumberColumn("Distance to estate (m)", format="%.0f m"),
        },
    )
    if not estate_configured:
        st.caption("Estate proximity not available — configure ERIC data in Settings.")

    csv_bytes = table.to_csv(index=False).encode("utf-8")
    st.download_button("Download results as CSV", data=csv_bytes, file_name="hub_candidates.csv", mime="text/csv")


def render_methodology_page() -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-brand">Quality Assurance</div>
            <div class="hero-title">Methodology</div>
            <div class="hero-subtitle">
                A full description of the scoring logic, data inputs, and assumptions underlying this tool.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if METHODOLOGY_PATH.exists():
        st.markdown(METHODOLOGY_PATH.read_text(encoding="utf-8"))
    else:
        st.error(f"Methodology file not found at {METHODOLOGY_PATH}.")


def main() -> None:
    inject_styles()
    require_authentication()

    if st.query_params.get("signout") == "1":
        st.session_state.pop("authenticated_username", None)
        st.session_state.pop("auth_error", None)
        st.query_params.clear()
        st.rerun()

    query_page = st.query_params.get("page", PAGES[0])
    if isinstance(query_page, list):
        query_page = query_page[0]
    if query_page not in PAGES:
        query_page = PAGES[0]
    page = query_page

    render_topnav(page)
    config = build_config()
    report = build_validation_report(config)
    inventory = build_inventory_summary(config)

    if page == "Introduction":
        render_intro_page(report, inventory, page)
    elif page == "Configure Inputs":
        render_configure_page(config, report)
    elif page == "Outputs":
        render_outputs_page()
    else:
        render_methodology_page()


if __name__ == "__main__":
    main()
