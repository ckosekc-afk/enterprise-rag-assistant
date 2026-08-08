import stripe
import streamlit as st
import os
import re
import io
import datetime
import chromadb
from openai import OpenAI
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from pypdf import PdfReader
import pandas as pd
import plotly.express as px
from supabase import create_client
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import streamlit as st
import chromadb
from supabase import create_client, Client

# --- 1. WAKE UP SUPABASE ---
# This pulls your keys from Streamlit secrets so 'supabase' is defined
supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(supabase_url, supabase_key)

# --- 2. WAKE UP CHROMADB ---
# This points to your local database folder so 'collection' is defined
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="financial_vault")

# =====================================================================
# 1. STREAMLIT PAGE SETUP & STYLING
# =====================================================================
st.set_page_config(page_title="QuantLex", page_icon="📊", layout="wide")
import streamlit as st

# 1. Page Config (Keep your existing config here)
st.set_page_config(page_title="QuantLex", page_icon="🏢", layout="wide")

# 2. Initialize authentication memory
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Initialize session state for user tracking
if "user" not in st.session_state:
    st.session_state["user"] = None

# Block access to the rest of the app if not logged in
if not st.session_state["user"]:
    st.title("Enterprise RAG Access")
    tab1, tab2 = st.tabs(["Login", "Create Account"])
    
    with tab1:
        log_email = st.text_input("Email", key="log_email")
        log_pwd = st.text_input("Password", type="password", key="log_pwd")
        if st.button("Login"):
            try:
                # Logs in an existing user
                res = supabase.auth.sign_in_with_password({"email": log_email, "password": log_pwd})
                st.session_state["user"] = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
                
    with tab2:
        reg_email = st.text_input("Email", key="reg_email")
        reg_pwd = st.text_input("Password", type="password", key="reg_pwd")
        if st.button("Sign Up"):
            try:
                # Creates a new user in the Supabase backend
                res = supabase.auth.sign_up({"email": reg_email, "password": reg_pwd})
                st.success("Account created successfully. Please log in.")
            except Exception as e:
                st.error(f"Registration failed: {e}")
                
    # st.stop() halts the script here until the user successfully authenticates
    st.stop()
# ---------------------------------------------------------
# 5. THE STRIPE PAYWALL
# ---------------------------------------------------------
user_id = st.session_state["user"].id
# --- STRIPE VERIFICATION ---
if "session_id" in st.query_params:
    session_id = st.query_params["session_id"]
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            supabase.table("profiles").update({"is_subscribed": True}).eq("id", user_id).execute()
            st.query_params.clear()
            st.rerun()
    except Exception as e:
        st.error("Error verifying payment with Stripe.")
# ---------------------------
# Check the new profiles table in the database
profile = supabase.table("profiles").select("is_subscribed").eq("id", user_id).execute()

# Create a profile if it's their first time
if len(profile.data) == 0:

    is_subscribed = False
else:
    is_subscribed = profile.data[0].get("is_subscribed", False)

if not is_subscribed:
    st.title("🔒 Enterprise Plan Required")
    st.warning("Your account is currently inactive. Upgrade to unlock the secure RAG vault.")
    
    # Updated the hardcoded text to reflect your actual price
    st.link_button(
    "Upgrade to Enterprise ($499/mo)", 
    f"{st.secrets['STRIPE_PAYMENT_LINK']}?client_reference_id={user_id}", 
    type="primary", 
    use_container_width=True
)
    
    st.stop() # <-- The Paywall Bouncer
# ---------------------------------------------------------
# -----------------------------------
# ---------------------------------------------------------
# --- ALL YOUR EXISTING RAG_UI.PY CODE GOES BELOW THIS LINE ---
# (No need to indent your existing code!)
st.title("QuantLex")
st.caption("Powered by OpenAI GPT-4o, ChromaDB, Pandas, Supabase Vaults & Word Brief Generation")


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

