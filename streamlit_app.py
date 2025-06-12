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

page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP", "Extract Labor Roles", "Estimate Labor Cost"])

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

def extract_roles_from_structured_blocks(text):
    pattern = re.compile(
        r"(?P<role>[A-Za-z ]+?)\\s*-\\s*Count:\\s*(?P<count>\\d+)\\s*-\\s*Duration:\\s*(?P<duration>\\d+)\\s*Days\\s*-\\s*Daily Rate:\\s*\\$(?P<rate>\\d+)",
        re.IGNORECASE
    )
    matches = pattern.findall(text)
    roles = []
    for role, count, duration, rate in matches:
        roles.append({
            "role": role.strip(),
            "count": int(count),
            "duration_days": int(duration),
            "daily_rate": int(rate),
            "notes": ""
        })
    return roles


def suggest_roles_from_project(text):
    text = text.lower()
    if "offshore" in text and "drilling" in text:
        return [
            {"role": "Drilling Engineer", "count": 2, "duration_days": 45, "daily_rate": 1200, "notes": ""},
            {"role": "Rig Worker", "count": 10, "duration_days": 45, "daily_rate": 500, "notes": ""},
            {"role": "Safety Officer", "count": 1, "duration_days": 30, "daily_rate": 800, "notes": ""}
        ]
    elif "maintenance" in text:
        return [
            {"role": "Technician", "count": 5, "duration_days": 20, "daily_rate": 600, "notes": ""},
            {"role": "Supervisor", "count": 1, "duration_days": 20, "daily_rate": 900, "notes": ""}
        ]
    elif "production" in text:
        return [
            {"role": "Production Engineer", "count": 2, "duration_days": 30, "daily_rate": 1000, "notes": ""},
            {"role": "Operator", "count": 3, "duration_days": 30, "daily_rate": 700, "notes": ""}
        ]       
    return []

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

# ----------------------- Sidebar Assistant ---------------------------
with st.sidebar:
    st.markdown("### 🤖 Assistant")
    uploaded_chat_file = st.file_uploader("Upload RFP to get summary", type=["docx"])

    if uploaded_chat_file:
        extracted_text = extract_text_from_docx(uploaded_chat_file)

        with st.expander("📝 Extracted RFP Content"):
            st.text_area("Text Preview", extracted_text, height=300)

        if st.button("📄 Generate Proposal Summary"):
            roles_data = extract_roles_from_structured_blocks(extracted_text)
            if not roles_data:
                roles_data = suggest_roles_from_project(extracted_text)
                st.info("⚠️ Roles were inferred based on project scope.")
                proposal_reqs = extract_proposal_requirements(extracted_text)

            if not roles_data:
                roles_data = suggest_roles_from_project(extracted_text)
                st.info("Roles were inferred based on project scope.")

            if roles_data:
                df_roles = pd.DataFrame(roles_data)
                df_roles["total_cost"] = df_roles["count"] * df_roles["duration_days"] * df_roles["daily_rate"]

                doc = Document()
                doc.add_heading("Proposal Summary", 0)

                doc.add_paragraph("Labor Requirements:")
                table1 = doc.add_table(rows=1, cols=3)
                table1.style = 'Table Grid'
                hdr_cells = table1.rows[0].cells
                hdr_cells[0].text = 'Role'
                hdr_cells[1].text = 'Count'
                hdr_cells[2].text = 'Duration (Days)'
                for _, row in df_roles.iterrows():
                    cells = table1.add_row().cells
                    cells[0].text = row["role"]
                    cells[1].text = str(row["count"])
                    cells[2].text = str(row["duration_days"])

                doc.add_heading("Labor Cost Estimation", level=1)
                table2 = doc.add_table(rows=1, cols=5)
                table2.style = 'Table Grid'
                hdr = table2.rows[0].cells
                hdr[0].text = 'Role'
                hdr[1].text = 'Count'
                hdr[2].text = 'Duration'
                hdr[3].text = 'Rate'
                hdr[4].text = 'Total Cost'
                for _, row in df_roles.iterrows():
                    row_cells = table2.add_row().cells
                    row_cells[0].text = row["role"]
                    row_cells[1].text = str(row["count"])
                    row_cells[2].text = str(row["duration_days"])
                    row_cells[3].text = f"${row['daily_rate']}"
                    row_cells[4].text = f"${row['total_cost']:,.2f}"

                doc.add_paragraph(f"\nEstimated Total Labor Cost: ${df_roles['total_cost'].sum():,.2f}")

                if proposal_reqs:
                    doc.add_heading("Responses to Proposal Requirements", level=1)
                    for req in proposal_reqs:
                        doc.add_paragraph(f"• {req}", style='List Bullet')
                        doc.add_paragraph(answer_proposal_question(req, load_faq_from_snowflake()), style='Intense Quote')

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

# ----------------------- Dashboard ---------------------------
if page == "Dashboard":
    st.title("📊 AI-Enhanced RFP Estimator - Labor Cost Focus")
    st.header("🔍 Recent Activity")
    st.table(pd.DataFrame({
        "RFP Name": ["Project Alpha", "Deep Sea X", "Ocean Drill"],
        "Uploaded Date": ["2025-06-01", "2025-05-28", "2025-05-20"],
        "Status": ["Estimated", "In Progress", "Estimated"],
        "Labor Cost Estimate": ["$540,000", "$--", "$650,000"]
    }))
    st.markdown("---")
    st.subheader("Start a New Estimate")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("Use the sidebar to upload a new RFP document.")
    with col2:
        if st.button("📄 View Past Estimates"):
            st.info("Coming soon: Historical analysis and accuracy dashboards.")

# ----------------------- Upload RFP ---------------------------
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

# ----------------------- Extract Labor Roles ---------------------------
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
    if st.button("🗓 Save to Snowflake"):
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
            st.dataframe(edited_roles)
            success, nchunks, nrows, _ = write_pandas(conn, edited_roles, table_name="EXTRACTED_LABOR_ROLES", overwrite=True)
            if success:
                st.success(f"✅ Saved {nrows} rows in {nchunks} chunk(s) to Snowflake.")
            else:
                st.error("❌ Failed to save data.")
        except Exception as e:
            st.exception(f"Snowflake Write Error: {e}")

# ----------------------- Estimate Labor Cost ---------------------------
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
                label="📅 Download Summary as DOCX",
                data=buffer,
                file_name="rfp_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    except Exception as e:
        st.error(f"❌ Connection failed: {e}")
