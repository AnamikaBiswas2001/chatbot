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
    matches = difflib.get_close_matches(text.lower(), keyword_list, n=1, cutoff=0.3)
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

def generate_proposal_summary(project_type, df_roles):
    total_cost = df_roles["total_cost"].sum()
    doc = Document()
    doc.add_heading("Proposal Summary", 0)
    doc.add_paragraph(f"Detected Project Type: {project_type.title()}")
    doc.add_heading("Labor Cost Estimation", level=1)

    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    headers = ["Role", "Count", "Duration", "Rate", "Total Cost"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h

    for _, row in df_roles.iterrows():
        row_cells = table.add_row().cells
        row_cells[0].text = row["role"]
        row_cells[1].text = str(row["count"])
        row_cells[2].text = str(row["duration_days"])
        row_cells[3].text = f"${row['daily_rate']}"
        row_cells[4].text = f"${row['total_cost']:,.2f}"

    doc.add_paragraph(f"\nEstimated Total Labor Cost: ${total_cost:,.2f}")
    return doc

# ----------------- UI: Text or File Input -----------------
keywords = load_keywords_from_snowflake()
tab1, tab2 = st.tabs(["💬 Chat Query", "📄 Upload DOCX"])

with tab1:
    user_input = st.text_input("Enter project-related question or task description:")
    if user_input:
        keyword = extract_keyword(user_input, keywords)
        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                st.markdown(f"### 📊 Estimated Labor Cost for '{keyword.title()}' Project")
                st.dataframe(df_roles[["role", "count", "duration_days", "daily_rate", "total_cost"]])
                st.success(f"💰 Total Estimated Cost: ${df_roles['total_cost'].sum():,.2f}")
                if st.button("📄 Generate DOCX Summary"):
                    doc = generate_proposal_summary(keyword, df_roles)
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
                st.warning("No matching labor roles found.")
        else:
            faq_df = load_faq_from_snowflake()
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
        keyword = extract_keyword(text, keywords)
        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                st.markdown(f"### 📊 Estimated Labor Cost for '{keyword.title()}' Project")
                st.dataframe(df_roles[["role", "count", "duration_days", "daily_rate", "total_cost"]])
                st.success(f"💰 Total Estimated Cost: ${df_roles['total_cost'].sum():,.2f}")
                if st.button("📄 Generate DOCX Summary"):
                    doc = generate_proposal_summary(keyword, df_roles)
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
                st.warning("No roles found in the database for the detected keyword.")
        else:
            st.warning("Could not detect project keyword from the document.")
