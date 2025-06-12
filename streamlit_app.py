import streamlit as st
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
import difflib
from docx import Document
from io import BytesIO
import re
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ----------------------- Helper Functions ---------------------------
def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

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
        st.error(f"Failed to load chatbot Q&A: {e}")
        return pd.DataFrame(columns=["question", "answer"])

def extract_roles_with_counts(text):
    pattern = re.compile(
        r"(?P<count>\d+)?\s*(?P<role>(?:Drilling|Rig|Production|Safety|Maintenance)?\s?(Engineer|Technician|Manager|Operator|Supervisor|Welder|Electrician|Inspector)s?)\s*(for\s(?P<duration>\d+)\s*days)?",
        re.IGNORECASE
    )
    extracted = []
    for match in pattern.finditer(text):
        role = match.group("role").strip().title()
        count = int(match.group("count")) if match.group("count") else 1
        duration = int(match.group("duration")) if match.group("duration") else 30
        extracted.append({
            "role": role,
            "count": count,
            "duration_days": duration,
            "daily_rate": 1000,
            "notes": ""
        })
    return extracted

def extract_proposal_requirements(text):
    match = re.search(r"Proposal Requirements:\s*(.*?)\s*(Submission Deadline:|Contact for Clarifications:|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        lines = [line.strip("-• ").strip() for line in raw.split("\n") if line.strip()]
        return lines
    return []

def answer_proposal_question(req, faq_df):
    matches = difflib.get_close_matches(req.lower(), faq_df['question'].str.lower(), n=1, cutoff=0.4)
    if matches:
        match = matches[0]
        return faq_df.loc[faq_df['question'].str.lower() == match, 'answer'].values[0]
    else:
        return "This requirement will be addressed in the final submission per project scope."

# ----------------------- Streamlit UI ---------------------------
st.set_page_config(page_title="AI-Enhanced RFP Estimator", layout="wide")
page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP", "Extract Labor Roles", "Estimate Labor Cost"])
faq_df = load_faq_from_snowflake()

def get_best_match(user_input):
    questions = faq_df["question"].tolist()
    matches = difflib.get_close_matches(user_input.lower(), questions, n=1, cutoff=0.4)
    if matches:
        answer = faq_df.loc[faq_df["question"] == matches[0], "answer"].values[0]
        return answer
    return "I'm sorry, I don't understand that yet."

# ----------------------- Sidebar Assistant ---------------------------
with st.sidebar:
    st.markdown("### 🤖 Assistant")
    uploaded_chat_file = st.file_uploader("Upload RFP to get summary", type=["docx"])

    if uploaded_chat_file:
        extracted_text = extract_text_from_docx(uploaded_chat_file)

        with st.expander("📝 Extracted RFP Content"):
            st.text_area("Text Preview", extracted_text, height=300)

        if st.button("📄 Generate Proposal Summary"):
            roles_data = extract_roles_with_counts(extracted_text)
            proposal_reqs = extract_proposal_requirements(extracted_text)

            if not roles_data:
                st.warning("No labor roles found in the document.")
            else:
                df_roles = pd.DataFrame(roles_data)

                doc = Document()
                doc.add_heading("Proposal Summary", 0)
                doc.add_paragraph("Below is a summary of labor requirements based on the uploaded RFP document:\n")

                table = doc.add_table(rows=1, cols=3)
                table.style = 'Table Grid'
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = 'Role'
                hdr_cells[1].text = 'Count'
                hdr_cells[2].text = 'Duration (Days)'

                for _, row in df_roles.iterrows():
                    cells = table.add_row().cells
                    cells[0].text = row["role"]
                    cells[1].text = str(row["count"])
                    cells[2].text = str(row["duration_days"])

                if proposal_reqs:
                    doc.add_heading("Responses to Proposal Requirements", level=1)
                    for req in proposal_reqs:
                        doc.add_paragraph(f"• {req}", style='List Bullet')
                        doc.add_paragraph(answer_proposal_question(req, faq_df), style='Intense Quote')

                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)

                st.success("✅ Summary document generated.")
                st.download_button(
                    label="⬇️ Download Proposal Summary",
                    data=buffer,
                    file_name="proposal_summary.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
