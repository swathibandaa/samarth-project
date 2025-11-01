import pandas as pd
import difflib

# Load both datasets
crop_data = pd.read_excel("crop_production.xlsx")   # Your crop dataset
rain_data = pd.read_csv("rainfall_data.csv")        # Your rainfall dataset

# Normalize column names
crop_data.columns = crop_data.columns.str.strip().str.lower()
rain_data.columns = rain_data.columns.str.strip().str.lower()

def find_close_match(word, possibilities):
    """Finds the closest match even if user misspells (fuzzy match)."""
    matches = difflib.get_close_matches(word.lower(), [str(p).lower() for p in possibilities], n=1, cutoff=0.6)
    return matches[0] if matches else None

def answer_query(query):
    query = query.lower()

    # Detect if the user is asking about rainfall or crops
    if "rain" in query:
        dataset = rain_data
        category = "rainfall"
    elif any(word in query for word in ["crop", "production", "yield", "output", "top"]):
        dataset = crop_data
        category = "crop"
    else:
        return "❌ I couldn't detect whether you're asking about rainfall or crop data."

    # Identify possible states and years
    states = dataset['state'].dropna().unique()
    years = dataset['year'].dropna().astype(str).unique()

    state = next((s for s in states if s.lower() in query), None)
    year = next((y for y in years if y in query), None)

    # Fuzzy match if spelling is slightly wrong
    if not state:
        words = query.split()
        for w in words:
            close = find_close_match(w, states)
            if close:
                state = close
                break

    if not year:
        for w in query.split():
            close = find_close_match(w, years)
            if close:
                year = close
                break

    if not state or not year:
        return "❌ Couldn't identify a valid state or year from your question."

    # Logic for rainfall dataset
    if category == "rainfall":
        row = dataset[(dataset['state'].str.lower() == state.lower()) & (dataset['year'].astype(str) == str(year))]
        if not row.empty:
            rainfall_value = row.iloc[0]['annual rainfall'] if 'annual rainfall' in row.columns else row.iloc[0]['rainfall']
            return f"🌧️ Average annual rainfall in {state} for {year}: {rainfall_value} mm"
        else:
            return f"❌ No rainfall data found for {state} in {year}."

    # Logic for crop dataset
    elif category == "crop":
        rows = dataset[(dataset['state'].str.lower() == state.lower()) & (dataset['year'].astype(str) == str(year))]
        if rows.empty:
            return f"❌ No crop data found for {state} in {year}."

        # Sort by production to find top crops
        top_crops = rows.sort_values(by='production', ascending=False).head(3)
        top_list = ", ".join([f"{row['crop']} ({row['production']} tonnes)" for _, row in top_crops.iterrows()])
        return f"🌾 Top 3 crops in {state} for {year}: {top_list}"

# --- TEST EXAMPLES ---
print(answer_query("Show rainfall in Telangana for 2019"))
print(answer_query("Top 5 crops in Telangana for 2017"))
print(answer_query("Compare rainfall in Maharashtra and Karnataka for last 3 years"))
print(answer_query("Show crop yield in Tamil Nadu for 2020"))
