import streamlit as st
import pandas as pd
import snowflake.connector
from docx import Document
from io import BytesIO
import difflib

# ----------------- Streamlit Config -----------------
st.set_page_config(page_title="RFP Chat Assistant", layout="wide")
st.title("🤖 AI Chat Assistant for RFP Labor Estimation")

# ----------------- Helper Functions -----------------
@st.cache_data(ttl=600)
def load_keywords_from_snowflake():
    try:
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"]
        )
        df = pd.read_sql("SELECT DISTINCT task_keyword FROM standard_task_roles", conn)
        return df["TASK_KEYWORD"].str.lower().tolist()
    except Exception as e:
        st.error(f"Failed to load keywords: {e}")
        return []

def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

def extract_keyword(text, keyword_list):
    text_lower = text.lower()
    for kw in keyword_list:
        if kw in text_lower:
            return kw
    matches = difflib.get_close_matches(text_lower, keyword_list, n=1, cutoff=0.3)
    return matches[0] if matches else None

def fetch_roles_for_keyword(keyword):
    try:
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"]
        )
        query = f"""
            SELECT role, "count", duration_days, daily_rate
            FROM standard_task_roles
            WHERE LOWER(task_keyword) = '{keyword.lower()}'
        """
        df = pd.read_sql(query, conn)
        if not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df["total_cost"] = df["count"] * df["duration_days"] * df["daily_rate"]
        return df
    except Exception as e:
        st.error(f"❌ Failed to fetch roles: {e}")
        return pd.DataFrame()

def display_estimate(df):
    st.markdown("### 📊 Estimated Labor Cost")
    st.dataframe(df[["role", "count", "duration_days", "daily_rate", "total_cost"]])
    st.success(f"💰 Total Estimated Cost: ${df['total_cost'].sum():,.2f}")

@st.cache_data(ttl=600)
def load_faq_from_snowflake():
    try:
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"]
        )
        cursor = conn.cursor()
        cursor.execute("SELECT question, answer FROM chatbot_faq")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return pd.DataFrame(data, columns=["question", "answer"])
    except Exception as e:
        st.error(f"Failed to load chatbot FAQ: {e}")
        return pd.DataFrame(columns=["question", "answer"])

def answer_question_with_fallback(text, keyword_list, faq_df):
    keyword = extract_keyword(text, keyword_list)
    if keyword:
        df = fetch_roles_for_keyword(keyword)
        if not df.empty:
            total = df["total_cost"].sum()
            rows = "\n".join([
                f"| {r['role']} | {r['count']} | {r['duration_days']} | ${r['daily_rate']} | ${r['total_cost']:,.2f} |"
                for _, r in df.iterrows()
            ])
            return (
                "Estimated Labor Cost Breakdown:\n\n"
                "| Role | Count | Duration (Days) | Daily Rate | Total Cost |\n"
                "|------|-------|------------------|-------------|-------------|\n"
                f"{rows}\n\n"
                f"**Total Estimated Cost:** ${total:,.2f}"
            )

    matches = difflib.get_close_matches(text.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
    if matches:
        match = matches[0]
        return faq_df.loc[faq_df["question"].str.lower() == match, "answer"].values[0]
    else:
        return "Sorry, I couldn't understand that question."

# ----------------- UI: Text or File Input -----------------
keywords = load_keywords_from_snowflake()
faq_df = load_faq_from_snowflake()

tab1, tab2 = st.tabs(["💬 Chat Query", "📄 Upload DOCX"])

with tab1:
    user_input = st.text_input("Enter project-related question or task description:")
    if user_input:
        response = answer_question_with_fallback(user_input, keywords, faq_df)
        st.markdown(response)

with tab2:
    doc_file = st.file_uploader("Upload a DOCX RFP file", type=["docx"])
    if doc_file:
        text = extract_text_from_docx(doc_file)
        st.text_area("📜 Extracted RFP Text", text, height=250)
        response = answer_question_with_fallback(text, keywords, faq_df)
        st.markdown(response)
