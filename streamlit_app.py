import streamlit as st
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

# Page setup
st.set_page_config(page_title="AI-Enhanced RFP Estimator", layout="wide")

# Sidebar Navigation
page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP", "Extract Labor Roles", "Estimate Labor Cost"])

# Chatbot Assistant (Sidebar)
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🤖 Assistant")
    chatbot_prompt = st.text_input("Ask about RFP or labor cost:")
    if chatbot_prompt:
        if "labor" in chatbot_prompt.lower():
            st.write("Labor costs typically include wages, benefits, offshore premiums, and shift differentials.")
        elif "upload" in chatbot_prompt.lower():
            st.write("To upload an RFP, go to 'Upload RFP' and select a document.")
        else:
            st.write("I'm still learning! Ask about uploading or estimating labor roles.")

# --- Page 1: Dashboard ---
if page == "Dashboard":
    st.title("📊 AI-Enhanced RFP Estimator - Labor Cost Focus")
    st.header("🔍 Recent Activity")

    # Example data (replace with dynamic later)
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

# --- Page 2: Upload RFP ---
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

# --- Page 3: Extract Labor Roles ---
elif page == "Extract Labor Roles":
    st.title("🛠 Extracted Labor Roles")
    st.markdown("Review and edit the extracted labor roles.")

    # Sample editable table (replace with data from Snowflake later)
    sample_roles = pd.DataFrame({
        "role": ["Drilling Engineer", "Rig Worker", "Safety Officer"],
        "count": [3, 20, 2],
        "duration_days": [30, 45, 30],
        "daily_rate": [1000, 500, 700],
        "notes": ["12-hr shifts", "2 teams rotating", "Offshore only"]
    })

    edited_roles = st.data_editor(sample_roles, num_rows="dynamic", use_container_width=True)

    if st.button("💾 Save to Snowflake"):
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
            write_pandas(conn, edited_roles, table_name="extracted_labor_roles", overwrite=True)
            st.success("Labor roles saved to Snowflake.")
        except Exception as e:
            st.error(f"❌ Error saving to Snowflake: {e}")

# --- Page 4: Estimate Labor Cost ---
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
        query = "SELECT * FROM extracted_labor_roles"
        df = pd.read_sql(query, conn)

        if not df.empty:
            df["Total Cost"] = df["count"] * df["duration_days"] * df["daily_rate"]
            st.dataframe(df, use_container_width=True)

            total = df["Total Cost"].sum()
            st.subheader(f"🧾 Estimated Total Labor Cost: ${total:,.2f}")
        else:
            st.warning("No labor roles found. Please upload and save roles first.")

    except Exception as e:
        st.error(f"❌ Connection failed: {e}")
