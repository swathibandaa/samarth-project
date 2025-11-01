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
# Dataset Paths
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
    try:
        agri = pd.read_excel(agri_path, engine='openpyxl')
    except Exception as e:
        errors.append(f"Error reading agriculture data ({agri_path}): {e}")
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
    st.success("✅ Datasets loaded successfully (local files). Data mirrors data.gov.in sources.")

# -----------------------------------
# Normalize column names
# -----------------------------------
def normalize_columns_agri(df):
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip().replace(" ", "_").title() for c in df.columns]
    colmap = {}
    for c in df.columns:
        lc = c.lower()
        if "state" in lc and "district" not in lc:
            colmap[c] = "State"
        if "district" in lc:
            colmap[c] = "District"
        if "crop" in lc:
            colmap[c] = "Crop"
        if "year" in lc:
            colmap[c] = "Crop_Year"
        if "production" in lc:
            colmap[c] = "Production"
        if "area" in lc and "harvested" in lc:
            colmap[c] = "Area_Harvested"
    return df.rename(columns=colmap)

def normalize_columns_rain(df):
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
    colmap = {}
    for c in df.columns:
        if "SUBDIV" in c or "STATE" in c:
            colmap[c] = "SUBDIVISION"
        if "YEAR" in c:
            colmap[c] = "YEAR"
        if "ANNUAL" in c or "TOTAL" in c or "RAIN" in c:
            colmap[c] = "ANNUAL"
    return df.rename(columns=colmap)

agri_df = normalize_columns_agri(agri_df)
rain_df = normalize_columns_rain(rain_df)

# -----------------------------------
# Prepare reference lists
# -----------------------------------
STATES = sorted(agri_df["State"].dropna().unique()) if "State" in agri_df.columns else []
RAIN_SUBDIVS = sorted(rain_df["SUBDIVISION"].dropna().astype(str).unique()) if "SUBDIVISION" in rain_df.columns else []
CROPS = sorted(agri_df["Crop"].dropna().unique()) if "Crop" in agri_df.columns else []
AGRI_YEARS = sorted(agri_df["Crop_Year"].dropna().unique()) if "Crop_Year" in agri_df.columns else []
RAIN_YEARS = sorted(rain_df["YEAR"].dropna().unique()) if "YEAR" in rain_df.columns else []

