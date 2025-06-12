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


# Assistant Sidebar Upload + Summary Generator
with st.sidebar:
    st.markdown("### 🤖 Assistant")
    uploaded_chat_file = st.file_uploader("Upload RFP to get summary", type=["docx"])

    if uploaded_chat_file:
        extracted_text = extract_text_from_docx(uploaded_chat_file)

        with st.expander("📝 Extracted RFP Content"):
            st.text_area("Text Preview", extracted_text, height=300)

        if st.button("📄 Generate Proposal Summary"):
            role_pattern = r"\b(?:Drilling|Rig|Production|Safety|Maintenance)?\s?(Engineer|Technician|Manager|Operator|Supervisor|Welder|Electrician|Inspector)\b"
            roles = re.findall(role_pattern, extracted_text, re.IGNORECASE)
            role_counts = dict(Counter([role.title() for role in roles]))

            summary_doc = Document()
            summary_doc.add_heading("Proposal Summary", 0)
            summary_doc.add_paragraph("Below is a summary of labor requirements based on the uploaded RFP document:\n")

            for role, count in role_counts.items():
                summary_doc.add_paragraph(f"{role}: {count} needed")

            buffer = BytesIO()
            summary_doc.save(buffer)
            buffer.seek(0)

            st.success("✅ Summary document generated.")
            st.download_button(
                label="⬇️ Download Proposal Summary",
                data=buffer,
                file_name="proposal_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )


# Dashboard Page
if page == "Dashboard":
    st.title("📊 AI-Enhanced RFP Estimator - Labor Cost Focus")
    st.header("🔍 Recent Activity")

    recent_activity = pd.DataFrame({
        "RFP Name": ["Project Alpha", "Deep Sea X", "Ocean Drill"],
        "Uploaded Date": ["2025-06-01", "2025-05-28", "2025-05-20"],
        "Status": ["Estimated", "In Progress", "Estimated"],
        "Labor Cost Estimate": ["$540,000", "$--", "$650,000"]
    })
    st.table(recent_activity)

    st.markdown("---")
    st.subheader("Start a New Estimate")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("Use the sidebar to upload a new RFP document.")
    with col2:
        if st.button("📄 View Past Estimates"):
            st.info("Coming soon: Historical analysis and accuracy dashboards.")


# Upload RFP Page
elif page == "Upload RFP":
    st.title("📁 Upload New RFP Document")
    st.markdown("Use this page to upload an RFP document and extract labor-related data.")

    uploaded_file = st.file_uploader("Choose an RFP file (PDF or DOCX)", type=["pdf", "docx"])
    project_type = st.selectbox("Project Type", ["Exploration", "Production", "Maintenance"])
    description = st.text_area("Optional Project Description")

    if st.button("🔍 Extract Labor Requirements"):
        if uploaded_file is None:
            st.warning("Please upload a document first.")
        else:
            st.success("RFP uploaded successfully. Labor extraction process started.")
            st.info("(This would trigger Snowflake NLP pipelines and populate labor roles.)")


# Extract Labor Roles Page
elif page == "Extract Labor Roles":
    st.title("🛠 Extracted Labor Roles")
    st.markdown("Review and edit the extracted labor roles.")

    try:
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"],
            role=st.secrets["snowflake"]["role"]
        )
        df_existing = pd.read_sql("SELECT * FROM EXTRACTED_LABOR_ROLES", conn)
        df_existing.columns = [col.lower() for col in df_existing.columns]
    except:
        df_existing = pd.DataFrame({
            "role": ["Drilling Engineer", "Rig Worker", "Safety Officer"],
            "count": [3, 20, 2],
            "duration_days": [30, 45, 30],
            "daily_rate": [1000, 500, 700],
            "notes": ["12-hr shifts", "2 teams rotating", "Offshore only"]
        })

    edited_roles = st.data_editor(df_existing, num_rows="dynamic", use_container_width=True)

    if st.button("📅 Save to Snowflake"):
        try:
            conn = snowflake.connector.connect(
                user=st.secrets["snowflake"]["user"],
                password=st.secrets["snowflake"]["password"],
                account=st.secrets["snowflake"]["account"],
                warehouse=st.secrets["snowflake"]["warehouse"],
                database=st.secrets["snowflake"]["database"],
                schema=st.secrets["snowflake"]["schema"],
                role=st.secrets["snowflake"]["role"]
            )
            edited_roles.columns = [c.upper() for c in edited_roles.columns]
            st.write("📄 Saving the following data to Snowflake:")
            st.dataframe(edited_roles)

            success, nchunks, nrows, _ = write_pandas(conn, edited_roles, table_name="EXTRACTED_LABOR_ROLES", overwrite=True)

            if success:
                st.success(f"✅ Saved {nrows} rows in {nchunks} chunk(s) to Snowflake.")
            else:
                st.error("❌ Failed to save data.")

        except Exception as e:
            st.exception(f"Snowflake Write Error: {e}")


# Estimate Labor Cost Page
elif page == "Estimate Labor Cost":
    st.title("💰 Labor Cost Estimation")
    st.markdown("Automatically estimate labor cost based on roles stored in Snowflake.")

    try:
        conn = snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"],
            role=st.secrets["snowflake"]["role"]
        )
        df = pd.read_sql("SELECT * FROM EXTRACTED_LABOR_ROLES", conn)
        df.columns = [col.lower() for col in df.columns]
        df["total_cost"] = df["count"] * df["duration_days"] * df["daily_rate"]

        st.dataframe(df)

        total = df["total_cost"].sum()
        st.subheader(f"🧾 Estimated Total Labor Cost: ${total:,.2f}")

        st.markdown("### 📄 Proposal Summary Report")
        if st.button("📄 Generate Proposal Summary"):
            doc = Document()
            doc.add_heading("RFP Labor Cost Summary", 0)
            doc.add_paragraph(f"Estimated Total Labor Cost: ${total:,.2f}")
            doc.add_paragraph("\nDetailed Breakdown:")

            table = doc.add_table(rows=1, cols=len(df.columns))
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            for i, col in enumerate(df.columns):
                hdr_cells[i].text = col.capitalize()

            for _, row in df.iterrows():
                row_cells = table.add_row().cells
                for i, val in enumerate(row):
                    row_cells[i].text = str(val)

            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            st.download_button(
                label="📥 Download Summary as DOCX",
                data=buffer,
                file_name="rfp_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

    except Exception as e:
        st.error(f"❌ Connection failed: {e}")
