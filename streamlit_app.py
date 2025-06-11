import streamlit as st
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

import openai

openai.api_key = st.secrets["openai"]["api_key"]

# Page setup
st.set_page_config(page_title="AI-Enhanced RFP Estimator", layout="wide")

# Sidebar Navigation
page = st.sidebar.selectbox("Go to", ["Dashboard", "Upload RFP", "Extract Labor Roles", "Estimate Labor Cost"])

# Chatbot Assistant (Sidebar)
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🤖 AI Chat Assistant")

    user_input = st.text_input("Ask anything about RFPs or labor cost:")

    if user_input:
        with st.spinner("Thinking..."):
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",  # Or "gpt-4" if you have access
                    messages=[
                        {"role": "system", "content": "You are an expert in oil and gas RFP proposal estimation, specializing in labor cost estimation and proposal creation."},
                        {"role": "user", "content": user_input}
                    ],
                    temperature=0.4
                )
                answer = response['choices'][0]['message']['content']
                st.write(answer)

            except Exception as e:
                st.error(f"Chatbot Error: {e}")

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

            # Uppercase column names to match Snowflake convention
            edited_roles.columns = [c.upper() for c in edited_roles.columns]

            st.write("📤 Saving the following data to Snowflake:")
            st.dataframe(edited_roles)

            # Save
            success, nchunks, nrows, _ = write_pandas(conn, edited_roles, table_name="EXTRACTED_LABOR_ROLES", overwrite=True)

            if success:
                st.success(f"✅ Saved {nrows} rows in {nchunks} chunk(s) to Snowflake.")
            else:
                st.error("❌ Failed to save data.")

        except Exception as e:
            st.exception(f"Snowflake Write Error: {e}")


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

        df = pd.read_sql("SELECT * FROM EXTRACTED_LABOR_ROLES", conn)

        # Standardize column names
        df.columns = [col.lower() for col in df.columns]

        df["total_cost"] = df["count"] * df["duration_days"] * df["daily_rate"]

        st.dataframe(df)

        total = df["total_cost"].sum()
        st.subheader(f"🧾 Estimated Total Labor Cost: ${total:,.2f}")

    except Exception as e:
        st.error(f"❌ Connection failed: {e}")