# -----------------------------------
# Helper functions (fuzzy matchers, extractors)
# -----------------------------------
def fuzzy_choice(name, choices, cutoff=0.6):
    if not name or not choices:
        return None
    matches = difflib.get_close_matches(name, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def extract_states(query):
    found = []
    qlow = query.lower()
    for s in sorted(STATES, key=lambda x: -len(x)):
        if s.lower() in qlow and s not in found:
            found.append(s)
            if len(found) >= 2:
                return found
    words = re.findall(r"[A-Za-z]+", query)
    for w in words:
        match = fuzzy_choice(w.title(), STATES, cutoff=0.75)
        if match and match not in found:
            found.append(match)
            if len(found) >= 2:
                return found
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
    for w in re.findall(r"[A-Za-z]+", query):
        match = fuzzy_choice(w.title(), CROPS, cutoff=0.75)
        if match:
            return match
    return None

def extract_top_m(query, default=3):
    m = re.search(r"top\s+(\d+)", query.lower())
    return int(m.group(1)) if m else default

def extract_last_n_years(query, default=3, limit=10):
    m = re.search(r"last\s+(\d+)", query.lower())
    n = int(m.group(1)) if m else default
    n = max(1, min(n, limit))
    years = sorted(set(AGRI_YEARS) | set(RAIN_YEARS))
    if not years:
        explicit = re.findall(r"(19|20)\d{2}", query)
        return [int(explicit[-1])] if explicit else []
    return sorted(years[-n:])

def extract_year_from_query(query):
    y = re.search(r"(19|20)\d{2}", query)
    return int(y.group(0)) if y else None

# -----------------------------------
# Core computations
# -----------------------------------
def compute_avg_rainfall_for_years(state, years):
    data = {}
    prov = []
    sub_match = fuzzy_choice(state.upper(), RAIN_SUBDIVS, cutoff=0.6)
    for y in years:
        val = None
        if sub_match and "SUBDIVISION" in rain_df.columns:
            subset = rain_df[(rain_df["SUBDIVISION"].astype(str).str.upper() == sub_match) & (rain_df["YEAR"] == y)]
            if not subset.empty:
                val = subset["ANNUAL"].astype(float).mean()
                prov.append(f"rain_df[(SUBDIVISION=='{sub_match}') & (YEAR=={y})]['ANNUAL']")
        if val is None:
            subset = rain_df[(rain_df["SUBDIVISION"].astype(str).str.contains(state, case=False, na=False)) & (rain_df["YEAR"] == y)]
            if not subset.empty:
                val = subset["ANNUAL"].astype(float).mean()
                prov.append(f"rain_df[SUBDIVISION contains '{state}' & YEAR=={y}]['ANNUAL']")
        data[y] = float(val) if val is not None else None
    return data, prov

def compute_top_crops_for_state_and_years(state, years, top_m=3):
    prov = []
    if "State" not in agri_df.columns:
        return pd.Series(dtype=float), prov
    subset = agri_df[agri_df["State"].astype(str).str.contains(state, case=False, na=False) & agri_df["Crop_Year"].isin(years)]
    prov.append(f"agri_df[State contains '{state}' & Crop_Year in {years}]")
    if subset.empty:
        return pd.Series(dtype=float), prov
    subset["Production"] = pd.to_numeric(subset["Production"], errors="coerce").fillna(0)
    top = subset.groupby("Crop")["Production"].sum().sort_values(ascending=False).head(top_m)
    return top, prov

# -----------------------------------
# Answer Assembly
# -----------------------------------
def answer_query(query):
    query = query.strip()
    if not query:
        return "Please type a question.", ""
    states = extract_states(query)
    crop = extract_crop(query)
    top_m = extract_top_m(query)
    years = extract_last_n_years(query)
    explicit_year = extract_year_from_query(query)
    if explicit_year:
        years = [explicit_year]

    parts, prov = [], []
    if len(states) >= 2:
        s1, s2 = states[0], states[1]
        rain1, p1 = compute_avg_rainfall_for_years(s1, years)
        rain2, p2 = compute_avg_rainfall_for_years(s2, years)
        parts.append(f"🌧️ **Rainfall comparison — {', '.join(map(str, years))}**")
        for y in years:
            parts.append(f"- {y}: {s1}: {rain1.get(y, 'N/A')} mm | {s2}: {rain2.get(y, 'N/A')} mm")
        prov += p1 + p2
        parts.append(f"\n🌾 **Top {top_m} crops comparison ({', '.join(map(str, years))})**")
        top1, ptop1 = compute_top_crops_for_state_and_years(s1, years, top_m)
        top2, ptop2 = compute_top_crops_for_state_and_years(s2, years, top_m)
        prov += ptop1 + ptop2
        if not top1.empty:
            parts.append(f"- **{s1}**: " + ", ".join([f"{idx} ({val:.1f} t)" for idx, val in top1.items()]))
        if not top2.empty:
            parts.append(f"- **{s2}**: " + ", ".join([f"{idx} ({val:.1f} t)" for idx, val in top2.items()]))
        return "\n".join(parts), {"provenance": prov}
    elif len(states) == 1:
        s = states[0]
        rain, p = compute_avg_rainfall_for_years(s, years)
        prov += p
        parts.append(f"🌧️ **Average annual rainfall for {s}**")
        for y in years:
            parts.append(f"- {y}: {rain.get(y, 'N/A')} mm")
        parts.append(f"\n🌾 **Top {top_m} crops in {s}**")
        top, ptop = compute_top_crops_for_state_and_years(s, years, top_m)
        prov += ptop
        if not top.empty:
            parts.append(" - " + ", ".join([f"{idx} ({val:.1f} tonnes)" for idx, val in top.items()]))
        return "\n".join(parts), {"provenance": prov}
    else:
        return "⚠️ Please include at least one state name in your question.", ""

# -----------------------------------
# Streamlit UI
# -----------------------------------
st.title("🌾 Project Samarth — Enhanced Agriculture & Rainfall Q&A")
st.caption("Ask natural-language questions about crop production and rainfall. Data is read from local files (simulating data.gov.in sources).")

st.markdown("**Example queries:**")
st.markdown("- Compare average annual rainfall in Tamil Nadu and Kerala for the last 3 years and list top 3 crops.")
st.markdown("- Top 5 crops in Maharashtra for the last 2 years.")
st.markdown("- Which district in Andhra Pradesh had the highest production of Rice in 2019?")
st.markdown("- Show average rainfall in Karnataka for 2015.")

query = st.text_input("💬 Your question", placeholder="Ex: Compare rainfall in Tamil Nadu and Kerala for the last 3 years")

if st.button("🔍 Get Answer") and query.strip():
    with st.spinner("Analyzing..."):
        answer, meta = answer_query(query)
    st.markdown(answer.replace("\n", "  \n"))
    if isinstance(meta, dict) and meta.get("provenance"):
        with st.expander("🧾 Provenance & Logic"):
            for p in meta["provenance"]:
                st.code(p)

st.markdown("---")
st.caption("📘 **Data source (local files):** `crop.xlsx` (Ministry of Agriculture style), `rainfall.csv` (IMD style). "
            "In production, data would be fetched from official [data.gov.in](https://data.gov.in) APIs for real-time updates.")
