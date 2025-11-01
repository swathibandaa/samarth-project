import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Project Samarth - Smart Agri Q&A", layout="centered")

# File paths
AGRI_PATH = "crop.xlsx"
RAINFALL_PATH = "rainfall.csv"

@st.cache_data
def load_data():
    try:
        agri = pd.read_excel(AGRI_PATH, engine="openpyxl")
        rain = pd.read_csv(RAINFALL_PATH, encoding="utf-8", on_bad_lines="skip")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

    # Clean column names and values
    agri.columns = agri.columns.str.strip().str.title()
    rain.columns = rain.columns.str.strip().str.upper()

    if "State" in agri.columns:
        agri["State"] = agri["State"].str.strip().str.title()
    if "Crop" in agri.columns:
        agri["Crop"] = agri["Crop"].str.strip().str.title()
    if "Subdivision" in rain.columns:
        rain["Subdivision"] = rain["Subdivision"].str.strip().str.title()
    return agri, rain

agri_df, rain_df = load_data()

if agri_df is None or rain_df is None:
    st.stop()

STATES = sorted(agri_df['State'].dropna().unique())
CROPS = sorted(agri_df['Crop'].dropna().unique())

def fuzzy_match(word, choices):
    """Return best fuzzy match if word is close enough"""
    match = difflib.get_close_matches(word, choices, n=1, cutoff=0.6)
    return match[0] if match else None

def detect_intent(query):
    """Detect what user is asking: rainfall, top crops, yield, etc."""
    q = query.lower()
    if "rain" in q:
        return "rainfall"
    elif "crop" in q or "production" in q:
        return "crop"
    elif "yield" in q:
        return "yield"
    else:
        return "unknown"

def answer_query(query):
    intent = detect_intent(query)
    top_n = int(re.search(r"top\s*(\d+)", query.lower()).group(1)) if re.search(r"top\s*(\d+)", query.lower()) else 3
    year = int(re.search(r"(20\d{2})", query).group(1)) if re.search(r"(20\d{2})", query) else int(agri_df["Crop_Year"].max())

    # Try to identify states and crops
    states = []
    for word in query.split():
        match = fuzzy_match(word.title(), STATES)
        if match and match not in states:
            states.append(match)

    crop_match = None
    for word in query.split():
        match = fuzzy_match(word.title(), CROPS)
        if match:
            crop_match = match
            break

    if not states:
        return "⚠️ Couldn't identify any state. Try including a valid state name like Telangana or Kerala.", ""

    ans_lines, provenance = [], []

    if intent == "rainfall":
        for s in states:
            sub_match = fuzzy_match(s, rain_df["SUBDIVISION"].astype(str).unique())
            if sub_match:
                subset = rain_df[rain_df["SUBDIVISION"] == sub_match]
                subset = subset[subset["YEAR"].between(year-2, year)]
                if not subset.empty:
                    avg = subset["ANNUAL"].mean()
                    ans_lines.append(f"🌧️ Average rainfall in **{s}** (last 3 years): {avg:.2f} mm")
                    provenance.append(f"Rainfall data → SUBDIVISION: {sub_match}, Years: {year-2}-{year}")
    elif intent == "crop":
        for s in states:
            subset = agri_df[(agri_df["State"] == s) & (agri_df["Crop_Year"] == year)]
            if subset.empty:
                continue
            top = subset.groupby("Crop")["Production"].sum().sort_values(ascending=False).head(top_n)
            if not top.empty:
                crops_str = ", ".join([f"{c} ({p:.1f} tonnes)" for c, p in top.items()])
                ans_lines.append(f"🌾 Top {top_n} crops in **{s}** for {year}: {crops_str}")
                provenance.append(f"Agriculture data → State: {s}, Year: {year}")
    elif intent == "yield":
        for s in states:
            subset = agri_df[(agri_df["State"] == s) & (agri_df["Crop_Year"] == year)]
            if not subset.empty:
                avg_yield = subset["Yield"].mean()
                ans_lines.append(f"📈 Average yield in **{s}** for {year}: {avg_yield:.2f} tonnes/hectare")
                provenance.append(f"Agriculture data → State: {s}, Year: {year}")
    else:
        ans_lines.append("🤖 I couldn’t understand your question. Try asking about rainfall, crop production, or yield.")

    if not ans_lines:
        return "❌ No matching records found in datasets. Try a different year or state name.", ""

    final = "\n\n".join(ans_lines)
    prov = "\n\n".join(provenance)
    return final, prov

# --- UI ---
st.title("🌾 Project Samarth — Smart Agriculture & Rainfall Q&A")
st.caption("Ask about rainfall, crop production, or yield. Type naturally — AI will interpret it!")

query = st.text_input("💬 Your Question:", placeholder="e.g., Top 5 crops in Tamil Nadu for 2018 or Rainfall in Telangana 2019-2021")

if st.button("Get Answer") and query.strip():
    with st.spinner("🔍 Analyzing your query..."):
        ans, prov = answer_query(query)
        st.markdown(ans)
        if prov:
            with st.expander("📊 Data Provenance"):
                st.text(prov)
