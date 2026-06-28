import os,sys
import nltk
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
import asyncio
import traceback

# Core AI & DB Imports
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from pinecone import Pinecone, ServerlessSpec
from langchain_community.retrievers import PineconeHybridSearchRetriever
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from llama_parse import LlamaParse
from pinecone_text.sparse import BM25Encoder

# load_dotenv()
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# Safely ensure BM25 has its English dictionary
# try:
#     nltk.data.find('corpora/stopwords')
# except LookupError:
#     nltk.download('stopwords', quiet=True)
# except Exception:
#     pass

# ==========================================
# GLOBAL INITIALIZATION 
# ==========================================
mcp = FastMCP("Semantic RAG Vault")

# 1. Initialize Dual Encoders (Semantic & Keyword)
# 1. Global Holders (Start empty)
_embeddings = None
_bm25_encoder = None
namespace = ""

def get_embeddings():
    """Loads the ML model ONLY on the first execution and caches it."""
    global _embeddings
    if _embeddings is None:
        print("Booting HuggingFace Embeddings into memory for the first time...",file=sys.stderr)
        _embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001" ,output_dimensionality=768)
    return _embeddings

def get_bm25_encoder():
    """Loads the sparse encoder ONLY on the first execution and caches it."""
    global _bm25_encoder
    if _bm25_encoder is None:
        print("Booting BM25 Encoder into memory for the first time...",file=sys.stderr)
        _bm25_encoder = BM25Encoder().default()
    return _bm25_encoder

# 2. Initialize Pinecone Client
index_name = "agent-workflow-rag"

def get_pinecone_index():
    """Builds the Pinecone client and connects to the index strictly at Run Time."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("Pinecone API Key is missing. Please provide it in the UI sidebar.")
    
    db = Pinecone(api_key=api_key)
    
    # Check and create the index safely at runtime
    if not db.has_index(index_name):
        print(f"Creating Pinecone index '{index_name}'...")
        db.create_index(
            name=index_name,
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            dimension=768,
            metric="dotproduct" 
        )
    return db.Index(index_name)

# 3. Create the Native Hybrid Retriever
# This correctly accepts the sparse_encoder without throwing a TypeError
def _get_retriever(namespace: str) -> PineconeHybridSearchRetriever:
    index = get_pinecone_index()
    return PineconeHybridSearchRetriever(
        embeddings=get_embeddings(),
        sparse_encoder=get_bm25_encoder(),
        index=index,
        text_key="text",
        namespace=namespace
    )

# MCP TOOLS

@mcp.tool()
async def ingest_document(filepath: str, namespace : str = '__default__') -> str:
    """
    Reads a local PDF or text file, extracts structured markdown, chunks it, 
    and saves it to the Semantic Vault vector database using Hybrid embeddings.
    """
    try:
        p = Path(filepath)
        if not p.is_file():
            return f"Error: Cannot find file at {filepath}"
        
        index = get_pinecone_index()
        
        #if uploading the same file, remove the old vectors
        try:
            print(f"🧹 Purging old vectors from namespace '{namespace}'...", file=sys.stderr)
            index.delete(delete_all=True, namespace=namespace)
        except Exception as e:
            print(f"Warning: Could not clear namespace (it might be empty already). {e}", file=sys.stderr)
        
        # 1. Structural Extraction with LlamaParse
        parsing_instruction = "You are an Expert Document Analyzer. Accurately parse the document including all tables and columns into clean markdown."
        
        parser = LlamaParse(
            result_type="markdown",
            verbose=True, 
            # Ensure your .env file has this exact variable name:
            api_key=os.getenv("LLAMA_CLOUD_API_KEY"), 
            system_prompt=parsing_instruction
        )
        
        # aload_data handles the async extraction
        llama_docs = await parser.aload_data(str(p))
        raw_markdown = "\n\n".join([doc.text for doc in llama_docs])
        
        # 2. Split by Markdown Headers first
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ],
            strip_headers=False
        )
        structural_docs = markdown_splitter.split_text(raw_markdown)
        
        # 3. Split the structural chunks by character length
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=250)
        final_docs = text_splitter.split_documents(structural_docs)
        
        # 4. Extract raw texts and metadata for the Hybrid Retriever
        texts = []
        metadatas = []
        for doc in final_docs:
            texts.append(doc.page_content)
            # Copy existing metadata (like the Markdown Headers) and inject the source path
            meta = doc.metadata.copy() if hasattr(doc, 'metadata') else {}
            meta["source"] = filepath
            metadatas.append(meta)
            
        # 5. Push to Pinecone (Generates both Dense & Sparse vectors)
        await asyncio.to_thread(_get_retriever(namespace).add_texts, texts, metadatas=metadatas)
        
        return f"Success: Ingested {len(texts)} chunks into namespace '{namespace}'."
        
    except Exception as e:
        return f"Ingestion Error: {str(e)}"


@mcp.tool()
async def query_vault(query: str, namespace: str = "__default__") -> str:
    """
    Searches the Semantic Vault vector database for information.
    
    """
    try:
        
        # Execute Hybrid Search
        results = await asyncio.to_thread(
          _get_retriever(namespace).invoke, query  
        ) 
        
        if not results:
            return "No relevant information found in the vault."
            
        formatted_context = "\n\n--- CHUNK ---\n".join([doc.page_content for doc in results])
        
        return f"Retrieved Context:\n{formatted_context}"
        
    except Exception as e:
        return f"Retrieval Error: {str(e)}\n\n{traceback.format_exc()}"


if __name__ == "__main__":
    mcp.run(transport='stdio')
