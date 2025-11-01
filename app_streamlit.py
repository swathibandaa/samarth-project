import streamlit as st
import pandas as pd
import re
import difflib

# -----------------------------------
# Streamlit Page Config
# -----------------------------------
st.set_page_config(page_title="Project Samarth - Agriculture & Climate Insights", layout="centered")

# -----------------------------------
# Dataset Paths
# -----------------------------------
AGRI_PATH = "crop.xlsx"       # Excel file
RAINFALL_PATH = "rainfall.csv"  # CSV file

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
    # Normalize column names (trim spaces)
    agri_df.columns = [c.strip() for c in agri_df.columns]
    rain_df.columns = [c.strip() for c in rain_df.columns]

    # -----------------------------------
    # Helper Functions
    # -----------------------------------
    STATES = sorted(agri_df['State'].dropna().unique())

    def fuzzy_match_state(name):
        matches = difflib.get_close_matches(name, STATES, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def extract_states(query):
        found = []
        for s in STATES:
            if s.lower() in query.lower():
                found.append(s)
        if not found:
            tokens = re.findall(r"[A-Z][a-z]+", query)
            for t in tokens:
                match = fuzzy_match_state(t)
                if match:
                    found.append(match)
        return list(set(found))

    def extract_crop(query):
        crops = agri_df['Crop'].dropna().unique()
        for c in crops:
            if c.lower() in query.lower():
                return c
        return None

    def extract_top_n(query):
        m = re.search(r"top\s*(\d+)", query.lower())
        return int(m.group(1)) if m else 3

    def extract_year(query):
        years = re.findall(r"(20\d{2})", query)
        if years:
            return int(years[-1])
        return int(agri_df["Crop_Year"].max())

    # -----------------------------------
    # Core Q&A Logic
    # -----------------------------------
    def answer_query(query):
        states = extract_states(query)
        crop = extract_crop(query)
        top_n = extract_top_n(query)
        year = extract_year(query)

        if not states:
            return "⚠️ Please mention at least one state in your query.", ""

        answer_lines = []
        provenance = []

        # ----- RAINFALL DATA -----
        if not rain_df.empty and "SUBDIVISION" in rain_df.columns:
            for s in states:
                sub_match = difflib.get_close_matches(s, rain_df["SUBDIVISION"].astype(str), n=1, cutoff=0.5)
                if sub_match:
                    sub = sub_match[0]
                    subset = rain_df[rain_df["SUBDIVISION"] == sub]
                    subset = subset[subset["YEAR"].between(year-2, year)]
                    if not subset.empty and "ANNUAL" in subset.columns:
                        avg_rain = subset["ANNUAL"].mean()
                        answer_lines.append(f"🌧️ Average annual rainfall in **{s}** (last 3 years): {avg_rain:.2f} mm")
                        provenance.append({
                            "dataset": "rainfall_data.csv",
                            "filter": f"SUBDIVISION == '{sub}', YEAR in [{year-2}..{year}]",
                            "code": f"rain_df[(rain_df['SUBDIVISION']=='{sub}') & (rain_df['YEAR'].between({year-2},{year}))]['ANNUAL'].mean()"
                        })

        # ----- AGRICULTURE DATA -----
        if not agri_df.empty:
            for s in states:
                subset = agri_df[(agri_df["State"].str.contains(s, case=False, na=False)) &
                                (agri_df["Crop_Year"] == year)]
                if subset.empty:
                    continue

                # Top crops by production
                top_crops = (
                    subset.groupby("Crop")["Production"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(top_n)
                )
                crops_str = ", ".join([f"{c} ({p:.1f} tonnes)" for c, p in top_crops.items()])
                answer_lines.append(f"🌾 Top {top_n} crops in **{s}** for {year}: {crops_str}")
                provenance.append({
                    "dataset": "crop_data.xlsx",
                    "filter": f"State == '{s}', Crop_Year == {year}",
                    "code": f"agri_df[(agri_df['State'].str.contains('{s}')) & (agri_df['Crop_Year']=={year})].groupby('Crop')['Production'].sum().sort_values(ascending=False).head({top_n})"
                })

        if not answer_lines:
            return "❌ No relevant data found for your query.", ""

        final_answer = "\n\n".join(answer_lines)

        prov_block = "\n\n".join([
            f"**Dataset:** {p['dataset']}\nFilter → {p['filter']}\n```python\n{p['code']}\n```"
            for p in provenance
        ])
        return final_answer, prov_block

    # -----------------------------------
    # STREAMLIT UI
    # -----------------------------------
    st.title("🌾 Project Samarth — Agriculture & Climate Q&A")
    st.caption("Ask questions about crop production and rainfall. Answers are based on Indian government datasets.")

    query = st.text_input(
        "💬 Ask your question here:",
        placeholder="Compare rainfall in Telangana and Tamil Nadu for 3 years and top 2 crops by production"
    )

    if st.button("Get Answer") and query.strip():
        with st.spinner("Analyzing your query..."):
            ans, prov = answer_query(query)
            st.markdown(ans)
            if prov:
                with st.expander("🔍 Provenance — data sources and logic used"):
                    st.markdown(prov)

    # -----------------------------------
    # Examples
    # -----------------------------------
    st.markdown("---")
    st.markdown("### 💡 Try these:")
    st.markdown("""
    - Compare rainfall in Maharashtra and Karnataka for last 3 years and top 3 crops  
    - Show top 5 crops in Telangana for 2017  
    - Compare average rainfall between Tamil Nadu and Kerala  
    - Find production of Rice in Andhra Pradesh for 2019  
    """)

    # Optional: Display datasets
    st.markdown("---")
    with st.expander("📊 View Raw Datasets"):
        st.write("**Agriculture Data Preview**")
        st.dataframe(agri_df.head())
        st.write("**Rainfall Data Preview**")
        st.dataframe(rain_df.head())