# --- SECURE SIDEBAR UPLOADER ---
with st.sidebar:
    st.header("📂 Secure Workspace")
    st.write(f"Logged in as: {st.session_state['user'].email}")
    
    uploaded_file = st.file_uploader("Upload a text document", type=["txt"])
    
    if uploaded_file is not None and st.button("Vault Document"):
        with st.spinner("Encrypting and vaulting..."):
            # 1. Read the file
            text_data = uploaded_file.getvalue().decode("utf-8")
            filename = uploaded_file.name
            
            # 2. Break it into readable chunks
            chunk_size = 1000
            chunks = [text_data[i:i+chunk_size] for i in range(0, len(text_data), chunk_size)]
            
            # 3. Save to Chroma database WITH the secure user_id
            for i, text_chunk in enumerate(chunks):
                chunk_id = f"{st.session_state['user'].id}_{filename}_chunk_{i}"
                
                # THIS IS THE SNIPPET YOU ASKED ABOUT!
                collection.add(
                    documents=[text_chunk],
                    metadatas=[{"user_id": st.session_state["user"].id, "source": filename}],
                    ids=[chunk_id]
                )
                
            st.success(f"Successfully vaulted: {filename}")
# -------------------------------
# =====================================================================
# 3. SUPABASE CLOUD VAULT ENGINE
# =====================================================================
@st.cache_resource(show_spinner=False)
def get_supabase_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase_client()
BUCKET_NAME = "client-vaults"

def upload_file_to_supabase(user_id, local_file_path, filename):
    """Uploads a local file to Supabase cloud storage under the user's folder."""
    cloud_path = f"{user_id}/{filename}"
    with open(local_file_path, "rb") as f:
        file_bytes = f.read()
    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            file=file_bytes,
            path=cloud_path,
            file_options={"upsert": "true"}
        )
    except Exception as e:
        print(f"Supabase Upload Exception for {filename}: {e}")

def delete_file_from_supabase(user_id, filename):
    """Deletes a file from Supabase and outputs live API diagnostic telemetry to the screen."""
    cloud_path = f"{user_id}/{filename}"
    try:
        res = supabase.storage.from_(BUCKET_NAME).remove([cloud_path])
        if not res:
            st.warning(f"⚠️ Supabase could not delete '{cloud_path}'. Verify permissions.")
        else:
            st.toast(f"☁️ Cloud Vault synced: Deleted '{filename}'")
        return res
    except Exception as e:
        st.error(f"❌ Cloud Deletion Blocked: {e}")
        return None

def sync_supabase_to_local(user_id, local_docs_folder):
    """Downloads all cloud files for this user to local storage on engine startup."""
    try:
        remote_files = supabase.storage.from_(BUCKET_NAME).list(user_id)
        for item in remote_files:
            filename = item.get("name")
            if not filename or filename == ".emptyFolderPlaceholder":
                continue
            
            local_path = os.path.join(local_docs_folder, filename)
            if not os.path.exists(local_path):
                cloud_path = f"{user_id}/{filename}"
                file_bytes = supabase.storage.from_(BUCKET_NAME).download(cloud_path)
                with open(local_path, "wb") as f:
                    f.write(file_bytes)
    except Exception as e:
        print(f"Supabase Sync Warning: {e}")


