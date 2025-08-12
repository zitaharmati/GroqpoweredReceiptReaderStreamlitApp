import streamlit as st
import base64
import json
import pandas as pd
import re
from groq import Groq

# --- UI ---
st.title("🧾 Receipt Data Extractor (Groq-powered)")

api_key = st.text_input("🔑 Enter your Groq API Key", type="password")
image_file = st.file_uploader("📤 Upload a receipt image", type=["jpg", "jpeg", "png"])
expected_items = st.number_input("🔢 Expected number of items (optional)", min_value=0, step=1)

if image_file and api_key:
    # Encode image
    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

    # Build prompt
    prompt_text = """Extract the following receipt details from the provided text response and return them as a structured JSON object. Return only JSON, no extra text or explanations

Fields to extract:
- Company
- Date
- Items (Description, Quantity, Unit Price, Total)
- Deduction 
- Total
- ProductType one of the following categories: food, alcoholic drink, petrol, drugstore product, clothing, medicine, other (if identified as other or if not identified)
"""
    if expected_items > 0:
        prompt_text += f"""
IMPORTANT: There are exactly {expected_items} items in the receipt. 
Do not infer or hallucinate additional items. 
Return exactly {expected_items} items in the 'Items' field of the JSON.
"""

    # Call Groq model
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        model="meta-llama/llama-4-scout-17b-16e-instruct",
    )

    # Extract and clean JSON from response
    result_str = response.choices[0].message.content

    match = re.search(r'\{.*\}', result_str, re.DOTALL)
    if not match:
        st.error(" No valid JSON found in model response.")
    else:
        try:
            result_json = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            st.error(f" JSON decoding failed: {e}")
            st.code(match.group(0), language="json")

    # Create DataFrames
    items_df = pd.DataFrame(result_json["Items"])
    total_without_discount = items_df["Total"].sum()
    summary_df = pd.DataFrame([{
        "Company": result_json["Company"],
        "Date": result_json["Date"],
        "Discount":  total_without_discount - result_json["Total"],
        "Total": result_json["Total"],
    }])

    st.subheader("📋 Summary")
    st.dataframe(summary_df)

    st.subheader("🛒 Items")
    st.dataframe(items_df)