import streamlit as st
import pandas as pd

import snowflake.connector

@st.cache_resource
def get_snowflake_connection():
    return snowflake.connector.connect(
        user=st.secrets["snowflake"]["user"],
        password=st.secrets["snowflake"]["password"],
        account=st.secrets["snowflake"]["account"],
        warehouse=st.secrets["snowflake"]["warehouse"],
        database=st.secrets["snowflake"]["database"],
        schema=st.secrets["snowflake"]["schema"],
        role=st.secrets["snowflake"]["role"]
    )



st.set_page_config(page_title="AI-Enhanced RFP Estimator", layout="wide")

# Page navigation
page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP", "Extract Labor Roles", "Estimate Labor Cost"])
# Sidebar chatbot assistant
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🤖 Assistant")
    chatbot_prompt = st.text_input("Ask something about the RFP process:")
    if chatbot_prompt:
        # Basic simulated responses for demonstration
        if "labor" in chatbot_prompt.lower():
            st.write("Labor costs typically include wages, benefits, offshore premiums, and shift differentials.")
        elif "upload" in chatbot_prompt.lower():
            st.write("To upload an RFP, go to 'Upload RFP' in the sidebar and choose your document.")
        else:
            st.write("I'm still learning! Try asking about labor roles or uploading RFPs.")


if page == "Dashboard":
    # --- Page 1: Dashboard ---
    st.title("📊 AI-Enhanced RFP Estimator - Labor Cost Focus")

    st.header("🔍 Recent Activity")

    # Sample recent activity table
    recent_activity = pd.DataFrame({
        "RFP Name": ["Project Alpha", "Deep Sea X", "Ocean Drill"],
        "Uploaded Date": ["2025-06-01", "2025-05-28", "2025-05-20"],
        "Status": ["Estimated", "In Progress", "Estimated"],
        "Labor Cost Estimate": ["$540,000", "$--", "$650,000"]
    })

    st.table(recent_activity)

    # Buttons to move forward
    st.markdown("---")
    st.subheader("Start a New Estimate")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("Use the sidebar to upload a new RFP document.")

    with col2:
        if st.button("📄 View Past Estimates"):
            st.info("Coming soon: Historical analysis and accuracy dashboards.")

elif page == "Upload RFP":
    # --- Page 2: Upload RFP ---
    st.title("📁 Upload New RFP Document")
    st.markdown("Use this page to upload an RFP document and extract labor-related data.")

    uploaded_file = st.file_uploader("Choose an RFP file (PDF or DOCX)", type=["pdf", "docx"])
    project_type = st.selectbox("Project Type", ["Exploration", "Production", "Maintenance"])
    description = st.text_area("Optional Project Description")

    if st.button("🔍 Extract Labor Requirements"):
        if uploaded_file is None:
            st.warning("Please upload a document first.")
        else:
            # Placeholder action
            st.success("RFP uploaded successfully. Labor extraction process started.")
            st.info("(In production, this would trigger Snowflake NLP pipelines and populate the labor roles table.)")
            # In production: Save to S3/Snowflake Stage and call processing pipeline

elif page == "Extract Labor Roles":
    # --- Page 3: Labor Role Extraction ---
    st.title("🛠 Extracted Labor Roles")
    st.markdown("Review and edit the extracted labor roles from the uploaded RFP.")

    sample_roles = pd.DataFrame({
        "Role": ["Drilling Engineer", "Rig Worker", "Safety Officer"],
        "Count Needed": [3, 20, 2],
        "Duration (Days)": [30, 45, 30],
        "Notes": ["12-hr shifts", "2 teams rotating", "Offshore only"]
    })

    edited_roles = st.data_editor(sample_roles, num_rows="dynamic", use_container_width=True)

    if st.button("💾 Save and Estimate Cost"):
        st.success("Labor roles saved. Proceed to cost estimation.")
        st.info("(In production, this would store data in Snowflake and move to estimation pipeline.)")
elif page == "Estimate Labor Cost":
    # --- Page 4: Labor Cost Estimation ---
    st.title("💰 Labor Cost Estimation")
    st.markdown("Review calculated labor costs based on uploaded and extracted data.")

    cost_data = pd.DataFrame({
        "Role": ["Drilling Engineer", "Rig Worker", "Safety Officer"],
        "Count Needed": [3, 20, 2],
        "Duration (Days)": [30, 45, 30],
        "Daily Rate ($)": [1000, 500, 700]
    })

    cost_data["Total Cost"] = cost_data["Count Needed"] * cost_data["Duration (Days)"] * cost_data["Daily Rate ($)"]

    st.dataframe(cost_data, use_container_width=True)

    total = cost_data["Total Cost"].sum()
    st.subheader(f"🧾 Estimated Total Labor Cost: ${total:,.2f}")

    if st.button("📥 Download Proposal Summary"):
        st.info("(Coming soon: Generate and download a formatted proposal document.)")
