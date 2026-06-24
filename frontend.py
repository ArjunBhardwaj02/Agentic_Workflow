import streamlit as st
import asyncio
import uuid
import os
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from orchestrator import build_graph
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==========================================
# 1. PAGE CONFIG & STAGING DIRECTORY
# ==========================================
st.set_page_config(page_title="Agentic Orchestrator", page_icon="🧠", layout="wide")
st.title("🧠 Multi-Agent MCP Orchestrator")

# Define where uploaded files will be staged on your local machine
UPLOAD_DIR = Path("./staging_vault")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. THE DUAL-CREDENTIAL SIDEBAR
# ==========================================
with st.sidebar:
    st.header("🔑 Developer Keys")
    st.markdown("Provide API keys for external services.")
    
    # Text inputs for Pure API Key services
    user_gemini_key = st.text_input("Gemini API Key", type="password")
    user_todoist_token = st.text_input("Todoist Token", type="password")
    user_notion_key = st.text_input("Notion API Key", type="password")
    user_pinecone_key = st.text_input("Pinecone API Key", type="password")
    user_llamaparse_key = st.text_input("LlamaParse Key", type="password")
    
    st.markdown("---")
    st.header("📅 Google Workspace")
    st.markdown("Connect identity services securely.")
    
    # Defensive Guard for Streamlit's Native Google OAuth 
    is_logged_in = getattr(st.user, "is_logged_in", False)
    
    if not is_logged_in:
        if st.button("🔗 Log in with Google"):
            st.login("google")
            st.stop()
    else:
        st.success(f"Connected as {st.user.name}")
        # Expose the access token to your Google MCP Server via environment variable
        if "access" in st.user.tokens:
            os.environ["GOOGLE_ACCESS_TOKEN"] = st.user.tokens["access"]
        if st.button("Disconnect"):
            st.logout()
            
    st.markdown("---")
    
    # ---------------------------------------------------------
    # THE DOCUMENT UPLOADER YOU ASKED FOR IS RIGHT HERE
    # ---------------------------------------------------------
    st.header("🗄️ Knowledge Vault")
    uploaded_file = st.file_uploader("Stage Document", type=["pdf", "txt", "md"])

    if uploaded_file is not None:
        # Prepend UUID to prevent duplicate name overwrites
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{uploaded_file.name}"
        staging_file_path = UPLOAD_DIR / safe_filename
        
        # Flush the file to the local disk
        with open(staging_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        st.success("✅ File securely staged!")
        # Print the exact path so the user can copy it into the chat
        st.code(str(staging_file_path), language="text")
    # ---------------------------------------------------------

# ==========================================
# 3. ENVIRONMENT INJECTION & GUARDS
# ==========================================
if user_gemini_key:
    os.environ["GOOGLE_API_KEY"] = user_gemini_key
if user_todoist_token:
    os.environ["TODOIST_API_TOKEN"] = user_todoist_token
if user_pinecone_key:
    os.environ["PINECONE_API_KEY"] = user_pinecone_key
if user_notion_key:
    os.environ["NOTION_API_KEY"] = user_notion_key
if user_llamaparse_key:
    os.environ["LLAMA_CLOUD_API_KEY"] = user_llamaparse_key

# Prevent the graph from running if the core LLM key is missing
if not os.environ.get("GOOGLE_API_KEY"):
    st.info("👈 Please enter your Gemini API Key in the sidebar to activate the AI.")
    st.stop()

# ==========================================
# 4. SESSION & MEMORY MANAGEMENT
# ==========================================
# Lock the session ID to prevent amnesia on UI reruns
if "user_thread_id" not in st.session_state:
    st.session_state["user_thread_id"] = f"session_{uuid.uuid4()}"

current_thread = st.session_state["user_thread_id"]

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    if isinstance(msg, HumanMessage):
        st.chat_message("user").write(msg.content)
    elif isinstance(msg, AIMessage) and msg.content:
        st.chat_message("assistant").write(msg.content)

# ==========================================
# 5. ASYNC GRAPH EXECUTION
# ==========================================
user_input = st.chat_input("Command your agents...")

if user_input:
    st.chat_message("user").write(user_input)
    st.session_state["messages"].append(HumanMessage(content=user_input))

    async def process_chat():
        # Get the database string from environment
        db_uri = os.getenv("POSTGRES_DB_URI")

        # db_uri = "postgresql://postgres:root@localhost:5432/agentic_workflow"
        
        # Safely open the Postgres Connection Pool
        async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
            # Automatically build required database tables if they don't exist
            await checkpointer.setup()
            
            # Inject Postgres memory into the graph
            app = await build_graph(checkpointer)
            
            with st.chat_message("assistant"):
                status_container = st.status("Agents are executing...", expanded=True)
                final_response = ""
                
                inputs = {"messages": st.session_state["messages"]}
                # Lock the execution to the current session's Postgres row
                config = {"configurable": {"thread_id": current_thread}}
                
                async for event in app.astream(inputs, config=config, stream_mode="updates"):
                    for node_name, node_state in event.items():
                        if node_name == "agent":
                            msg = node_state["messages"][-1]
                            
                            if msg.tool_calls:
                                for tool in msg.tool_calls:
                                    status_container.write(f"⚙️ **Action:** `{tool['name']}`")
                            elif msg.content:
                                if isinstance(msg.content, list):
                                    extracted_text = ""
                                    for block in msg.content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            extracted_text += block.get("text", "")
                                    final_response = extracted_text
                                else:
                                    final_response = msg.content
                                    
                        elif node_name == "tools":
                            status_container.write("✅ **Tools Execution Complete**")

                status_container.update(label="Complete", state="complete", expanded=False)
                st.write(final_response)
                return AIMessage(content=final_response)

    ai_message = asyncio.run(process_chat())
    st.session_state["messages"].append(ai_message)