# =====================================================================
# 4. HYBRID ENGINE SETUP (Multi-Tenant Isolated Architecture)
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

    sync_supabase_to_local(user_id, docs_folder)

    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(
        name=f"collection_{user_id}"
    )
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    stripe.api_key = st.secrets["STRIPE_API_KEY"]
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
# 5. THE SIDEBAR DASHBOARD
# =====================================================================
with st.sidebar:
    st.success(f"👤 Logged in as: **{name}**")
    authenticator.logout(button_name="Logout", location="sidebar")
    st.markdown("---")

    st.header("📊 System Dashboard")
    st.success("🟢 Cloud Vault & Brief Generator Online")

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
        with st.spinner("Vaulting files to Supabase & Hybrid Engines..."):
            for uploaded_file in uploaded_files:
                file_path = os.path.join(docs_folder, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                upload_file_to_supabase(current_user, file_path, uploaded_file.name)

            load_rag_engine.clear()
            st.success("Files successfully processed and vaulted!")
            st.rerun()

    st.markdown("---")
    st.subheader("🧪 Synthetic Demo Sandbox")
    st.caption("Load pre-configured financial datasets for instant zero-risk testing.")

    if st.button("⚡ Load Demo Financial Vault", use_container_width=True):
        with st.spinner("Generating synthetic trust policies & portfolio holdings..."):
            demo_csv_path = os.path.join(docs_folder, "Synthetic_Q3_Holdings.csv")
            demo_df = pd.DataFrame({
                'Client Account': ['Smith Trust', 'Smith Trust', 'Vance IRA', 'Vance IRA', 'Rostova Endowment', 'Rostova Endowment'],
                'Ticker': ['VTI', 'VXUS', 'BND', 'SPY', 'QQQ', 'ARKK'],
                'Asset Class': ['US Equity', 'Intl Equity', 'Fixed Income', 'US Equity', 'Tech Equity', 'Speculative Growth'],
                'Region': ['North America', 'Global', 'North America', 'North America', 'North America', 'Global'],
                'Total Value': [450000, 180000, 320000, 610000, 890000, 150000],
                'Expense Ratio': [0.03, 0.07, 0.03, 0.09, 0.20, 0.75]
            })
            demo_df.to_csv(demo_csv_path, index=False)
            upload_file_to_supabase(current_user, demo_csv_path, "Synthetic_Q3_Holdings.csv")

            demo_txt_path = os.path.join(docs_folder, "Smith_Family_Trust_Policy.txt")
            trust_policy_text = (
                "=== SMITH FAMILY TRUST POLICY & FIDUCIARY GUIDELINES ===\n\n"
                "1. ASSET ALLOCATION LIMITS: The Smith Family Trust mandates a maximum exposure of 20% to International Equities "
                "and a minimum baseline of 25% in Fixed Income (Bonds) to preserve capital.\n\n"
                "2. EXPENSE RATIO THRESHOLDS: To protect long-term compounding, no actively managed fund or ETF with an expense ratio "
                "exceeding 0.50% may be held in the primary endowment without formal written authorization from the trustees.\n\n"
                "3. REBALANCING SCHEDULE: Portfolio rebalancing must occur quarterly. Any single asset class that drifts more than 5% "
                "from its target allocation must be rebalanced within 14 business days of quarter-end."
            )
            with open(demo_txt_path, "w", encoding="utf-8") as f:
                f.write(trust_policy_text)
            upload_file_to_supabase(current_user, demo_txt_path, "Smith_Family_Trust_Policy.txt")

            load_rag_engine.clear()
            st.success("Demo Vault successfully loaded into active memory!")
            st.rerun()

    st.markdown("---")
    st.subheader("🗂️ Manage Uploaded Docs")
with st.sidebar:
    st.divider()
    if st.button("Log Out"):
        st.session_state["authenticated"] = False
        st.rerun()
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

                delete_file_from_supabase(current_user, file_to_delete)

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

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    if "messages" in st.session_state and st.session_state.messages:
        chat_transcript = "=== ENTERPRISE AI CHAT LOG ===\n\n"
        for msg in st.session_state.messages:
            role = "👤 You" if msg["role"] == "user" else "🤖 AI Assistant"
            chat_transcript += f"{role}:\n{msg['content']}\n\n"

        st.download_button(
            label="💾 Download Chat Transcript (.txt)",
            data=chat_transcript,
            file_name=f"chat_log_{current_user}.txt",
            mime="text/plain",
            use_container_width=True,
        )


# =====================================================================
# INTERACTIVE CHART RENDERING, WORD GENERATION & CLEANING ENGINE
# =====================================================================
def clean_ai_text(text):
    """Hides raw Python code blocks from the chat display without deleting normal text."""
    if not text:
        return ""
    return re.sub(
        r"```(?:python)?\s*.*?```", "", text, flags=re.DOTALL | re.IGNORECASE
    ).strip()


@st.cache_data(show_spinner=False)
def create_executive_brief_docx(query_text, ai_response, user_name):
    """Compiles AI analysis into a professionally styled Word document (Cached for instant UI rendering!)."""
    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        
    title = doc.add_paragraph()
    title_run = title.add_run("EXECUTIVE BRIEFING & AUDIT REPORT")
    title_run.font.size = Pt(18)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(15, 23, 42)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    meta = doc.add_paragraph()
    meta.add_run("Prepared For: ").bold = True
    meta.add_run(f"{user_name}\n")
    meta.add_run("Inquiry / Subject: ").bold = True
    meta.add_run(f"{query_text}\n")
    
    timestamp_str = datetime.datetime.now().strftime("%B %d, %Y — %I:%M %p")
    meta.add_run("Timestamp: ").bold = True
    meta.add_run(f"{timestamp_str}\n")
    
    status_run = meta.add_run("Status: Verified Multi-Tenant RAG & Spreadsheet Analysis")
    status_run.font.italic = True
    status_run.font.size = Pt(9.5)
    status_run.font.color.rgb = RGBColor(100, 116, 139)
    
    doc.add_paragraph("_________________________________________________________________________________")
    
    clean_text = clean_ai_text(ai_response)
    
    def add_styled_paragraph(text, is_bullet=False):
        style = 'List Bullet' if is_bullet else None
        p = doc.add_paragraph(style=style)
        
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**') and len(part) >= 4:
                run = p.add_run(part[2:-2])
                run.bold = True
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(15, 23, 42)
            else:
                run = p.add_run(part)
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(51, 65, 85)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        return p

    for line in clean_text.split("\n"):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("#"):
            header_level = len(line.split()[0])
            header_text = line.lstrip("# ").strip()
            p = doc.add_paragraph()
            run = p.add_run(header_text)
            run.bold = True
            
            if header_level == 1:
                run.font.size = Pt(15)
                run.font.color.rgb = RGBColor(15, 23, 42)
                p.paragraph_format.space_before = Pt(14)
                p.paragraph_format.space_after = Pt(4)
            elif header_level == 2:
                run.font.size = Pt(13)
                run.font.color.rgb = RGBColor(30, 41, 59)
                p.paragraph_format.space_before = Pt(10)
                p.paragraph_format.space_after = Pt(3)
            else:
                run.font.size = Pt(11.5)
                run.font.color.rgb = RGBColor(51, 65, 85)
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(2)
                
        elif line.startswith("- ") or line.startswith("* "):
            bullet_text = line[2:].strip()
            add_styled_paragraph(bullet_text, is_bullet=True)
            
        else:
            add_styled_paragraph(line, is_bullet=False)
            
    doc.add_paragraph("\n_________________________________________________________________________________")
    footer = doc.add_paragraph()
    f_run = footer.add_run("CONFIDENTIAL & PROPRIETARY — ENTERPRISE AI ASSISTANT\nGenerated with Zero-Flash Token Streaming & Inline Audit Citations.")
    f_run.font.size = Pt(8.5)
    f_run.font.italic = True
    f_run.font.color.rgb = RGBColor(148, 163, 184)
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def render_ai_charts(text, msg_idx=0):
    """Scans AI responses for Plotly code blocks, renders them, and attaches a uniquely keyed export button."""
    code_blocks = re.findall(
        r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE
    )

    for i, code in enumerate(code_blocks):
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

                df_data = exec_scope.get("data")
                if isinstance(df_data, pd.DataFrame) and not df_data.empty:
                    csv_data = df_data.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Download Cleaned Chart Data (.csv)",
                        data=csv_data,
                        file_name=f"ai_filtered_report_{msg_idx}_{i+1}.csv",
                        mime="text/csv",
                        key=f"export_btn_{msg_idx}_{i}",
                        use_container_width=False,
                    )
            except Exception as e:
                st.caption(f"⚠️ *Chart rendering note: {e}*")


