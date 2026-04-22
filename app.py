from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from branca.colormap import linear
from streamlit_folium import st_folium

from build_weighted_priority_map import load_community_pharmacies, load_family_hubs, load_gp_practices
from webapp.analysis import INDEX_DEFINITIONS, AnalysisResult, run_analysis
from webapp.config import AppConfig, ICB_CHOICES
from webapp.data_access import load_asset_counts, load_neighbourhoods
from webapp.data_validation import ValidationReport, validate_config


st.set_page_config(page_title="Neighbourhood Hub Ranker", layout="wide")

LOGO_PATH = Path("data/logos/PPL Logo_RGB.png")
BRAND_PURPLE = "#490E6F"
BRAND_PURPLE_DARK = "#350355"
BRAND_PURPLE_SOFT = "#FAF6FD"
BRAND_PURPLE_MID = "#EAE3F0"
BRAND_TEXT = "#0D0517"
PAGES = ["Introduction", "Configure Inputs", "Outputs"]
ICB_CODE_BY_NAME = {
    "NHS North Central London ICB": "NCL",
    "NHS North East London ICB": "NEL",
    "NHS North West London ICB": "NWL",
    "NHS South East London ICB": "SEL",
    "NHS South West London ICB": "SWL",
}
ASSET_OVERLAY_STYLES = {
    "GP practices": {"loader": load_gp_practices, "color": "#D81B60", "radius": 5},
    "Community pharmacies": {"loader": load_community_pharmacies, "color": "#1F77B4", "radius": 5},
    "Family hubs": {"loader": load_family_hubs, "color": "#2CA02C", "radius": 5},
}


def render_app_header() -> None:
    left, right = st.columns([0.24, 0.76], vertical_alignment="center")
    with left:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=220)
        else:
            st.markdown('<div class="brand-fallback">PPL</div>', unsafe_allow_html=True)
    with right:
        st.markdown(
            """
            <div class="brand-kicker">PPL</div>
            <div class="brand-heading">London Neighbourhood Hub Decision Explorer</div>
            <div class="brand-note">Candidate location ranking for neighbourhood hub planning</div>
            """,
            unsafe_allow_html=True,
        )


