import os
import PyPDF2
from supabase import create_client, Client
from openai import OpenAI

# ==========================================
# 1. SETUP & CREDENTIALS
# ==========================================
# Use your Supabase SERVICE ROLE KEY, not the public anon key. 
# The service role key bypasses Row Level Security so you can insert data.
SUPABASE_URL = "https://qbzrcpouvjdfyihwzplv.supabase.co"
import os
import tomllib  # Built-in in Python 3.11+

# 1. Dynamically locate and load your secrets.toml file
secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
if not os.path.exists(secrets_path):
    secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")

with open(secrets_path, "rb") as f:
    secrets = tomllib.load(f)

# 2. Extract keys securely without hardcoding them in git
SUPABASE_URL = secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = secrets["SUPABASE_KEY"]
OPENAI_API_KEY = secrets["OPENAI_API_KEY"]

# 3. Initialize your clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================================
# 2. CLIENT CONFIGURATION
# ==========================================
# Change these two variables for every new client onboarding
TENANT_ID = "stark_financial"  
FOLDER_PATH = "./client_files" # Drop their PDFs into this local folder

# ==========================================
# 3. CHUNKING LOGIC
# ==========================================
def chunk_text(text, chunk_size=1000, overlap=200):
    """Splits a massive document into overlapping paragraphs for the AI."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

# ==========================================
# 4. MAIN INGESTION ENGINE
# ==========================================
def process_client_folder():
    print(f"Starting ingestion for Tenant: {TENANT_ID}...")
    
    # Loop through every file in the target folder
    for filename in os.listdir(FOLDER_PATH):
        if filename.endswith(".pdf"):
            filepath = os.path.join(FOLDER_PATH, filename)
            print(f"-> Reading: {filename}")
            
            # Step A: Extract Text from PDF
            text = ""
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            
            # Step B: Chunk the Text
            chunks = chunk_text(text)
            
            # Step C: Embed and Upload each chunk
            for i, chunk in enumerate(chunks):
                clean_chunk = chunk.strip().replace("\n", " ")
                if not clean_chunk:
                    continue
                    
                # Generate OpenAI Vector Embedding
                response = openai_client.embeddings.create(
                    input=clean_chunk,
                    model="text-embedding-3-small"
                )
                embedding = response.data[0].embedding
                
                # Format the row for your Supabase database
                db_row = {
                    "content": clean_chunk,
                    "metadata": {"source": filename, "chunk": i},
                    "embedding": embedding,
                    "tenant_id": TENANT_ID
                }
                
                # Insert the row into the 'documents' table
                supabase.table("documents").insert(db_row).execute()
                
            print(f"   [SUCCESS] Uploaded {len(chunks)} embedded chunks for {filename}.")

if __name__ == "__main__":
    process_client_folder()
    print(f"\n✅ All files for {TENANT_ID} have been securely ingested and isolated.")