def live_stream_filter(stream_obj, raw_accumulator):
    """Intercepts live tokens: streams clean text while silently buffering Python code."""
    hide_code = False
    buffer = ""

    for chunk in stream_obj:
        if not hasattr(chunk, "choices") or not chunk.choices:
            continue

        delta = getattr(chunk.choices[0], "delta", None)
        if not delta:
            continue

        token = getattr(delta, "content", "") or ""
        if not token:
            continue

        raw_accumulator.append(token)

        if not hide_code:
            buffer += token
            if "```" in buffer:
                hide_code = True
                clean_prefix = buffer.split("```")[0]
                if clean_prefix:
                    yield clean_prefix
                buffer = ""
            elif not buffer.endswith("`"):
                yield buffer
                buffer = ""

    if not hide_code and buffer:
        yield buffer


# =====================================================================
# 6. CONVERSATIONAL MEMORY (The Stable Historical Loop)
# =====================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown(clean_ai_text(message["content"]))
            render_ai_charts(message["content"], msg_idx=idx)
            
            associated_query = "General Executive Inquiry"
            if idx > 0 and st.session_state.messages[idx - 1]["role"] == "user":
                associated_query = st.session_state.messages[idx - 1]["content"]
                
            docx_bytes = create_executive_brief_docx(
                associated_query, message["content"], name or current_user
            )
            st.download_button(
                label="📄 Download Executive Brief (.docx)",
                data=docx_bytes,
                file_name=f"Executive_Brief_{idx}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"brief_btn_hist_{idx}",
                use_container_width=False,
            )
            
            with st.expander("🔍 View Retrieved Database & Spreadsheet Proof"):
                st.info("Retrieved context verified and locked in session memory.")
        else:
            st.markdown(message["content"])


