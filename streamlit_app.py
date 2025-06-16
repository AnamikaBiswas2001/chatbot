import streamlit as st
import pandas as pd
import snowflake.connector
from docx import Document
from io import BytesIO
import difflib
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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
        return df["TASK_KEYWORD"].dropna().str.lower().tolist()
    except Exception as e:
        st.error(f"Failed to load keywords: {e}")
        return []

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

def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

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
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"]
        )
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
    st.markdown("### 📊 Estimated Labor Cost")
    st.dataframe(df[["role", "count", "duration_days", "daily_rate", "total_cost"]])
    st.success(f"💰 Total Estimated Cost: ${df['total_cost'].sum():,.2f}")

def extract_proposal_requirements(text):
    match = re.search(r"Proposal Requirements:\s*(.*?)\s*(Submission Deadline:|Contact for Clarifications:|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        lines = [line.strip("-• ").strip() for line in raw.split("\n") if line.strip()]
        return lines
    return []

def extract_proposal_requirements(text):
    match = re.search(r"Proposal Requirements:\s*(.*?)\s*(Submission Deadline:|Contact for Clarifications:|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        return [line.strip("-• ").strip() for line in raw.split("\n") if line.strip()]
    return []

def extract_project_info(text):
    info = {
        "Project Title": "",
        "Client": "",
        "Location": "",
        "Estimated Duration": "",
        "Start Date": "",
        "Scope of Work": ""
    }

    patterns = {
        "Project Title": r"Project Title:\s*(.*)",
        "Client": r"Client:\s*(.*)",
        "Location": r"Location:\s*(.*)",
        "Estimated Duration": r"Estimated Duration:\s*(.*)",
        "Start Date": r"Start Date:\s*(.*)",
        "Scope of Work": r"Scope of Work:\s*(.*?)(Proposal Requirements:|Submission Deadline:|Contact for Clarifications:|$)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            info[key] = match.group(1).strip().replace("\n", " ")
    return info


# ----------------- Main App -----------------
keywords = load_keywords_from_snowflake()
faq_df = load_faq_from_snowflake()

tab1, tab2 = st.tabs(["💬 Chat Query", "📄 Upload DOCX"])

with tab1:
    user_input = st.text_input("Enter project-related question or task description:")
    if user_input:
        keyword = extract_semantic_keyword(user_input, keywords)

        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                display_estimate(df_roles)
            else:
                st.warning("No matching labor roles found.")
        else:
            matches = difflib.get_close_matches(user_input.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
            if matches:
                match = matches[0]
                response = faq_df.loc[faq_df["question"].str.lower() == match, "answer"].values[0]
                st.markdown(f"**Answer:** {response}")
            else:
                st.warning("Sorry, I couldn't understand that question.")

with tab2:
    doc_file = st.file_uploader("Upload a DOCX RFP file", type=["docx"])
    if doc_file:
        text = extract_text_from_docx(doc_file)
        st.text_area("📜 Extracted RFP Text", text, height=250)

        project_info = extract_project_info(text)

        # Display project info summary
        st.subheader("📋 Project Information")
        for key, value in project_info.items():
            if value:
                st.markdown(f"**{key}:** {value}")


        keyword = extract_semantic_keyword(text, keywords)
        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                display_estimate(df_roles)

                st.markdown("---")
                st.markdown("### 📝 Responses to Proposal Requirements")
                requirements = extract_proposal_requirements(text)
                if requirements:
                    st.subheader("📌 Proposal Requirements & Responses")
                    for req in requirements:
                        st.markdown(f"**• {req}**")
                        match = difflib.get_close_matches(req.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
                        if match:
                            answer = faq_df.loc[faq_df["question"].str.lower() == match[0], "answer"].values[0]
                            st.markdown(f"✅ {answer}")
                        else:
                            st.markdown("❓ This requirement will be addressed in the proposal.")

            else:
                st.warning("No roles found in the database for the detected keyword.")
        else:
            st.warning("Could not detect project keyword from the document.")
