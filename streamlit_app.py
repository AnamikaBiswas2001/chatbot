import streamlit as st
import pandas as pd
import snowflake.connector
from docx import Document
from io import BytesIO
import difflib
import re
import json
from datetime import datetime
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

def save_estimation_to_history(project_title, total_cost, df_roles, question=None):
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        cursor = conn.cursor()
        json_roles = json.dumps(df_roles.to_dict(orient="records"))
        current_time = datetime.utcnow()
        query = """
            INSERT INTO rfp_estimation_history (project_title, total_cost, roles, timestamp, question)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (project_title, float(total_cost), json_roles, current_time, question))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        st.warning(f"⚠️ Failed to save estimation history: {e}")


def display_estimate(df):
    st.markdown("### 📊 Estimated Labor Cost")
    st.dataframe(df[["role", "count", "duration_days", "daily_rate", "total_cost"]])
    total_cost = df["total_cost"].sum()
    st.success(f"💰 Total Estimated Cost: ${total_cost:,.2f}")
    return total_cost

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

keywords = load_keywords_from_snowflake()
faq_df = load_faq_from_snowflake()

tabs = st.tabs(["💬 Chat Query", "📄 Upload DOCX", "📚 Estimation History"])

with tabs[0]:
    st.subheader("💬 Chat Assistant")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    user_input = st.chat_input("Ask a project-related question or describe your RFP task...")

    if user_input:
        # Display user message
        st.chat_message("user").write(user_input)

        keyword = extract_semantic_keyword(user_input, keywords)
        response = ""

        if keyword:
            df_roles = fetch_roles_for_keyword(keyword)
            if not df_roles.empty:
                total = df_roles["total_cost"].sum()
                response = f"### 📊 Estimated Labor Cost\n"
                response += df_roles[["role", "count", "duration_days", "daily_rate", "total_cost"]].to_markdown(index=False)
                response += f"\n\n💰 **Total Estimated Cost:** ${total:,.2f}"
                save_estimation_to_history("Chat Query", total, df_roles, question=user_input)
            else:
                response = "⚠️ No matching labor roles found in the database."
        else:
            matches = difflib.get_close_matches(user_input.lower(), faq_df["question"].str.lower(), n=1, cutoff=0.4)
            if matches:
                response = faq_df.loc[faq_df["question"].str.lower() == matches[0], "answer"].values[0]
            else:
                response = "❓ Sorry, I couldn't understand that question."

        # Show assistant message
        st.chat_message("assistant").markdown(response)

        # Save to session history
        st.session_state.chat_history.append({"role": "user", "text": user_input})
        st.session_state.chat_history.append({"role": "assistant", "text": response})


with tabs[1]:
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

            total = display_estimate(df_roles)
            save_estimation_to_history(project_info.get("Project Title", "Untitled RFP"), total, df_roles, question=text)


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
        else:
            st.warning("Could not detect any labor roles in the document.")

with tabs[2]:
    st.subheader("📚 Estimation History")
    try:
        conn = snowflake.connector.connect(**st.secrets["snowflake"])
        history_df = pd.read_sql(
            "SELECT project_title, total_cost, roles, question, timestamp FROM rfp_estimation_history ORDER BY timestamp DESC",
            conn
        )

        if not history_df.empty:
            for _, row in history_df.iterrows():
                with st.container():
                    st.markdown(f"""
                        <div style="background-color:#f5f5f5; padding:15px; border-radius:10px; margin-bottom:10px">
                            <strong>📌 Project:</strong> {row['PROJECT_TITLE']}<br>
                            <strong>💬 Query:</strong> <em>{row['QUESTION'] if row['QUESTION'] else 'N/A'}</em><br>
                            <strong>💰 Total Cost:</strong> ${row['TOTAL_COST']:,.2f}<br>
                            <strong>⏱️ Timestamp:</strong> {row['TIMESTAMP']}
                        </div>
                    """, unsafe_allow_html=True)

                    with st.expander("📋 View Estimated Roles"):
                        try:
                            roles_df = pd.DataFrame(json.loads(row["ROLES"]))
                            if not roles_df.empty:
                                roles_df["total_cost"] = roles_df["count"] * roles_df["duration_days"] * roles_df["daily_rate"]
                                st.dataframe(
                                    roles_df[["role", "count", "duration_days", "daily_rate", "total_cost"]],
                                    use_container_width=True
                                )
                        except Exception as e:
                            st.error(f"Error parsing roles data: {e}")
        else:
            st.info("No estimation history found.")
    except Exception as e:
        st.warning(f"⚠️ Failed to load estimation history: {e}")

