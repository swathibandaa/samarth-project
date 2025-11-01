import streamlit as st
import pandas as pd

# 🌾 Load datasets
rainfall_data = pd.read_csv("rainfall_data.csv")
crop_data = pd.read_excel("crop_production.xlsx")

# 🌦️ Chatbot UI
st.title("🌾 Project Samarth — Smart Agriculture & Rainfall Q&A")
st.markdown("Ask about rainfall, crop production, or yield. Type naturally — AI will interpret it!")

# 💬 User input
user_query = st.text_input("💬 Ask your question here:")

# Helper function: clean text
def clean_text(text):
    return text.strip().lower()

# Helper: extract year if mentioned
import re
def extract_year(query):
    match = re.search(r'\b(19|20)\d{2}\b', query)
    return int(match.group()) if match else None

# 🧠 Main chatbot logic
if user_query:
    query = clean_text(user_query)
    year = extract_year(query)

    # Check for Karnataka subregions
    if "karnataka" in query and all(x not in query for x in ["coastal", "north", "south"]):
        st.warning("Did you mean: 'Coastal Karnataka', 'North Interior Karnataka', or 'South Interior Karnataka'?")
    else:
        # 🌧️ Rainfall queries
        if "rainfall" in query:
            state = None
            for s in rainfall_data["State"].unique():
                if s.lower() in query:
                    state = s
                    break

            if year:
                if year > 2015:
                    st.error("❌ Data unavailable: Rainfall data is only available up to 2015.")
                elif state:
                    result = rainfall_data[(rainfall_data["State"] == state) & (rainfall_data["Year"] == year)]
                    if not result.empty:
                        avg_rain = result["Rainfall"].mean()
                        st.success(f"🌧️ Average rainfall in {state} for {year}: **{avg_rain:.2f} mm**")
                    else:
                        st.error(f"❌ No data found for {state} in {year}.")
                else:
                    st.error("❌ Please specify a valid state name.")
            else:
                st.error("❌ Please include a year in your question (e.g., 2015).")

        # 🌾 Crop production queries
        elif "crop" in query or "production" in query or "yield" in query or "top" in query:
            state = None
            for s in crop_data["State"].unique():
                if s.lower() in query:
                    state = s
                    break

            if year:
                if year > 2019:
                    st.error("❌ Data unavailable: Crop data is only available up to 2019.")
                elif state:
                    result = crop_data[(crop_data["State"] == state) & (crop_data["Year"] == year)]
                    if not result.empty:
                        top_crops = result.groupby("Crop")["Production"].sum().nlargest(5)
                        crops_str = ", ".join([f"{crop} ({prod:.0f} tonnes)" for crop, prod in top_crops.items()])
                        st.success(f"🌾 Top 5 crops in {state} for {year}: {crops_str}")
                    else:
                        st.error(f"❌ No data found for {state} in {year}.")
                else:
                    st.error("❌ Please specify a valid state name.")
            else:
                st.error("❌ Please include a year in your question (e.g., 2019).")

        # ❓ Fallback
        else:
            st.info("🤖 Sorry, I couldn't understand that. Try asking about rainfall or crops with a year (e.g., 'Show rainfall in Tamil Nadu for 2015').")

# 💡 Example prompts
st.markdown("### 💡 **Try asking:**")
st.markdown("- Show rainfall in Telangana for 2015")
st.markdown("- Top 5 crops in Maharashtra for 2019")
st.markdown("- Compare rainfall in Tamil Nadu and Kerala for 2013")
