import streamlit as st

st.set_page_config(page_title="AI-Enhanced RFP Estimator", layout="wide")

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
import difflib
from docx import Document
from io import BytesIO
import re

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

def extract_project_type(text):
    keywords = ["drilling", "installation", "exploration", "production", "maintenance"]
    for word in keywords:
        if word in text.lower():
            return word
    return None

@st.cache_data(ttl=600)
def fetch_roles_by_project_type(project_type):
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
            WHERE LOWER(task_keyword) = '{project_type.lower()}'
        """
        df = pd.read_sql(query, conn)
        df.columns = [c.lower() for c in df.columns]
        df["total_cost"] = df["count"] * df["duration_days"] * df["daily_rate"]
        return df
    except Exception as e:
        st.error(f"Error fetching roles: {e}")
        return pd.DataFrame()

# ----------------------- App Interface ---------------------------
faq_df = load_faq_from_snowflake()
page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP"])

# ---------------- Sidebar Chat Assistant ----------------
with st.sidebar:
    st.markdown("### 🤖 Assistant")
    user_query = st.text_input("Ask something about the RFP process:")
    if user_query:
        proj_type = extract_project_type(user_query)
        if proj_type:
            df_resp = fetch_roles_by_project_type(proj_type)
            if not df_resp.empty:
                st.markdown("**Estimated Labor Cost:**")
                st.dataframe(df_resp[["role", "count", "duration_days", "daily_rate", "total_cost"]])
                st.markdown(f"**Total:** ${df_resp['total_cost'].sum():,.2f}")
            else:
                st.warning("No roles matched from database.")
        else:
            st.info("Couldn't detect task keyword. Try mentioning drilling, installation, etc.")

# ---------------- Upload and Process RFP ----------------
if page == "Upload RFP":
    st.title("📁 Upload RFP Document")
    uploaded_file = st.file_uploader("Upload your DOCX RFP file", type=["docx"])

    if uploaded_file:
        text = extract_text_from_docx(uploaded_file)
        st.text_area("📜 RFP Text Extracted", text, height=300)

        if st.button("📄 Generate Labor Estimation Summary"):
            proj_type = extract_project_type(text)
            if proj_type:
                df_roles = fetch_roles_by_project_type(proj_type)
                print(df_roles)
                if not df_roles.empty:
                    total_cost = df_roles["total_cost"].sum()
                    doc = Document()
                    doc.add_heading("Proposal Summary", 0)
                    doc.add_paragraph(f"Detected Project Type: {proj_type.title()}")
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
                    st.warning("⚠️ No labor roles found for this project type.")
            else:
                st.error("⚠️ Could not determine project type from the RFP document.")




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
