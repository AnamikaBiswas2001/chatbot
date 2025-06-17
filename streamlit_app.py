import streamlit as st
import pandas as pd
import snowflake.connector
from docx import Document
from io import BytesIO
import difflib
import re
import numpy as np
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="RFP Chat Assistant", layout="wide")
st.title("🤖 AI Chat Assistant for RFP Labor Estimation")

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
    st.markdown("### 📊 Estimated Labor Cost")
    st.dataframe(df[["role", "count", "duration_days", "daily_rate", "total_cost"]])
    st.success(f"💰 Total Estimated Cost: ${df['total_cost'].sum():,.2f}")

def extract_proposal_requirements(text):
    match = re.search(r"Proposal Requirements:\s*(.*?)\s*(Submission Deadline:|Contact for Clarifications:|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        return [line.strip("-• ").strip() for line in raw.split("\n") if line.strip()]
    return []

def extract_project_info(text):
    info = {}
    fields = ["Project Title", "Client", "Location", "Estimated Duration", "Start Date", "Scope of Work"]
    for field in fields:
        pattern = rf"{field}:\s*(.*?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info[field] = match.group(1).strip()
    return info

def convert_df_for_json_storage(df):
    return json.dumps([
        {k: (int(v) if isinstance(v, (np.integer,)) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ])

def save_estimation_to_history(project_title, total_cost, roles_df):
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        cursor = conn.cursor()
        details_json = convert_df_for_json_storage(roles_df)
        insert_sql = """
            INSERT INTO rfp_estimation_history (project_title, estimated_cost, details_json, timestamp)
            VALUES (%s, %s, PARSE_JSON(%s), CURRENT_TIMESTAMP)
        """
        cursor.execute(insert_sql, (project_title, float(total_cost), details_json))
        cursor.close()
        conn.close()
    except Exception as e:
        st.warning(f"⚠️ Failed to save estimation history: {e}")

keywords = load_keywords_from_snowflake()
faq_df = load_faq_from_snowflake()

page = st.sidebar.radio("Navigate", ["💬 Chat", "📄 Upload RFP", "📚 Estimation History"])

if page == "💬 Chat":
    user_input = st.text_input("Enter project-related question or task description:")
    if user_input:
        keyword = extract_semantic_keyword(user_input, keywords)
        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                display_estimate(df_roles)
                save_estimation_to_history(keyword.title(), df_roles["total_cost"].sum(), df_roles)
            else:
                st.warning("No matching labor roles found.")
        else:
            matches = difflib.get_close_matches(user_input.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
            if matches:
                response = faq_df.loc[faq_df["question"].str.lower() == matches[0], "answer"].values[0]
                st.markdown(f"**Answer:** {response}")
            else:
                st.warning("Sorry, I couldn't understand that question.")

elif page == "📄 Upload RFP":
    doc_file = st.file_uploader("Upload a DOCX RFP file", type=["docx"])
    if doc_file:
        text = extract_text_from_docx(doc_file)
        st.text_area("📜 Extracted RFP Text", text, height=250)

        project_info = extract_project_info(text)
        structured_df = extract_structured_roles(text)

        if structured_df.empty:
            keyword = extract_semantic_keyword(text, keywords)
            df_roles = fetch_roles_for_keyword(keyword) if keyword else pd.DataFrame()
        else:
            df_roles = structured_df

        if not df_roles.empty:
            st.subheader("📋 Project Information")
            for k, v in project_info.items():
                st.markdown(f"**{k}:** {v}")

            display_estimate(df_roles)
            save_estimation_to_history(project_info.get("Project Title", "Uploaded RFP"), df_roles["total_cost"].sum(), df_roles)

            st.markdown("### 📝 Responses to Proposal Requirements")
            reqs = extract_proposal_requirements(text)
            for req in reqs:
                st.markdown(f"**• {req}**")
                match = difflib.get_close_matches(req.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
                if match:
                    answer = faq_df.loc[faq_df["question"].str.lower() == match[0], "answer"].values[0]
                    st.markdown(f"✅ {answer}")
                else:
                    st.markdown("❓ This requirement will be addressed in the proposal.")

            if st.button("📄 Download Proposal Summary"):
                doc = Document()
                doc.add_heading("Proposal Summary", 0)

                for k, v in project_info.items():
                    doc.add_paragraph(f"{k}: {v}")

                doc.add_heading("Labor Cost Estimation", level=1)
                table = doc.add_table(rows=1, cols=5)
                table.style = 'Table Grid'
                hdrs = ["Role", "Count", "Duration", "Rate", "Total Cost"]
                for i, h in enumerate(hdrs):
                    table.rows[0].cells[i].text = h
                for _, row in df_roles.iterrows():
                    cells = table.add_row().cells
                    cells[0].text = row["role"]
                    cells[1].text = str(row["count"])
                    cells[2].text = str(row["duration_days"])
                    cells[3].text = f"${row['daily_rate']}"
                    cells[4].text = f"${row['total_cost']:,.2f}"

                doc.add_paragraph(f"Estimated Total Labor Cost: ${df_roles['total_cost'].sum():,.2f}")

                if reqs:
                    doc.add_heading("Responses to Proposal Requirements", level=1)
                    for req in reqs:
                        doc.add_paragraph(f"• {req}")
                        match = difflib.get_close_matches(req.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
                        if match:
                            ans = faq_df.loc[faq_df["question"].str.lower() == match[0], "answer"].values[0]
                            doc.add_paragraph(ans, style='Intense Quote')
                        else:
                            doc.add_paragraph("This requirement will be addressed in the proposal.", style='Intense Quote')

                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                st.download_button(
                    label="⬇️ Download DOCX Summary",
                    data=buffer,
                    file_name="proposal_summary.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
        else:
            st.warning("Could not detect any labor roles in the document.")

elif page == "📚 Estimation History":
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        df_hist = pd.read_sql("SELECT * FROM rfp_estimation_history ORDER BY timestamp DESC", conn)
        st.subheader("📚 Past Estimations")
        if not df_hist.empty:
            st.dataframe(df_hist[["project_title", "estimated_cost", "timestamp"]])
        else:
            st.info("No historical data available.")
    except Exception as e:
        st.warning(f"⚠️ Failed to load estimation history: {e}")
