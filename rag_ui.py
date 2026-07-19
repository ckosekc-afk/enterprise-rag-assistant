import os
import chromadb
from openai import OpenAI
import streamlit as st
from pypdf import PdfReader
import pandas as pd

# =====================================================================
# 1. STREAMLIT PAGE SETUP & STYLING
# =====================================================================
st.set_page_config(
    page_title="Enterprise AI Assistant",
    page_icon="🏢",
    layout="wide"
)

st.title("🏢 Enterprise AI Assistant")
st.caption("Powered by OpenAI GPT-4o, ChromaDB (Text Engine), and Pandas (Data Engine)")

# =====================================================================
# 2. HYBRID ENGINE SETUP (Two-Brain Architecture!)
# =====================================================================
@st.cache_resource
def load_rag_engine():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "rag_db")
    docs_folder = os.path.join(script_dir, "rag documents")
    
    if not os.path.exists(docs_folder):
        os.makedirs(docs_folder)
    
    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(name="company_policies")
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    def chunk_text(text, chunk_size=150):
        words = text.split()
        return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    chunks_loaded = 0
    spreadsheet_tables = [] # <-- NEW: Separate memory bank for spreadsheets!
    
    if os.path.exists(docs_folder):
        all_chunks = []
        all_ids = []
        chunk_counter = 0
        
        for filename in os.listdir(docs_folder):
            file_path = os.path.join(docs_folder, filename)
            text_content = ""
            
            # --- BRAIN 1: TEXT DOCUMENTS (Go to ChromaDB) ---
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
            
            # --- BRAIN 2: SPREADSHEETS (Go to Pandas Data Engine!) ---
            elif filename.endswith(".csv") or filename.endswith(".xlsx"):
                try:
                    if filename.endswith(".csv"):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)
                    
                    df = df.dropna(how="all").fillna("N/A")
                    
                    # We convert the entire spreadsheet into a clean, structured table format!
                    table_string = f"=== SPREADSHEET DATA FROM [{filename}] ===\n"
                    table_string += df.to_string(index=False)
                    spreadsheet_tables.append(table_string)
                    
                except Exception as e:
                    print(f"Error reading spreadsheet {filename}: {e}")

            # Slices standard TXT and PDF text into ChromaDB!
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

collection, openai_client, chunks_loaded, spreadsheet_tables, docs_folder = load_rag_engine()

# =====================================================================
# 3. THE SIDEBAR DASHBOARD
# =====================================================================
with st.sidebar:
    st.header("📊 System Dashboard")
    st.success("🟢 Two-Brain Hybrid Engine Online")
    
    st.markdown("---")
    st.subheader("Database Stats")
    st.write(f"**Text Paragraphs Loaded:** `{chunks_loaded}`")
    st.write(f"**Active Spreadsheets Loaded:** `{len(spreadsheet_tables)}`")
    st.write(f"**Docs Folder:** `{os.path.basename(docs_folder)}`")
    
    st.markdown("---")
    st.subheader("📥 Add New Knowledge")
    
    uploaded_files = st.file_uploader(
        "Upload TXT, PDF, CSV, or XLSX files:", 
        type=["txt", "pdf", "csv", "xlsx"], 
        accept_multiple_files=True
    )
    
    if uploaded_files and st.button("🚀 Process & Ingest Files", use_container_width=True):
        with st.spinner("Routing files to Hybrid Engines..."):
            for uploaded_file in uploaded_files:
                file_path = os.path.join(docs_folder, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            
            load_rag_engine.clear()
            st.success("Files successfully processed!")
            st.rerun()
            
    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# =====================================================================
# 4. CONVERSATIONAL MEMORY (Session State)
# =====================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# =====================================================================
# 5. THE INTERACTIVE CHAT BOX
# =====================================================================
if query := st.chat_input("Ask about policies, syllabi, or spreadsheet data..."):
    
    with st.chat_message("user"):
        st.markdown(query)
    st.session_state.messages.append({"role": "user", "content": query})

    # Brain 1: Grab text context from ChromaDB
    results = collection.query(query_texts=[query], n_results=15)
    text_context = "\n---\n".join(results['documents'][0]) if results['documents'] and results['documents'][0] else "No text documents found."
    
    # Brain 2: Grab full structured table context from Pandas!
    spreadsheet_context = "\n\n".join(spreadsheet_tables) if spreadsheet_tables else "No spreadsheet tables loaded."

    # Combine both brains so GPT-4o has 100% visibility!
    full_combined_context = f"--- UNSTRUCTURED TEXT DOCUMENTS ---\n{text_context}\n\n--- STRUCTURED SPREADSHEETS (100% INTACT TABLES) ---\n{spreadsheet_context}"

    messages_payload = [
        {"role": "system", "content": "You are an elite enterprise AI data assistant. You have access to both unstructured text documents and complete, intact structured spreadsheet tables. When answering questions about spreadsheets, perform exact mathematical comparisons, count every single row carefully, and never omit any data present in the table. Be precise and thorough."}
    ]
    
    for msg in st.session_state.messages[-6:]:
        messages_payload.append({"role": msg["role"], "content": msg["content"]})
        
    messages_payload.append({"role": "user", "content": f"System Data Context:\n{full_combined_context}\n\nCurrent Question: {query}"})

    with st.chat_message("assistant"):
        with st.spinner("Analyzing tables & searching documents..."):
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_payload,
                    timeout=15.0
                )
                ai_answer = response.choices[0].message.content
                st.markdown(ai_answer)
                
                with st.expander("🔍 View Retrieved Database & Spreadsheet Proof"):
                    st.info(full_combined_context)
                    
                st.session_state.messages.append({"role": "assistant", "content": ai_answer})
                
            except Exception as e:
                st.error(f"Error connecting to AI: {e}")