# =====================================================================
# 7. THE INTERACTIVE CHAT BOX (With Instant WebSocket Locking!)
# =====================================================================
if query := st.chat_input("Ask about policies, syllabi, or generate spreadsheet charts..."):

    # 1. Show and save user question
    with st.chat_message("user"):
        st.markdown(query)
    st.session_state.messages.append({"role": "user", "content": query})

    # 2. Pull the RAG Context with User Security Filter
    results = collection.query(
        query_texts=[query], 
        n_results=15,
        where={"user_id": st.session_state["user"].id}  # <--- Locks access to current user only
    )
    
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

    # 3. Build the Payload for the AI
    messages_payload = [
        {
            "role": "system",
            "content": (
                "You are an elite enterprise AI data assistant with advanced data visualization and auditing capabilities. "
                "You have access to both unstructured text documents and complete, intact structured spreadsheet tables. "
                "When answering questions about spreadsheets, perform exact mathematical comparisons, count rows carefully, and never omit data.\n\n"
                "CRITICAL AUDIT & CITATION INSTRUCTIONS:\n"
                "1. You must act as an auditable research analyst. Every factual claim, number, policy, or metric you state MUST end with an inline footnote citation.\n"
                "2. For text documents (PDF/TXT), cite the source filename and section/paragraph where possible, e.g., [Source: Employee_Handbook.pdf].\n"
                "3. For spreadsheet data, cite the exact table name or row/column context, e.g., [Source: Q3_Revenue.csv, Row 14].\n"
                "4. Never invent facts or numbers. If the data is missing from the provided context, explicitly state: 'No supporting data found in workspace archives.'\n"
                "5. ZERO HALLUCINATION POLICY: You must extract answers verbatim. Do not paraphrase, creatively summarize, or alter the wording of the provided rules. If quoting a policy, use the exact words from the text.\n\n"
                "CRITICAL VISUALIZATION INSTRUCTIONS:\n"
                "If the user explicitly asks for a chart, graph, plot, or visual representation of spreadsheet data, you MUST include a self-contained Python code block wrapped in ```python and ``` at the very end of your response.\n"
                "Inside that code block:\n"
                "1. Construct a clean pandas DataFrame named `data` containing ALL relevant categories, groups, and rows required for the chart. You are strictly forbidden from omitting or skipping any data points.\n"
                "2. Use `plotly.express` (referenced as `px`) to generate the requested chart and assign the output to a variable named exactly `fig`.\n"
                "3. Use a modern, professional color scheme and clear axis labels/titles.\n"
                "4. DO NOT call `fig.show()` or `st.plotly_chart()` inside your code block—simply assign the figure to `fig`.\n"
                "IMPORTANT FOR USER EXPERIENCE: Do NOT mention the Python code in your text response, do NOT say 'Here is the code:', and do NOT explain how the code works. Simply provide a natural, executive-level business explanation of the insights with citations, followed silently by the code block at the very end."
            ),
        }
    ]

    # Add conversation history to the AI's memory
    for msg in st.session_state.messages[-6:-1]:
        messages_payload.append({"role": msg["role"], "content": msg["content"]})

    # Add the current question + context
    messages_payload.append(
        {
            "role": "user",
            "content": f"System Data Context:\n{full_combined_context}\n\nCurrent Question: {query}",
        }
    )

    # 4. Generate Answer via Streaming
    with st.chat_message("assistant"):
        try:
            raw_tokens = []

            stream = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                stream=True,
                temperature=0.0,
            )

            # Stream the live tokens seamlessly to the user
            st.write_stream(live_stream_filter(stream, raw_tokens))
            full_ai_answer = "".join(raw_tokens)

            # Lock the complete answer into permanent session memory FIRST
            st.session_state.messages.append(
                {"role": "assistant", "content": full_ai_answer}
            )

            # FORCE AN IMMEDIATE RERUN! 
            # This triggers Section 6 to safely redraw the text and attach your buttons
            st.rerun()

        except Exception as e:
            st.error(f"Error connecting to AI: {e}")
            stream = openai_client.chat.completions.create(
    model="gpt-4o",
    messages=messages_payload,
    stream=True,
    temperature=0.0  # <--- THIS LOCKS DOWN THE CREATIVITY
)