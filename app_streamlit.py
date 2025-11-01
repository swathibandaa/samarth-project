# app_streamlit.py
import streamlit as st
import pandas as pd
import numpy as np
import re
import difflib
from datetime import datetime

# -----------------------------------
# Streamlit Page Config
# -----------------------------------
st.set_page_config(page_title="🌾 Project Samarth - Smart Agriculture Chatbot", layout="centered")

# -----------------------------------
# Dataset Paths (edit if you store elsewhere)
# -----------------------------------
AGRI_PATH = "crop.xlsx"        # Excel file (Ministry of Agriculture style)
RAINFALL_PATH = "rainfall.csv" # CSV file (IMD-style)

# -----------------------------------
# Load Datasets
# -----------------------------------
@st.cache_data
def load_data(agri_path=AGRI_PATH, rain_path=RAINFALL_PATH):
    agri = pd.DataFrame()
    rain = pd.DataFrame()
    errors = []
    # Load agriculture dataset
    try:
        agri = pd.read_excel(agri_path, engine='openpyxl')
    except Exception as e:
        errors.append(f"Error reading agriculture data ({agri_path}): {e}")

    # Load rainfall dataset
    try:
        rain = pd.read_csv(rain_path, encoding='utf-8', on_bad_lines='skip')
    except Exception as e:
        errors.append(f"Error reading rainfall data ({rain_path}): {e}")

    return agri, rain, errors

agri_df, rain_df, load_errors = load_data()

if load_errors:
    for e in load_errors:
        st.error(e)
if agri_df.empty or rain_df.empty:
    st.warning("One or both datasets are missing or empty. The app will still attempt to run but results may be limited.")
else:
    st.success("Datasets loaded (local files). For submission, cite original data.gov.in sources in your Loom video.")

# -----------------------------------
# Normalize column names to ease matching
# -----------------------------------
def normalize_columns_agri(df):
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip().replace(" ", "_").title() for c in df.columns]
    # Make common names predictable
    # Some datasets might have 'State Name' or 'State', 'Crop_Year' or 'Year'
    colmap = {}
    for c in df.columns:
        lc = c.lower()
        if "state" in lc and "district" not in lc:
            colmap[c] = "State"
        if "district" in lc:
            colmap[c] = "District"
        if "crop" == lc or "crop" in lc:
            colmap[c] = "Crop"
        if "year" in lc or "crop_year" in lc:
            colmap[c] = "Crop_Year"
        if "production" in lc or "prod" in lc:
            colmap[c] = "Production"
        if "area" in lc and "harvested" in lc:
            colmap[c] = "Area_Harvested"
    df = df.rename(columns=colmap)
    return df

def normalize_columns_rain(df):
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
    # Commonize expected columns: SUBDIVISION, YEAR, ANNUAL
    colmap = {}
    for c in df.columns:
        if "SUBDIV" in c or "STATE" in c or "REGION" in c:
            colmap[c] = "SUBDIVISION"
        if "YEAR" in c:
            colmap[c] = "YEAR"
        if "ANNUAL" in c or "TOTAL" in c or "RAIN" in c:
            colmap[c] = "ANNUAL"
    df = df.rename(columns=colmap)
    return df

agri_df = normalize_columns_agri(agri_df)
rain_df = normalize_columns_rain(rain_df)

# -----------------------------------
# Build dictionaries & lists for fuzzy lookup
# -----------------------------------
STATES = []
if not agri_df.empty and "State" in agri_df.columns:
    STATES = sorted([s for s in agri_df["State"].dropna().unique()])

# also include subdivisions from rainfall dataset for matching
RAIN_SUBDIVS = []
if not rain_df.empty and "SUBDIVISION" in rain_df.columns:
    RAIN_SUBDIVS = sorted([s for s in rain_df["SUBDIVISION"].astype(str).dropna().unique()])

# crops list
CROPS = []
if not agri_df.empty and "Crop" in agri_df.columns:
    CROPS = sorted([c for c in agri_df["Crop"].dropna().unique()])

# years available
AGRI_YEARS = sorted(agri_df["Crop_Year"].dropna().unique()) if ("Crop_Year" in agri_df.columns and not agri_df.empty) else []
RAIN_YEARS = sorted(rain_df["YEAR"].dropna().unique()) if ("YEAR" in rain_df.columns and not rain_df.empty) else []

