import os
import re
import chromadb
from openai import OpenAI
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from pypdf import PdfReader
import pandas as pd
import plotly.express as px

# =====================================================================
# 1. STREAMLIT PAGE SETUP & STYLING
# =====================================================================
st.set_page_config(page_title="Enterprise AI Assistant", page_icon="🏢", layout="wide")

st.title("🏢 Enterprise AI Assistant")
st.caption("Powered by OpenAI GPT-4o, ChromaDB (Text Engine), and Pandas (Data Engine)")


# =====================================================================
# 2. THE GATEKEEPER (Authentication & Tenant Routing)
# =====================================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.yaml")

with open(config_path) as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

authenticator.login(location="main")

if st.session_state.get("authentication_status") is False:
    st.error("Username or password is incorrect.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password to access the workspace.")
    st.stop()

current_user = st.session_state.get("username")
name = st.session_state.get("name")


# =====================================================================
# 3. HYBRID ENGINE SETUP (Multi-Tenant Isolated Architecture!)
# =====================================================================
@st.cache_resource(show_spinner=False)
def load_rag_engine(user_id):
    engine_dir = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(engine_dir, "rag_db", "tenants", user_id)
    docs_folder = os.path.join(engine_dir, "rag documents", "tenants", user_id)

    if not os.path.exists(docs_folder):
        os.makedirs(docs_folder)
    if not os.path.exists(db_path):
        os.makedirs(db_path)

    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(
        name=f"collection_{user_id}"
    )
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

    def chunk_text(text, chunk_size=150):
        words = text.split()
        return [
            " ".join(words[i : i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]

    chunks_loaded = 0
    spreadsheet_tables = []

    if os.path.exists(docs_folder):
        all_chunks = []
        all_ids = []
        chunk_counter = 0

        for filename in os.listdir(docs_folder):
            file_path = os.path.join(docs_folder, filename)
            text_content = ""

            # --- BRAIN 1: TEXT DOCUMENTS ---
            if filename.endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as file:
                    text_content = file.read()

            elif filename.endswith(".pdf"):
                try:
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text_content += extracted + " "
                except Exception as e:
                    print(f"Error reading PDF {filename}: {e}")

            # --- BRAIN 2: SPREADSHEETS ---
            elif filename.endswith(".csv") or filename.endswith(".xlsx"):
                try:
                    if filename.endswith(".csv"):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)

                    df = df.dropna(how="all").fillna("N/A")

                    table_string = f"=== SPREADSHEET DATA FROM [{filename}] ===\n"
                    table_string += df.to_string(index=False)
                    spreadsheet_tables.append(table_string)

                except Exception as e:
                    print(f"Error reading spreadsheet {filename}: {e}")

            if text_content:
                chunks = chunk_text(text_content, chunk_size=150)
                for chunk in chunks:
                    all_chunks.append(chunk)
                    all_ids.append(f"{filename}_chunk_{chunk_counter}")
                    chunk_counter += 1

        if all_chunks:
            collection.upsert(documents=all_chunks, ids=all_ids)
            chunks_loaded = len(all_chunks)

    return collection, openai_client, chunks_loaded, spreadsheet_tables, docs_folder


collection, openai_client, chunks_loaded, spreadsheet_tables, docs_folder = (
    load_rag_engine(current_user)
)


# =====================================================================
# 4. THE SIDEBAR DASHBOARD
# =====================================================================
with st.sidebar:
    st.success(f"👤 Logged in as: **{name}**")
    authenticator.logout(button_name="Logout", location="sidebar")
    st.markdown("---")

    st.header("📊 System Dashboard")
    st.success("🟢 Two-Brain Hybrid Engine Online")

    st.markdown("---")
    st.subheader("Database Stats")
    st.write(f"**Workspace:** `{current_user}`")
    st.write(f"**Text Paragraphs Loaded:** `{chunks_loaded}`")
    st.write(f"**Active Spreadsheets Loaded:** `{len(spreadsheet_tables)}`")

    st.markdown("---")
    st.subheader("📥 Add New Knowledge")

    uploaded_files = st.file_uploader(
        "Upload TXT, PDF, CSV, or XLSX files:",
        type=["txt", "pdf", "csv", "xlsx"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button(
        "🚀 Process & Ingest Files", use_container_width=True
    ):
        with st.spinner("Routing files to Hybrid Engines..."):
            for uploaded_file in uploaded_files:
                file_path = os.path.join(docs_folder, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

            load_rag_engine.clear()
            st.success("Files successfully processed!")
            st.rerun()

    st.markdown("---")
    st.subheader("🗂️ Manage Uploaded Docs")

    existing_files = (
        os.listdir(docs_folder) if os.path.exists(docs_folder) else []
    )

    if existing_files:
        file_to_delete = st.selectbox(
            "Select a document to remove:", existing_files
        )

        if st.button("🗑️ Delete Selected File", use_container_width=True):
            with st.spinner("Removing file & purging database memory..."):
                file_path = os.path.join(docs_folder, file_to_delete)
                if os.path.exists(file_path):
                    os.remove(file_path)

                engine_dir = os.path.dirname(os.path.abspath(__file__))
                db_path = os.path.join(
                    engine_dir, "rag_db", "tenants", current_user
                )
                chroma_client = chromadb.PersistentClient(path=db_path)

                try:
                    chroma_client.delete_collection(
                        name=f"collection_{current_user}"
                    )
                except Exception as e:
                    pass

                load_rag_engine.clear()
                st.success(f"Successfully deleted '{file_to_delete}'!")
                st.rerun()
    else:
        st.info("No documents uploaded yet.")

    st.markdown("---")

    # Clear Chat button
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    # Download Chat Log Feature
    if "messages" in st.session_state and st.session_state.messages:
        chat_transcript = "=== ENTERPRISE AI CHAT LOG ===\n\n"
        for msg in st.session_state.messages:
            role = "👤 You" if msg["role"] == "user" else "🤖 AI Assistant"
            chat_transcript += f"{role}:\n{msg['content']}\n\n"

        st.download_button(
            label="💾 Download Chat Transcript",
            data=chat_transcript,
            file_name=f"chat_log_{current_user}.txt",
            mime="text/plain",
            use_container_width=True,
        )


# =====================================================================
# INTERACTIVE CHART RENDERING ENGINE (Fail-Safe)
# =====================================================================
def render_ai_charts(text):
    """Scans AI responses for Plotly code blocks and renders them safely."""
    code_blocks = re.findall(
        r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE
    )

    for code in code_blocks:
        if "fig" in code:
            try:
                clean_code = re.sub(r"fig\.show\(\)", "", code)

                exec_scope = {
                    "pd": pd,
                    "px": px,
                    "st": st,
                }

                exec(clean_code, exec_scope)

                fig = exec_scope.get("fig") or exec_scope.get("figure")
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.caption(f"⚠️ *Chart rendering note: {e}*")


# =====================================================================
# 5. CONVERSATIONAL MEMORY (Session State)
# =====================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_ai_charts(message["content"])


# =====================================================================
# 6. THE INTERACTIVE CHAT BOX (With Real-Time Streaming & Plotly Charts!)
# =====================================================================
if query := st.chat_input("Ask about policies, syllabi, or generate spreadsheet charts..."):

    with st.chat_message("user"):
        st.markdown(query)
    st.session_state.messages.append({"role": "user", "content": query})

    results = collection.query(query_texts=[query], n_results=15)
    text_context = (
        "\n---\n".join(results["documents"][0])
        if results["documents"] and results["documents"][0]
        else "No text documents found."
    )

    spreadsheet_context = (
        "\n\n".join(spreadsheet_tables)
        if spreadsheet_tables
        else "No spreadsheet tables loaded."
    )

    full_combined_context = f"--- UNSTRUCTURED TEXT DOCUMENTS ---\n{text_context}\n\n--- STRUCTURED SPREADSHEETS (100% INTACT TABLES) ---\n{spreadsheet_context}"

    messages_payload = [
        {
            "role": "system",
            "content": (
                "You are an elite enterprise AI data assistant with advanced data visualization capabilities. "
                "You have access to both unstructured text documents and complete, intact structured spreadsheet tables. "
                "When answering questions about spreadsheets, perform exact mathematical comparisons, count rows carefully, and never omit data.\n\n"
                "CRITICAL VISUALIZATION INSTRUCTIONS:\n"
                "If the user explicitly asks for a chart, graph, plot, or visual representation of spreadsheet data, you MUST include a self-contained Python code block wrapped in ```python and ``` at the end of your response.\n"
                "Inside that code block:\n"
                "1. Construct a clean pandas DataFrame named `data` containing ONLY the relevant data required for the chart.\n"
                "2. Use `plotly.express` (referenced as `px`) to generate the requested chart and assign the output to a variable named exactly `fig`.\n"
                "3. Use a modern, professional color scheme and clear axis labels/titles.\n"
                "4. DO NOT call `fig.show()` or `st.plotly_chart()` inside your code block—simply assign the figure to `fig`."
            ),
        }
    ]

    for msg in st.session_state.messages[-6:]:
        messages_payload.append({"role": msg["role"], "content": msg["content"]})

    messages_payload.append(
        {
            "role": "user",
            "content": f"System Data Context:\n{full_combined_context}\n\nCurrent Question: {query}",
        }
    )

    with st.chat_message("assistant"):
        try:
            stream = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                stream=True,
            )
            ai_answer = st.write_stream(stream)

            st.session_state.messages.append(
                {"role": "assistant", "content": ai_answer}
            )

            render_ai_charts(ai_answer)

            with st.expander("🔍 View Retrieved Database & Spreadsheet Proof"):
                st.info(full_combined_context)

        except Exception as e:
            st.error(f"Error connecting to AI: {e}")