def inject_styles() -> None:
    st.markdown(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
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
            --shadow-lg: 0 20px 50px rgba(73,14,111,.14);
        }
        html, body, [class*="css"] {
            font-family: 'Poppins', Inter, system-ui, sans-serif !important;
        }
        .stApp {
            background: var(--ppl-cream);
        }
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }
        section[data-testid="stSidebar"] {
            background-color: var(--ppl-purple);
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .stMarkdown {
            color: white !important;
        }
        section[data-testid="stSidebar"] .stExpander details {
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 8px;
            background: rgba(255,255,255,.06);
        }
        section[data-testid="stSidebar"] .stExpander summary {
            color: white !important;
        }
        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] textarea {
            background: rgba(255,255,255,.1) !important;
            color: white !important;
            border-color: rgba(255,255,255,.2) !important;
        }
        .sidebar-credentials {
            font-size: 0.72rem;
            color: rgba(255,255,255,.5);
            text-align: center;
            padding-top: 12px;
            border-top: 1px solid rgba(255,255,255,.12);
            margin-top: 16px;
            line-height: 1.6;
        }
        .brand-fallback {
            color: var(--ppl-purple);
            font-weight: 800;
            font-size: 2.2rem;
            line-height: 1;
        }
        .brand-kicker {
            color: var(--ppl-purple);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 2px;
        }
        .brand-heading {
            color: var(--ppl-ink);
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .brand-note {
            color: var(--ppl-muted);
            font-size: 0.95rem;
            text-align: left;
            max-width: 640px;
            margin-top: 6px;
        }
        .hero-shell {
            border: 1px solid var(--ppl-line);
            border-radius: 24px;
            padding: 24px 28px;
            background: var(--ppl-paper);
            box-shadow: var(--shadow-md);
            margin-bottom: 18px;
        }
        .hero-brand {
            color: var(--ppl-purple);
            font-weight: 700;
            letter-spacing: 0.1em;
            font-size: 0.72rem;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .hero-title {
            color: var(--ppl-ink);
            font-size: 2.2rem;
            font-weight: 700;
            line-height: 1.05;
            margin-bottom: 8px;
        }
        .hero-subtitle {
            color: var(--ppl-ink2);
            font-size: 1.05rem;
            max-width: 920px;
        }
        .nav-card {
            border: 1px solid var(--ppl-line);
            border-radius: 12px;
            padding: 14px 16px;
            background: var(--ppl-paper);
            min-height: 170px;
            box-shadow: var(--shadow-sm);
            transition: transform 150ms cubic-bezier(.2,.7,.2,1), box-shadow 150ms cubic-bezier(.2,.7,.2,1), border-color 150ms cubic-bezier(.2,.7,.2,1);
        }
        .nav-card:hover {
            transform: translateY(-1px);
            border-color: var(--ppl-purple);
            box-shadow: var(--shadow-md);
        }
        .nav-card-active {
            border-color: var(--ppl-purple);
            background: var(--ppl-paper);
            box-shadow: var(--shadow-md);
        }
        .nav-card h4 {
            margin: 0 0 6px 0;
            color: var(--ppl-ink);
            font-size: 1rem;
        }
        .nav-card p {
            margin: 0;
            color: var(--ppl-muted);
            font-size: 0.95rem;
        }
        .nav-action {
            margin-top: 14px;
        }
        .nav-action button {
            width: 100%;
            min-height: 42px;
        }
        .section-shell {
            border: 1px solid var(--ppl-line);
            border-radius: 12px;
            padding: 18px 20px;
            background: var(--ppl-paper);
            box-shadow: var(--shadow-sm);
            margin-bottom: 18px;
        }
        .section-title {
            color: var(--ppl-ink);
            font-size: 1.55rem;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .section-copy {
            color: var(--ppl-muted);
            margin-bottom: 14px;
        }
        .mini-label {
            color: var(--ppl-purple);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 6px;
        }
        .stButton > button, div[data-testid="stDownloadButton"] > button {
            background: var(--ppl-purple);
            color: white;
            border: 1px solid var(--ppl-purple);
            border-radius: 999px;
            font-weight: 600;
            font-family: 'Poppins', Inter, system-ui, sans-serif;
            transition: background 150ms cubic-bezier(.2,.7,.2,1), border-color 150ms cubic-bezier(.2,.7,.2,1);
        }
        .stButton > button:hover, div[data-testid="stDownloadButton"] > button:hover {
            background: var(--ppl-deep);
            border-color: var(--ppl-deep);
            color: white;
        }
        input[type="radio"] {
            accent-color: var(--ppl-purple);
        }
        div[role="radiogroup"] label[data-baseweb="radio"] {
            align-items: center;
        }
        div[data-testid="stMetric"] {
            background: var(--ppl-paper);
            border: 1px solid var(--ppl-line);
            padding: 10px 12px;
            border-radius: 12px;
            box-shadow: var(--shadow-sm);
        }
        @media (max-width: 900px) {
            .brand-note {
                max-width: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_config() -> AppConfig:
    with st.sidebar:
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
    card_specs = [
        (
            "Introduction",
            "Guide",
            "Understand what the tool does, what data it depends on, and how outputs should be interpreted.",
        ),
        (
            "Configure Inputs",
            "Setup",
            "Define geography, focus neighbourhoods, need indices, and candidate postcodes.",
        ),
        (
            "Outputs",
            "Outputs",
            "Review the choropleth, candidate ranking, scoring explanation, and audit summary.",
        ),
    ]
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-brand">NHS / ICB Decision Support</div>
            <div class="hero-title">Neighbourhood Hub<br>Location Ranker</div>
            <div class="hero-subtitle">
                Explore candidate hub locations against nearby population need, preview neighbourhood footprint before
                running the model, and rank options using a transparent proximity-weighted scoring method.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(3, gap="large")
    for idx, (page_name, title, copy) in enumerate(card_specs):
        active_class = " nav-card-active" if current_page == page_name else ""
        with cols[idx]:
            st.markdown(
                f"""
                <div class="nav-card{active_class}">
                    <h4>{title}</h4>
                    <p>{copy}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Open {title.lower()}",
                key=f"nav_{page_name}",
                use_container_width=True,
                type="secondary" if current_page == page_name else "primary",
            ):
                st.query_params["page"] = page_name
                st.rerun()
    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">About this tool</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">This application ranks proposed Neighbourhood Hub locations by estimating how much nearby need they would serve. It uses your existing London LSOA need inputs as the analytical engine, then applies a postcode-led proximity model around each candidate hub.</div>',
        unsafe_allow_html=True,
    )
    st.write(
        "Need Score is calculated at LSOA level from user-selected indices. Each selected index is min-max scaled "
        "across the chosen geography, then combined using user-defined weights that must sum to 100."
    )
    st.write(
        "Hub Score is calculated from the candidate postcode's host LSOA and surrounding LSOA centroids: "
        "`0.60 x host Need Score + 0.25 x mean Need Score within 500m + 0.15 x mean Need Score between 500m and 2km`."
    )
    st.info("Outputs are decision-support only. They do not replace local service planning, estate checks, or clinical judgement.")

    st.subheader("Data Validation")
    render_validation_panel(report)

    st.subheader("Audit")
    render_audit_metrics(report, inventory)

    st.subheader("Sources")
    render_source_table(report)
    st.markdown("</div>", unsafe_allow_html=True)


def selected_indices_controls() -> tuple[list[str], dict[str, float], float]:
    st.subheader("Need Model")
    selected_indices = st.multiselect(
        "Select indices to include",
        options=list(INDEX_DEFINITIONS),
        default=["deprivation_inverse", "population", "population_65_plus"],
        format_func=lambda key: INDEX_DEFINITIONS[key]["label"],
    )
    weights: dict[str, float] = {}
    total_weight = 0.0
    for index_name in selected_indices:
        weight = st.number_input(
            f"{INDEX_DEFINITIONS[index_name]['label']} weight",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=5.0,
            key=f"weight_{index_name}",
        )
        weights[index_name] = weight
        total_weight += weight

    if selected_indices:
        st.write("Selected indices")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Index": INDEX_DEFINITIONS[index_name]["label"],
                        "Weight": weights[index_name],
                        "Definition": INDEX_DEFINITIONS[index_name]["description"],
                    }
                    for index_name in selected_indices
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    st.metric("Weight total", f"{total_weight:.0f}")
    return selected_indices, weights, total_weight


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

    if neighbourhoods.empty:
        return folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles="CartoDB positron")

    selected_set = set(selected_neighbourhoods)
    centre_geom = neighbourhoods.to_crs(27700).union_all().centroid
    centre_geom = pd.Series([centre_geom], dtype="object")
    centre = gpd.GeoSeries(centre_geom, crs=27700).to_crs(4326).iloc[0]
    fmap = folium.Map(
        location=[float(centre.y), float(centre.x)],
        zoom_start=10,
        tiles="CartoDB positron",
    )

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
def load_asset_overlay_frame(asset_name: str) -> pd.DataFrame:
    overlay = ASSET_OVERLAY_STYLES[asset_name]["loader"]()
    overlay = overlay.to_crs(4326)
    label_column = None
    for candidate in ["Practice Name", "SiteName", "Family_Hub", "Postcode", "hub_name"]:
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


def add_asset_overlays(
    fmap: folium.Map,
    result: AnalysisResult,
    selected_overlays: list[str],
) -> folium.Map:
    if not selected_overlays:
        return fmap

    scope_union = result.need_scores.to_crs(4326).union_all()
    for asset_name in selected_overlays:
        style = ASSET_OVERLAY_STYLES[asset_name]
        asset_points = load_asset_overlay_frame(asset_name)
        if asset_points.empty:
            continue
        asset_points = gpd.GeoDataFrame(
            asset_points,
            geometry=gpd.points_from_xy(asset_points["longitude"], asset_points["latitude"]),
            crs=4326,
        )
        asset_points = asset_points[asset_points.intersects(scope_union)].copy()
        if asset_points.empty:
            continue
        layer = folium.FeatureGroup(name=asset_name, show=True)
        for _, row in asset_points.iterrows():
            folium.CircleMarker(
                location=[float(row.geometry.y), float(row.geometry.x)],
                radius=style["radius"],
                color=style["color"],
                weight=1,
                fill=True,
                fill_color=style["color"],
                fill_opacity=0.85,
                tooltip=f"{asset_name}: {row['label']}",
            ).add_to(layer)
        layer.add_to(fmap)

    return fmap


def render_configure_page(config: AppConfig, report: ValidationReport) -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-brand">Setup</div>
            <div class="hero-title">Footprint Builder</div>
            <div class="hero-subtitle">
                Define the analysis area, preview the neighbourhood footprint that will be included, then configure
                need weights and candidate hub locations.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.markdown('<div class="mini-label">Spatial Perspective</div>', unsafe_allow_html=True)
    geography_mode = st.radio("Geography", options=["All London", "Specific ICB"], horizontal=True, label_visibility="collapsed")
    icb_name = None
    if geography_mode == "Specific ICB":
        icb_name = st.selectbox("ICB", options=ICB_CHOICES)

    neighbourhood_frame = load_neighbourhood_frame(config)
    if geography_mode == "Specific ICB" and icb_name:
        icb_code = ICB_CODE_BY_NAME.get(icb_name)
        neighbourhood_frame = neighbourhood_frame[neighbourhood_frame["ICB"].eq(icb_code)].copy()

    filter_col, select_col = st.columns(2, gap="large")
    with filter_col:
        borough_options = sorted(neighbourhood_frame["borough"].dropna().unique().tolist())
        selected_boroughs = st.multiselect("Filter neighbourhood list by borough", options=borough_options)
    if selected_boroughs:
        filtered_neighbourhoods = neighbourhood_frame[neighbourhood_frame["borough"].isin(selected_boroughs)].copy()
    else:
        filtered_neighbourhoods = neighbourhood_frame.copy()
    with select_col:
        neighbourhood_options = sorted(filtered_neighbourhoods["nghbrhd"].dropna().unique().tolist())
        selected_neighbourhoods = st.multiselect(
            "Select neighbourhoods to focus on",
            options=neighbourhood_options,
            placeholder="Leave blank to include the full selected geography",
        )
    st.caption(
        f"Selected neighbourhoods: {len(selected_neighbourhoods)} of {len(neighbourhood_options) if neighbourhood_options else 0}"
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Neighbourhood coverage preview</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">The preview map spans the page so users can confirm the footprint before moving into scoring inputs.</div>',
        unsafe_allow_html=True,
    )
    preview_map = build_neighbourhood_preview_map(config, geography_mode, icb_name, selected_neighbourhoods)
    st_folium(preview_map, use_container_width=True, height=560, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)

    lower_left, lower_right = st.columns([1.05, 0.95], gap="large")
    with lower_left:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        selected_indices, weights, total_weight = selected_indices_controls()
        st.markdown("</div>", unsafe_allow_html=True)
    with lower_right:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.subheader("Candidate Hub Locations")
        candidate_postcodes_raw = st.text_area(
            "Enter one postcode per line",
            height=220,
            placeholder="E1 4DG\nSE1 2QH\nN15 4RX",
        )
        candidate_postcodes = parse_postcodes(candidate_postcodes_raw)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.subheader("Analysis Audit")
    audit_frame = pd.DataFrame(
        [
            {"Setting": "Selected geography", "Value": icb_name if icb_name else geography_mode},
            {"Setting": "Indexed LSOAs in source files", "Value": report.index_lsoa_count or 0},
            {
                "Setting": "Focus neighbourhoods",
                "Value": ", ".join(selected_neighbourhoods[:8]) + (" ..." if len(selected_neighbourhoods) > 8 else "")
                if selected_neighbourhoods
                else "Full selected geography",
            },
            {"Setting": "Candidate hubs", "Value": len(candidate_postcodes)},
            {
                "Setting": "Indices and weights",
                "Value": ", ".join(
                    f"{INDEX_DEFINITIONS[index_name]['label']} ({weights[index_name]:.0f})"
                    for index_name in selected_indices
                )
                or "None selected",
            },
        ]
    )
    st.dataframe(audit_frame, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    can_run = bool(selected_indices) and total_weight == 100 and report.can_run_analysis and bool(candidate_postcodes)
    if total_weight != 100:
        st.error("Weights must sum to 100 before analysis can run.")
    if not selected_indices:
        st.error("Select at least one index.")
    if not candidate_postcodes:
        st.error("Enter at least one candidate postcode.")
    if not report.can_run_analysis:
        st.error("Fix the blocking input issues shown on the Introduction page before running analysis.")

    if st.button("Run analysis", type="primary", disabled=not can_run):
        try:
            with st.spinner("Running need and hub scoring..."):
                result = run_analysis(
                    config=config,
                    geography_mode=geography_mode,
                    icb_name=icb_name,
                    index_weights=weights,
                    candidate_postcodes=candidate_postcodes,
                    selected_neighbourhoods=selected_neighbourhoods,
                )
            st.session_state["analysis_result"] = result
            st.success("Analysis complete. Open the Output page to review the ranking.")
        except Exception as exc:
            st.session_state.pop("analysis_result", None)
            st.error(str(exc))


def build_output_map(result: AnalysisResult, selected_overlays: list[str] | None = None) -> folium.Map:
    need_scores = result.need_scores.to_crs(4326)
    candidates = result.candidate_scores.to_crs(4326)
    valid_need_scores = need_scores[need_scores.geometry.notna() & (~need_scores.geometry.is_empty)].copy()
    valid_candidates = candidates[candidates.geometry.notna() & (~candidates.geometry.is_empty)].copy()

    if valid_need_scores.empty:
        return folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles="CartoDB positron")

    centre_geom = valid_need_scores.to_crs(27700).union_all().centroid
    centre_geom = pd.Series([centre_geom], dtype="object")
    centre = gpd.GeoSeries(centre_geom, crs=27700).to_crs(4326).iloc[0]
    fmap = folium.Map(location=[float(centre.y), float(centre.x)], zoom_start=10, tiles="CartoDB positron")

    colormap = linear.YlOrRd_09.scale(
        float(valid_need_scores["need_score_pct"].min()),
        float(valid_need_scores["need_score_pct"].max()),
    )
    colormap.caption = "Need Score"
    colormap.add_to(fmap)

    folium.GeoJson(
        valid_need_scores.loc[:, ["LSOA_code", "need_score_pct", "geometry"]].to_json(),
        style_function=lambda feature: {
            "fillColor": colormap(feature["properties"]["need_score_pct"]),
            "color": "#666666",
            "weight": 0.3,
            "fillOpacity": 0.7,
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
                    "weight": 2.0,
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
        hub_score_label = f"{hub_score_pct:.2f}" if pd.notna(hub_score_pct) else "N/A"
        popup = folium.Popup(
            html=(
                f"<strong>{row['postcode']}</strong><br>"
                f"Rank: {row['rank']}<br>"
                f"Hub Score: {hub_score_label}<br>"
                f"Host LSOA: {row['LSOA_code']}"
            ),
            max_width=260,
        )
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=7,
            color="#350355",
            weight=1,
            fill=True,
            fill_color="#9576FF",
            fill_opacity=0.95,
            popup=popup,
        ).add_to(fmap)

    fmap = add_asset_overlays(fmap, result, selected_overlays or [])
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def render_outputs_page() -> None:
    st.title("Outputs")
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
            "No valid Hub Scores were generated for this run. Check whether the candidate postcode host LSOAs are "
            "inside the selected geography and neighbourhood footprint."
        )
        diagnostics = pd.DataFrame(
            [
                {"Metric": "LSOAs analysed", "Value": result.metadata.get("lsoa_count", 0)},
                {"Metric": "Valid Need Scores", "Value": result.metadata.get("valid_need_score_count", 0)},
                {"Metric": "Candidate hubs", "Value": result.metadata.get("candidate_count", 0)},
                {"Metric": "In-scope host LSOAs", "Value": result.metadata.get("in_scope_host_count", 0)},
                {"Metric": "Valid Hub Scores", "Value": result.metadata.get("valid_hub_score_count", 0)},
            ]
        )
        st.dataframe(diagnostics, use_container_width=True, hide_index=True)
        return

    st.subheader("Map")
    overlay_toggle_col, overlay_picker_col = st.columns([0.22, 0.78], gap="large")
    with overlay_toggle_col:
        show_existing_assets = st.toggle("Show existing services", value=False)
    with overlay_picker_col:
        selected_overlays = st.multiselect(
            "Add existing services to the map",
            options=list(ASSET_OVERLAY_STYLES),
            default=list(ASSET_OVERLAY_STYLES) if show_existing_assets else [],
            disabled=not show_existing_assets,
            placeholder="Select GP practices, community pharmacies, and family hubs",
        )
    st_folium(build_output_map(result, selected_overlays), use_container_width=True, height=700)

    st.subheader("Ranked Candidate Hubs")
    table = result.candidate_scores.drop(columns="geometry").copy()
    ordered_columns = [
        "postcode",
        "rank",
        "hub_score_pct",
        "LSOA_code",
        "host_need_score_pct",
        "mean_need_score_0_to_500m_pct",
        "mean_need_score_500m_to_2km_pct",
        "lsoas_0_to_500m",
        "lsoas_500m_to_2km",
        "geocode_source",
    ]
    available_columns = [column for column in ordered_columns if column in table.columns]
    st.dataframe(table.loc[:, available_columns], use_container_width=True, hide_index=True)

    st.subheader("Method")
    weights_summary = ", ".join(
        f"{INDEX_DEFINITIONS[index_name]['label']} ({weight:.0f})"
        for index_name, weight in result.metadata["index_weights"].items()
    )
    neighbourhood_summary = result.metadata.get("selected_neighbourhoods", [])
    st.write(f"Selected indices and weights: {weights_summary}")
    if neighbourhood_summary:
        st.write(f"Neighbourhood focus: {', '.join(neighbourhood_summary)}")
    else:
        st.write("Neighbourhood focus: full selected geography.")
    st.write(
        "Need Score uses min-max scaled indices within the selected geography. Hub Score combines the host LSOA "
        "Need Score with nearby centroid-based demand using 60/25/15 proximity weights."
    )

    st.subheader("Audit")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("LSOAs analysed", f"{result.metadata['lsoa_count']:,}")
    col2.metric("Candidate hubs ranked", f"{result.metadata['candidate_count']:,}")
    col3.metric("Generated", str(result.metadata["generated_at"]))
    col4.metric("Data version", str(result.metadata["data_version"]))
    diag1, diag2 = st.columns(2)
    diag1.metric("Valid Need Scores", f"{result.metadata.get('valid_need_score_count', 0):,}")
    diag2.metric("Valid Hub Scores", f"{result.metadata.get('valid_hub_score_count', 0):,}")


def main() -> None:
    inject_styles()
    render_app_header()
    config = build_config()
    report = build_validation_report(config)
    inventory = build_inventory_summary(config)

    query_page = st.query_params.get("page", PAGES[0])
    if isinstance(query_page, list):
        query_page = query_page[0]
    if query_page not in PAGES:
        query_page = PAGES[0]

    page = st.sidebar.radio("Pages", options=PAGES, index=PAGES.index(query_page))
    st.sidebar.markdown(
        '<div class="sidebar-credentials">B Corp · Social Enterprise UK<br>FT Leading Consultancy 2025</div>',
        unsafe_allow_html=True,
    )
    if page != query_page:
        st.query_params["page"] = page
    if page == "Introduction":
        render_intro_page(report, inventory, page)
    elif page == "Configure Inputs":
        render_configure_page(config, report)
    else:
        render_outputs_page()


if __name__ == "__main__":
    main()
