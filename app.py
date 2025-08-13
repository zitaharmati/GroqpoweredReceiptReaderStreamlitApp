import streamlit as st
import base64
import json
import pandas as pd
import re
from groq import Groq, AuthenticationError
from io import StringIO, BytesIO

def get_info_df(df):
    buffer = StringIO()
    df.info(buf=buffer)
    info_str = buffer.getvalue()
  
    lines = info_str.split('\n')
    rows = []
    for line in lines[5:-2]:  
        parts = line.split()
        row = [parts[0], parts[1], " ".join(parts[2:])]
        rows.append(row)

    info_df = pd.DataFrame(rows, columns=["Index", "Non-Null Count", "Dtype"])
    return info_df

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Sheet1')
    processed_data = output.getvalue()
    return processed_data

@st.cache_data(show_spinner="🔍 Processing receipt...", ttl=3600)
def process_receipt(image_bytes, api_key, expected_items):

    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    prompt_text = """Extract the following receipt details from the provided text response and return them as a structured JSON object. Return only JSON, no extra text or explanations

    Fields to extract:
    - Company
    - Date
    - Items (Description, Quantity, Unit Price, Total)
    - Deduction 
    - Total
    - ProductType one of the following categories: food, alcoholic drink, petrol, drugstore product, cloth, electric device, medicine, other. If not identified use "unknown".
    """
    if expected_items > 0:
        prompt_text += f"""
    IMPORTANT: There are exactly {expected_items} items in the receipt. 
    Do not infer or hallucinate additional items. 
    Return exactly {expected_items} items in the 'Items' field of the JSON.
    """

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

    result_str = response.choices[0].message.content
    match = re.search(r'\{.*\}', result_str, re.DOTALL)
    if not match:
        raise ValueError("No valid JSON found in model response.")

    result_json = json.loads(match.group(0))
    return result_json


# --- UI ---
st.title("🧾 Receipt Data Extractor (Groq-powered)")

with st.sidebar:
    st.markdown("""
    <div style="background-color: #f8f0f5; padding: 15px; border-radius: 10px; border: 1px solid #e0cfe3;">
        <h4 style="color: #d6336c;">📘 App Usage Guide</h4>
        <ol style="padding-left: 20px; color: #333;">
            <li>📸 Take a good quality photo of the receipt</li>
            <li>✂️ Crop the receipt to remove background clutter</li>
            <li>🔑 Insert your Groq API key</li>
            <li>📤 Upload your photo</li>
            <li>🔢 If extraction is not correct:</li>
                <ul style="padding-left: 20px; margin-top: 5px;">
                <li>Try adding the expected number of items</li>
                <li>Upload a clearer or better-cropped photo</li>
                </ul>
            <li>📥 Download items list and summary as Excel files</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<p style="font-size:1.3rem; font-weight:bold;">🔑 Enter your Groq API Key</p>', unsafe_allow_html=True)
api_key = st.text_input("Groq API Key", type="password", label_visibility="collapsed")
st.caption("Your key should start with 'gsk_' and be valid for Groq API access.")

st.markdown('<p style="font-size:1.3rem; font-weight:bold;"></p>', unsafe_allow_html=True)
st.markdown('<p style="font-size:1.3rem; font-weight:bold;">📤 Upload a receipt image - Make sure your photo is clear and the receipt is well-cropped</p>', unsafe_allow_html=True)

image_file = st.file_uploader("Upload image", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
st.markdown('<p style="font-size:1.3rem; font-weight:bold;"></p>', unsafe_allow_html=True)
st.markdown('<p style="font-size:1.3rem; font-weight:bold;">🔢 Expected number of items (optional, if data extraction is not correct)</p>', unsafe_allow_html=True)

expected_items = st.number_input("Expected Items", min_value=0, step=1, label_visibility="collapsed")

if image_file and api_key:
    st.image(image_file, caption="Uploaded Receipt", use_container_width=True)

    try:
        image_bytes = image_file.read()
        result_json = process_receipt(image_bytes, api_key, expected_items)

        items_df = pd.DataFrame(result_json["Items"])
        total_without_discount = items_df["Total"].sum()
        summary_df = pd.DataFrame([{
            "Company": result_json.get("Company", "Unknown"),
            "Date": result_json.get("Date", "Unknown"),
            "Discount": total_without_discount - result_json["Total"],
            "Total": result_json.get("Total", "Unknown"),
        }])

        # Display and download logic remains unchanged
        st.subheader("📋 Summary")
        st.dataframe(summary_df)
        st.download_button(
            label="Download summary as Excel",
            data=convert_df_to_excel(summary_df),
            file_name='summary.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        st.subheader("🛒 Items")
        st.dataframe(items_df)
        try:
            grouped = items_df.groupby("ProductType")["Total"].sum().reset_index()
            st.subheader("📊 Total by Product Type")
            st.dataframe(grouped)
            st.bar_chart(grouped.set_index("ProductType"))
        except Exception:
            st.warning("⚠️ Could not generate chart by Product type")

        st.download_button(
            label="Download items as Excel",
            data=convert_df_to_excel(items_df),
            file_name='items.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except AuthenticationError:
        st.error("🚫 Invalid API key. Please check your Groq key and try again.")
        st.stop()
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        st.error("🚫 Receipt processing failed. Please upload a clearer image.")
