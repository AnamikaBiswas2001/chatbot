import streamlit as st
import pandas as pd
import snowflake.connector
from docx import Document
from io import BytesIO
import difflib
import re
import json
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="RFP Chat Assistant", layout="wide")
st.title("🤖 AI Chat Assistant for RFP Labor Estimation")

# ----------------- Session Initialization -----------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "last_tab" not in st.session_state:
    st.session_state.last_tab = "💬 Chat Query"
if "doc_text" not in st.session_state:
    st.session_state.doc_text = ""

# ----------------- Data Loaders -----------------
@st.cache_data(ttl=600)
def load_keywords_from_snowflake():
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        df = pd.read_sql("SELECT DISTINCT task_keyword FROM standard_task_roles", conn)
        return df["TASK_KEYWORD"].dropna().str.lower().tolist()
    except Exception as e:
        st.error(f"Failed to load keywords: {e}")
        return []

@st.cache_data(ttl=600)
def load_faq_from_snowflake():
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        cursor = conn.cursor()
        cursor.execute("SELECT question, answer FROM chatbot_faq")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return pd.DataFrame(data, columns=["question", "answer"])
    except Exception as e:
        st.error(f"Failed to load chatbot FAQ: {e}")
        return pd.DataFrame(columns=["question", "answer"])

# ----------------- Text & Data Extraction -----------------
def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

def extract_structured_roles(text):
    pattern = re.compile(r"([A-Za-z ]+?)\s*-\s*Count:\s*(\d+)\s*-\s*Duration:\s*(\d+)\s*Days\s*-\s*Daily Rate:\s*\$(\d+)", re.IGNORECASE)
    matches = pattern.findall(text)
    roles = []
    for role, count, duration, rate in matches:
        roles.append({
            "role": role.strip(),
            "count": int(count),
            "duration_days": int(duration),
            "daily_rate": int(rate),
            "total_cost": int(count) * int(duration) * int(rate)
        })
    return pd.DataFrame(roles)

def extract_semantic_keyword(text, keyword_list):
    keyword_list = [kw.lower() for kw in keyword_list]
    corpus = keyword_list + [text.lower()]
    vectorizer = TfidfVectorizer().fit(corpus)
    vectors = vectorizer.transform(corpus)
    sim_scores = cosine_similarity(vectors[-1], vectors[:-1]).flatten()
    best_idx = sim_scores.argmax()
    return keyword_list[best_idx] if sim_scores[best_idx] > 0.2 else None

def fetch_roles_for_keyword(keyword):
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        query = f"""
            SELECT role, \"count\", duration_days, daily_rate
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
    total_cost = df["total_cost"].sum()
    st.success(f"💰 Total Estimated Cost: ${total_cost:,.2f}")
    st.dataframe(df[["role", "count", "duration_days", "daily_rate", "total_cost"]])
    return total_cost

# ----------------- App Tabs -----------------
keywords = load_keywords_from_snowflake()
faq_df = load_faq_from_snowflake()
tabs = st.tabs(["💬 Chat Query", "📄 Upload DOCX", "📚 Estimation History"])

# --- Chat Tab ---
with tabs[0]:
    st.subheader("💬 Ask a Question or Describe a Project")
    user_query = st.text_input("Enter your question or task description:")

    if user_query:
        keyword = extract_semantic_keyword(user_query, keywords)
        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                cost = display_estimate(df_roles)
                response = f"Estimated labor cost for **{keyword.title()}** is **${cost:,.2f}**."
            else:
                response = "No labor role matches found for the detected keyword."
        else:
            matches = difflib.get_close_matches(user_query.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
            if matches:
                response = faq_df.loc[faq_df["question"].str.lower() == matches[0], "answer"].values[0]
            else:
                response = "Sorry, I couldn't find a relevant answer. Please try again."

        st.session_state.chat_history.append((user_query, response))

    # Display chat history
    for user, assistant in st.session_state.chat_history:
        with st.chat_message("user"):
            st.markdown(user)
        with st.chat_message("assistant"):
            st.markdown(assistant)

# --- Upload DOCX Tab ---
with tabs[1]:
    st.subheader("📄 Upload RFP Document")
    doc_file = st.file_uploader("Upload a DOCX file", type="docx")
    if doc_file:
        raw_text = extract_text_from_docx(doc_file)
        st.text_area("Extracted Text", raw_text, height=200)
        structured_df = extract_structured_roles(raw_text)
        if not structured_df.empty:
            cost = display_estimate(structured_df)
        else:
            keyword = extract_semantic_keyword(raw_text, keywords)
            if keyword:
                df_roles = fetch_roles_for_keyword(keyword)
                if not df_roles.empty:
                    cost = display_estimate(df_roles)
                else:
                    st.warning("Could not match any labor roles from keyword.")
            else:
                st.warning("Could not detect any relevant keyword in the document.")

# --- History Tab ---
with tabs[2]:
    st.subheader("📚 Chat & Estimation History")
    if st.session_state.chat_history:
        for user, assistant in st.session_state.chat_history:
            st.markdown(f"**You:** {user}")
            st.markdown(f"**Assistant:** {assistant}")
    else:
        st.info("No history available.")
