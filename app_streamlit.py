import streamlit as st
import pandas as pd
import re
import difflib

# -----------------------------------
# Streamlit Page Config
# -----------------------------------
st.set_page_config(page_title="🌾 Project Samarth - Smart Agriculture Chatbot", layout="centered")

# -----------------------------------
# Dataset Paths
# -----------------------------------
AGRI_PATH = "crop.xlsx"        # Excel file (Agriculture)
RAINFALL_PATH = "rainfall.csv" # CSV file (Rainfall)

# -----------------------------------
# Load Datasets
# -----------------------------------
@st.cache_data
def load_data():
    try:
        agri = pd.read_excel(AGRI_PATH, engine='openpyxl')
    except Exception as e:
        st.error(f"Error reading {AGRI_PATH}: {e}")
        agri = pd.DataFrame()

    try:
        rain = pd.read_csv(RAINFALL_PATH, encoding='utf-8', on_bad_lines='skip')
    except Exception as e:
        st.error(f"Error reading {RAINFALL_PATH}: {e}")
        rain = pd.DataFrame()

    return agri, rain

agri_df, rain_df = load_data()

if agri_df.empty or rain_df.empty:
    st.warning("⚠️ One or both datasets failed to load. Please check file paths and formats.")
else:
    st.success("✅ Datasets loaded successfully!")

# Normalize column names
agri_df.columns = [c.strip().title() for c in agri_df.columns]
rain_df.columns = [c.strip().upper() for c in rain_df.columns]

# -----------------------------------
# Helper Functions
# -----------------------------------
STATES = sorted(agri_df['State'].dropna().unique())

def fuzzy_match_state(name):
    matches = difflib.get_close_matches(name, STATES, n=1, cutoff=0.6)
    return matches[0] if matches else None

def extract_state(query):
    for s in STATES:
        if s.lower() in query.lower():
            return s
    words = query.split()
    for w in words:
        match = fuzzy_match_state(w.title())
        if match:
            return match
    return None

def extract_crop(query):
    crops = agri_df['Crop'].dropna().unique()
    for c in crops:
        if c.lower() in query.lower():
            return c
    return None

def extract_year(query):
    year_match = re.search(r"(19|20)\d{2}", query)
    if year_match:
        return int(year_match.group(0))
    return int(agri_df['Crop_Year'].max())

def extract_top_n(query):
    match = re.search(r"top\s*(\d+)", query.lower())
    return int(match.group(1)) if match else 3

def detect_category(query):
    q = query.lower()
    if any(word in q for word in ["rain", "rainfall", "precipitation", "climate"]):
        return "rainfall"
    elif any(word in q for word in ["crop", "production", "yield", "harvest", "farm"]):
        return "crop"
    else:
        return "unknown"

# -----------------------------------
# Core Q&A Logic
# -----------------------------------
def answer_query(query):
    state = extract_state(query)
    crop = extract_crop(query)
    year = extract_year(query)
    top_n = extract_top_n(query)
    category = detect_category(query)

    if not state:
        return "⚠️ Please mention a valid state name (even approximately).", ""

    results = []
    provenance = []

    # 🌧️ RAINFALL LOGIC
    if category in ["rainfall", "unknown"] and not rain_df.empty:
        match = difflib.get_close_matches(state.upper(), rain_df['SUBDIVISION'].astype(str).unique(), n=1, cutoff=0.5)
        if match:
            sub = match[0]
            subset = rain_df[rain_df['SUBDIVISION'] == sub]
            subset = subset[subset['YEAR'] == year]
            if not subset.empty:
                avg_rain = subset['ANNUAL'].mean()
                results.append(f"🌧️ Average annual rainfall in **{state}** for **{year}**: {avg_rain:.2f} mm")
                provenance.append(f"rain_df[(SUBDIVISION=='{sub}') & (YEAR=={year})]['ANNUAL'].mean()")

    # 🌾 CROP LOGIC
    if category in ["crop", "unknown"] and not agri_df.empty:
        subset = agri_df[(agri_df["State"].str.contains(state, case=False, na=False)) &
                         (agri_df["Crop_Year"] == year)]
        if crop:
            subset = subset[subset["Crop"].str.contains(crop, case=False, na=False)]

        if not subset.empty:
            top_crops = (
                subset.groupby("Crop")["Production"]
                .sum()
                .sort_values(ascending=False)
                .head(top_n)
            )
            crops_str = ", ".join([f"{c} ({p:.1f} tonnes)" for c, p in top_crops.items()])
            results.append(f"🌾 Top {top_n} crops in **{state}** for {year}: {crops_str}")
            if crop:
                provenance.append(f"agri_df[(State contains '{state'}) & (Crop=='{crop}') & (Crop_Year=={year})]")
            else:
                provenance.append(f"agri_df[(State contains '{state'}) & (Crop_Year=={year})].groupby('Crop')['Production'].sum().head({top_n})")

    if not results:
        return "❌ No matching records found in datasets. Try a different year or state name.", ""

    final_answer = "\n\n".join(results)
    prov_text = "\n".join([f"```python\n{p}\n```" for p in provenance])

    return final_answer, prov_text

# -----------------------------------
# STREAMLIT UI
# -----------------------------------
st.title("🌾 Project Samarth — Smart Agriculture & Rainfall Chatbot")
st.caption("Ask about rainfall, crop production, or yield. Type naturally — AI will interpret it!")

query = st.text_input("💬 Your Question:", placeholder="Ex: Which crops performed best in Telangana 2019?")

if st.button("🔍 Get Answer") and query.strip():
    with st.spinner("Thinking..."):
        ans, prov = answer_query(query)
        st.markdown(ans)
        if prov:
            with st.expander("🧩 Logic & Provenance"):
                st.markdown(prov)

st.markdown("---")
st.markdown("💡 **Try asking:**")
st.markdown("- Show rainfall in Telangana for 2015")
st.markdown("- Top 5 crops in Maharashtra for 2019")
st.markdown("- Compare rainfall in Tamil Nadu and Kerala for 2011")
st.markdown("- Which crop produced the most in Andhra Pradesh 2017?")
st.markdown("- What is the average rainfall in Karnataka?")