# -----------------------------------
# Helper functions: fuzzy extractors
# -----------------------------------
def fuzzy_choice(name, choices, cutoff=0.6):
    if not name or not choices:
        return None
    matches = difflib.get_close_matches(name, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def extract_states(query):
    """Return list of 0..2 state-like strings found in query via direct or fuzzy match."""
    found = []
    qlow = query.lower()
    # direct substring match (longer names first)
    for s in sorted(STATES, key=lambda x: -len(x)):
        if s.lower() in qlow and s not in found:
            found.append(s)
            if len(found) >= 2:
                return found
    # try from words and fuzzy match
    words = re.findall(r"[A-Za-z]+", query)
    for w in words:
        match = fuzzy_choice(w.title(), STATES, cutoff=0.75)
        if match and match not in found:
            found.append(match)
            if len(found) >= 2:
                return found
    # try matching against rain subdivisions as fallback (IMD uses subdivisions)
    for s in sorted(RAIN_SUBDIVS, key=lambda x: -len(x)):
        if s.lower() in qlow and s not in found:
            found.append(s)
            if len(found) >= 2:
                return found
    return found

def extract_crop(query):
    qlow = query.lower()
    for c in sorted(CROPS, key=lambda x: -len(x)):
        if c.lower() in qlow:
            return c
    # fuzzy by words
    words = re.findall(r"[A-Za-z]+", query)
    for w in words:
        match = fuzzy_choice(w.title(), CROPS, cutoff=0.75)
        if match:
            return match
    return None

def extract_top_m(query, default=3):
    m = re.search(r"top\s+(\d+)", query.lower())
    if m:
        return int(m.group(1))
    m = re.search(r"top[-\s]?(\d+)", query.lower())
    if m:
        return int(m.group(1))
    return default

def extract_last_n_years(query, default=3, limit=10):
    """Return list of last N years (most recent available in both datasets)"""
    n_match = re.search(r"last\s+(\d+)\s+years", query.lower())
    if n_match:
        n = int(n_match.group(1))
    else:
        # also support "for the last N years" or "over N years"
        n_match = re.search(r"last\s+(\d+)", query.lower())
        n = int(n_match.group(1)) if n_match else default
    n = max(1, min(n, limit))
    # determine recent common year range
    years = sorted(set(AGRI_YEARS) | set(RAIN_YEARS))
    if not years:
        # fallback - try any plausible year mention
        explicit = re.findall(r"(19|20)\d{2}", query)
        if explicit:
            return [int(explicit[-1])]
        return []
    latest = max(years)
    # pick latest N years that exist in at least one dataset
    selected = [y for y in sorted(years, reverse=True)][:n]
    return sorted(selected)

def extract_year_from_query(query):
    y = re.search(r"(19|20)\d{2}", query)
    return int(y.group(0)) if y else None

# -----------------------------------
# Core answer-building functions
# -----------------------------------
def compute_avg_rainfall_for_years(state, years):
    """Return dict year -> avg annual rainfall (mm) and provenance"""
    data = {}
    provenance = []
    # try matching state to SUBDIVISION first (IMD)
    sub_match = fuzzy_choice(state.upper(), RAIN_SUBDIVS, cutoff=0.6) if RAIN_SUBDIVS else None
    # also try match against State names present in rain_df (if any)
    fallback_match = fuzzy_choice(state, STATES, cutoff=0.6) if STATES else None

    for y in years:
        val = None
        # attempt: filter by SUBDIVISION match
        if sub_match and "SUBDIVISION" in rain_df.columns:
            subset = rain_df[(rain_df["SUBDIVISION"].astype(str).str.upper() == sub_match) & (rain_df["YEAR"] == y)]
            if not subset.empty and "ANNUAL" in subset.columns:
                val = subset["ANNUAL"].astype(float).replace([np.inf, -np.inf], np.nan).dropna().mean()
                provenance.append(f"rain_df[(SUBDIVISION=='{sub_match}') & (YEAR=={y})]['ANNUAL']")
        # fallback: try using state name in rain_df as substring
        if val is None and "SUBDIVISION" in rain_df.columns:
            subset = rain_df[(rain_df["SUBDIVISION"].astype(str).str.contains(state, case=False, na=False)) & (rain_df["YEAR"] == y)]
            if not subset.empty and "ANNUAL" in subset.columns:
                val = subset["ANNUAL"].astype(float).replace([np.inf, -np.inf], np.nan).dropna().mean()
                provenance.append(f"rain_df[SUBDIVISION contains '{state}' & YEAR=={y}]['ANNUAL']")
        # absolute fallback: any record for that year
        if val is None and "ANNUAL" in rain_df.columns:
            subset = rain_df[rain_df["YEAR"] == y]
            if not subset.empty:
                # average across subdivisions (less precise)
                val = subset["ANNUAL"].astype(float).replace([np.inf, -np.inf], np.nan).dropna().mean()
                provenance.append(f"rain_df[YEAR=={y}]['ANNUAL'] (state match failed, used national avg fallback)")
        data[y] = float(val) if (val is not None and not np.isnan(val)) else None
    return data, provenance

def compute_top_crops_for_state_and_years(state, years, top_m=3):
    """Return top M crops by total production across the given years for that state."""
    provenance = []
    df = agri_df.copy()
    # filter by state (case-insensitive contains)
    if "State" in df.columns:
        subset = df[df["State"].astype(str).str.contains(state, case=False, na=False) & df["Crop_Year"].isin(years)]
        provenance.append(f"agri_df[State contains '{state}' & Crop_Year in {years}]")
    else:
        subset = pd.DataFrame()
    if subset.empty:
        return pd.Series(dtype=float), provenance
    # ensure numeric production
    if "Production" in subset.columns:
        subset["Production"] = pd.to_numeric(subset["Production"], errors="coerce").fillna(0)
        top = subset.groupby("Crop")["Production"].sum().sort_values(ascending=False).head(top_m)
        return top, provenance
    else:
        return pd.Series(dtype=float), provenance

def district_extremes_for_crop(state, crop, year):
    """Return district with highest and lowest production for given state, crop, year."""
    prov = []
    df = agri_df.copy()
    if "State" in df.columns and "Crop" in df.columns and "District" in df.columns and "Production" in df.columns:
        subset = df[
            df["State"].astype(str).str.contains(state, case=False, na=False) &
            (df["Crop"].astype(str).str.lower() == str(crop).lower()) &
            (df["Crop_Year"] == year)
        ]
        prov.append(f"agri_df[State contains '{state}' & Crop=='{crop}' & Crop_Year=={year}]")

        if subset.empty:
            return None, None, prov
        subset["Production"] = pd.to_numeric(subset["Production"], errors="coerce").fillna(0)
        grouped = subset.groupby("District")["Production"].sum()
        high = grouped.idxmax()
        low = grouped.idxmin()
        return (high, grouped[high]), (low, grouped[low]), prov
    else:
        return None, None, prov

# -----------------------------------
# Answer assembly
# -----------------------------------
def answer_query(query):
    query = query.strip()
    if not query:
        return "Please type a question.", ""
    # Extract items
    states = extract_states(query)  # 0..2
    crop = extract_crop(query)
    top_m = extract_top_m(query, default=3)
    years = extract_last_n_years(query, default=3)
    explicit_year = extract_year_from_query(query)
    if explicit_year:
        years = [explicit_year] if years == [] else years
        # If user gives single explicit year, prefer that
        # but if they asked "last 5 years" AND included explicit year, we keep last N logic

    # build answer parts
    parts = []
    prov_lines = []
    # 1) If two states asked -> compare rainfall over years
    if len(states) >= 2:
        s1, s2 = states[0], states[1]
        if not years:
            years = extract_last_n_years(query, default=3)
        rain1, p1 = compute_avg_rainfall_for_years(s1, years)
        rain2, p2 = compute_avg_rainfall_for_years(s2, years)
        parts.append(f"🌧️ **Rainfall comparison — {', '.join(map(str, years))}**")
        table = []
        for y in years:
            v1 = rain1.get(y)
            v2 = rain2.get(y)
            v1s = f"{v1:.2f} mm" if v1 is not None else "N/A"
            v2s = f"{v2:.2f} mm" if v2 is not None else "N/A"
            parts.append(f"- {y}: **{s1}**: {v1s}   |   **{s2}**: {v2s}")
            table.append({"Year": y, s1: v1, s2: v2})
        prov_lines += p1 + p2
        # show visual
        prov_lines.append(f"Visualization: bar chart of annual rainfall for {s1} and {s2} over {years}")
        # If crops also asked, show top crops for both
        if "crop" in query.lower() or crop:
            parts.append(f"\n🌾 **Top {top_m} crops comparison ({', '.join(map(str, years))})**")
            top1, ptop1 = compute_top_crops_for_state_and_years(s1, years, top_m)
            top2, ptop2 = compute_top_crops_for_state_and_years(s2, years, top_m)
            prov_lines += ptop1 + ptop2
            if not top1.empty:
                parts.append(f"- **{s1}**: " + ", ".join([f"{idx} ({val:.1f} t)" for idx, val in top1.items()]))
            else:
                parts.append(f"- **{s1}**: No crop data found for selection.")
            if not top2.empty:
                parts.append(f"- **{s2}**: " + ", ".join([f"{idx} ({val:.1f} t)" for idx, val in top2.items()]))
            else:
                parts.append(f"- **{s2}**: No crop data found for selection.")
        # return with simple table data for plotting in UI
        return ("\n".join(parts), {"provenance": prov_lines, "table": pd.DataFrame(table)})
    # 2) Single state queries: rainfall and top crops for given years or year
    if len(states) == 1:
        s = states[0]
        if not years:
            years = extract_last_n_years(query, default=3)
        # rainfall
        rain_data, p = compute_avg_rainfall_for_years(s, years)
        prov_lines += p
        parts.append(f"🌧️ **Average annual rainfall for {s}**")
        for y in years:
            v = rain_data.get(y)
            parts.append(f"- {y}: {f'{v:.2f} mm' if v is not None else 'N/A'}")
        # top crops
        if "crop" in query.lower() or crop or ("top" in query.lower()):
            parts.append(f"\n🌾 **Top {top_m} crops in {s} (aggregated over {', '.join(map(str, years))})**")
            top, ptop = compute_top_crops_for_state_and_years(s, years, top_m)
            prov_lines += ptop
            if not top.empty:
                parts.append(" - " + ", ".join([f"{idx} ({val:.1f} tonnes)" for idx, val in top.items()]))
            else:
                parts.append(" - No crop production found for this selection.")
        # district extremes if user asks specifically for highest/lowest district for a crop
        if crop and ("highest" in query.lower() or "lowest" in query.lower() or "district" in query.lower()):
            # use most recent year if multiple
            use_year = years[-1] if years else (max(AGRI_YEARS) if AGRI_YEARS else None)
            if use_year:
                high, low, provd = district_extremes_for_crop(s, crop, use_year)
                prov_lines += provd
                parts.append(f"\n📍 **District-level extremes for {crop} in {s} ({use_year})**")
                if high and low:
                    parts.append(f"- Highest production: {high[0]} — {high[1]:.1f} tonnes")
                    parts.append(f"- Lowest production: {low[0]} — {low[1]:.1f} tonnes")
                else:
                    parts.append("- No district-level data found for this selection.")
        return ("\n".join(parts), {"provenance": prov_lines, "rain_data": rain_data})
    # 3) No states found: try country-level or instruct user
    # If the user asked to compare two named states but our extractor failed, prompt politely
    if not states:
        return ("⚠️ I couldn't detect a state name in your question. Please mention one or two Indian states (e.g., 'Maharashtra', 'Kerala').", "")
    return ("I couldn't answer that query with available data. Try a different phrasing.", "")

# -----------------------------------
# STREAMLIT UI
# -----------------------------------
st.title("🌾 Project Samarth — Enhanced Agriculture & Rainfall Q&A")
st.caption("Ask natural-language questions about crop production and rainfall. Data is read from local files (simulate data.gov.in sources).")

st.markdown("**Examples:**")
st.markdown("- Compare the average annual rainfall in Tamil Nadu and Kerala for the last 3 years and list top 3 crops.")
st.markdown("- Top 5 crops in Maharashtra for the last 2 years")
st.markdown("- Which district in Andhra Pradesh had the highest production of Rice in 2019?")
st.markdown("- Show average rainfall in Karnataka for 2015")

query = st.text_input("💬 Your question", placeholder="Ex: Compare rainfall in Tamil Nadu and Kerala for the last 5 years")
if st.button("🔍 Get Answer") and query.strip():
    with st.spinner("Analyzing..."):
        answer, meta = answer_query(query)
    # If meta is a dataframe table (comparison case), render differently
    if isinstance(meta, dict) and "table" in meta and isinstance(meta["table"], pd.DataFrame):
        st.markdown(answer)
        df_table = meta["table"]
        st.dataframe(df_table.set_index("Year"))
        # Plot if valid numbers
        plot_df = df_table.set_index("Year")
        try:
            st.line_chart(plot_df)
        except Exception:
            pass
        if meta.get("provenance"):
            with st.expander("🧾 Provenance & Logic"):
                for p in meta["provenance"]:
                    st.code(p)
        # cite sources
        st.markdown("**Data source (local files used):** `crop.xlsx` (Ministry of Agriculture style), `rainfall.csv` (IMD style). In a full deployment these would be fetched from data.gov.in APIs.")
    else:
        # plain text answer with optional structured meta
        st.markdown(answer.replace("\n", "  \n"))
        if isinstance(meta, dict):
            # show rainfall chart if present
            if "rain_data" in meta and isinstance(meta["rain_data"], dict) and any(v is not None for v in meta["rain_data"].values()):
                rd = meta["rain_data"]
                rd_series = pd.Series({y: rd[y] for y in sorted(rd.keys())})
                # turn numeric N/A to NaN so chart skips them
                rd_series = rd_series.astype(float)
                st.line_chart(rd_series)
            # provenance
            prov = meta.get("provenance")
            if prov:
                with st.expander("🧾 Provenance & Logic"):
                    for p in prov:
                        st.code(p)
        # final data source note
        st.markdown("**Data source (local files used):** `crop.xlsx` (Ministry of Agriculture style), `rainfall.csv` (IMD style). Cite original datasets from data.gov.in in final submission.")

st.markdown("---")
st.markdown("💡 Tips for the 2-minute Loom:")
st.markdown("- Show the Streamlit app answering 1) a two-state comparison and 2) a single-state + top crops query.  \n- Expand the Provenance to show how each number maps to a dataset slice.  \n- Mention where you'd plug in data.gov.in APIs for live updates.")

