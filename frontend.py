import sys
import asyncio
import os
import uuid
import psycopg
from pathlib import Path
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from orchestrator import build_graph

# ==========================================
# 0. ASYNC SHOCK ABSORBER (CRITICAL)
# ==========================================
sys.modules['uvloop'] = None
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==========================================
# 1. PAGE CONFIG & STAGING DIRECTORY
# ==========================================
st.set_page_config(page_title="Agentic Orchestrator", page_icon="🧠", layout="wide")
st.title("🧠 Multi-Agent MCP Orchestrator")

UPLOAD_DIR = Path("./staging_vault")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. SESSION STATE — MUST BE BEFORE SIDEBAR
# ==========================================
welcome_text = """
👋 **Welcome to your Agentic Orchestrator!**

To bring your AI agents online, you need to provide your API keys in the sidebar. If you don't have them yet, you can generate them for free using the official developer consoles below:

* **Gemini (The Brain):** [Google AI Studio](https://aistudio.google.com/app/apikey)
* **Pinecone (Vector Database):** [Pinecone Console](https://app.pinecone.io/)
* **LlamaParse (Document Extraction):** [LlamaCloud](https://cloud.llamaindex.ai/)
* **Todoist (Task Management):** [Todoist Developer App Console](https://developer.todoist.com/appconsole.html)
* **Notion (Workspace Integration):** [Notion Integrations](https://www.notion.so/my-integrations)

Once your Gemini key is entered, the chat interface will unlock. 🚀
"""

if "user_thread_id" not in st.session_state:
    is_logged_in_early = getattr(st.user, "is_logged_in", False)
    if is_logged_in_early and getattr(st.user, "email", None):
        st.session_state["user_thread_id"] = f"user_{st.user.email}"
    else:
        st.session_state["user_thread_id"] = f"guest_{uuid.uuid4()}"

if "messages" not in st.session_state:
    st.session_state["messages"] = [AIMessage(content=welcome_text)]

# Tracks whether a document was ingested this session
# Resets to False when user removes the file or starts fresh
if "vault_active" not in st.session_state:
    st.session_state["vault_active"] = False

# Tracks the last ingested filename to detect new uploads
# Reset to None so the same file can be re-uploaded in a new session
if "last_processed_file" not in st.session_state:
    st.session_state["last_processed_file"] = None

# ==========================================
# 3. THE GLOBAL EXECUTION ENGINE
# ==========================================
async def process_chat():
    """
    Compiles the multi-agent graph, connects to Postgres memory,
    and streams events to the UI.
    Always returns a valid AIMessage — never None.
    """
    try:
        db_uri = os.getenv("POSTGRES_DB_URI")
        if not db_uri:
            st.error("❌ Environment variable 'POSTGRES_DB_URI' is missing. Check your .env file.")
            return AIMessage(content="❌ Database connection error. POSTGRES_DB_URI is not set.")

        current_thread = st.session_state["user_thread_id"]
        user_google_token = st.session_state.get("google_token")

        async with await psycopg.AsyncConnection.connect(
            db_uri,
            prepare_threshold=0,
            autocommit=True
        ) as conn:
            checkpointer = AsyncPostgresSaver(conn)
            await checkpointer.setup()
            app = await build_graph(checkpointer, user_token=user_google_token)

            with st.chat_message("assistant"):
                status_container = st.status("Agents are executing...", expanded=True)
                final_response = ""

                inputs = {"messages": st.session_state["messages"]}
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
                return AIMessage(content=final_response or "Agent completed with no response.")

    except Exception as e:
        error_str = str(e).lower()

        if any(keyword in error_str for keyword in [
            "quota", "rate limit", "ratelimit", "429",
            "resource_exhausted", "too many requests",
            "exceeded", "limit reached"
        ]):
            friendly = "⚠️ API limit reached. Please wait a moment and try again, or check your API quota on Google AI Studio."
            st.warning(friendly)
            return AIMessage(content=friendly)

        st.error(f"❌ Agent error: {str(e)}")
        return AIMessage(content=f"❌ Error: {str(e)}")

# ==========================================
# 4. THE DUAL-CREDENTIAL SIDEBAR (INPUTS)
# ==========================================
with st.sidebar:
    st.header("🔑 Developer Keys")
    st.markdown("Provide your API keys to unlock agent capabilities.")

    user_gemini_key     = st.text_input("Gemini API Key",   type="password")
    user_todoist_token  = st.text_input("Todoist Token",    type="password")
    user_notion_key     = st.text_input("Notion API Key",   type="password")
    user_pinecone_key   = st.text_input("Pinecone API Key", type="password")
    user_llamaparse_key = st.text_input("LlamaParse Key",   type="password")

# ==========================================
# 4.5. ENVIRONMENT INJECTION
# ==========================================
if user_gemini_key:     os.environ["GOOGLE_API_KEY"]      = user_gemini_key
if user_todoist_token:  os.environ["TODOIST_API_TOKEN"]   = user_todoist_token
if user_pinecone_key:   os.environ["PINECONE_API_KEY"]    = user_pinecone_key
if user_notion_key:     os.environ["NOTION_API_KEY"]      = user_notion_key
if user_llamaparse_key: os.environ["LLAMA_CLOUD_API_KEY"] = user_llamaparse_key

# ==========================================
# 5. SIDEBAR ACTIONS & AUTOMATED INGESTION
# ==========================================
with st.sidebar:
    st.markdown("---")
    st.header("📅 Google Workspace")
    st.markdown("Connect identity services securely.")

    is_logged_in = getattr(st.user, "is_logged_in", False)

    if not is_logged_in:
        if st.button("🔗 Log in with Google"):
            st.login("google")
            st.stop()
    else:
        st.success(f"Connected as {st.user.name}")
        if "access" in st.user.tokens:
            st.session_state["google_token"] = st.user.tokens["access"]
        if st.button("Disconnect"):
            st.logout()

        if getattr(st.user, "email", None):
            email_thread = f"user_{st.user.email}"
            if st.session_state.get("user_thread_id") != email_thread:
                st.session_state["user_thread_id"] = email_thread

    st.markdown("---")

    # KNOWLEDGE VAULT (AUTOMATED INGESTION)
    st.header("🗄️ Knowledge Vault")

    # Show currently active document if any
    if st.session_state["vault_active"] and st.session_state["last_processed_file"]:
        st.info(f"📄 Active: **{st.session_state['last_processed_file']}**")
        if st.button("🗑️ Remove Document"):
            st.session_state["vault_active"] = False
            st.session_state["last_processed_file"] = None
            st.rerun()

    uploaded_file = st.file_uploader(
        "Upload a new document (replaces current)",
        type=["pdf", "txt", "md"],
        # Use a dynamic key so the uploader resets after each successful ingest
        # allowing the same file to be re-uploaded in a new session
        key=f"uploader_{st.session_state.get('upload_count', 0)}"
    )

    if uploaded_file is not None:
        if not os.environ.get("GOOGLE_API_KEY"):
            st.warning("⚠️ Enter your **Gemini API Key** above before uploading a document.")
        else:
            # Trigger ingest if this is a different file than the last ingested one
            if st.session_state["last_processed_file"] != uploaded_file.name:
                file_id = str(uuid.uuid4())
                safe_filename = f"{file_id}_{uploaded_file.name}"
                staging_file_path = UPLOAD_DIR / safe_filename

                with open(staging_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.success("✅ File securely staged!")

                # Always use 'default' namespace — each user has their own
                # Pinecone API key so no cross-user collision is possible
                ingest_command = (
                    f"CRITICAL SYSTEM COMMAND: Execute the `ingest_document` tool. "
                    f"You MUST pass BOTH parameters exactly: "
                    f"filepath='{staging_file_path}', namespace='default'. "
                    f"Reply ONLY with the exact raw text returned by the tool. "
                    f"If the tool returns an error, output the exact error. "
                    f"Do not summarize or hallucinate."
                )

                st.session_state["messages"].append(HumanMessage(content=ingest_command))
                ai_message = asyncio.run(process_chat())
                st.session_state["messages"].append(ai_message)

                # Mark vault as active and record filename
                st.session_state["vault_active"] = True
                st.session_state["last_processed_file"] = uploaded_file.name

                # Increment upload counter to reset the uploader widget
                # This allows re-uploading the same filename again later
                st.session_state["upload_count"] = st.session_state.get("upload_count", 0) + 1

                st.rerun()

# ==========================================
# 6. RENDER CHAT HISTORY
# ==========================================
for msg in st.session_state["messages"]:
    # Hide all backend system commands
    if "CRITICAL SYSTEM COMMAND:" in getattr(msg, "content", ""):
        continue

    if isinstance(msg, HumanMessage):
        # Strip the hidden [SYSTEM: ...] namespace hint before displaying
        display_content = msg.content.split("\n\n[SYSTEM")[0].strip()
        if display_content:
            st.chat_message("user").write(display_content)

    elif isinstance(msg, AIMessage) and msg.content:
        # Hide ingest success/error responses — backend confirmations only
        content = msg.content
        if content.startswith("Success: Ingested") or content.startswith("Ingestion Error"):
            continue
        st.chat_message("assistant").write(content)

# ==========================================
# 7. USER CHAT TRIGGER
# ==========================================
is_chat_enabled = bool(os.environ.get("GOOGLE_API_KEY"))

if not is_chat_enabled:
    st.info("👈 Please enter your **Gemini API Key** in the sidebar to unlock the chat interface.")

user_input = st.chat_input("Command your agents...", disabled=not is_chat_enabled)

if user_input:
    st.chat_message("user").write(user_input)

    # Inject vault instruction based on whether a document is active this session
    if st.session_state.get("vault_active"):
        augmented_input = (
            f"{user_input}\n\n"
            f"[SYSTEM INSTRUCTION — MANDATORY: The user has uploaded a document. "
            f"You MUST call the `query_vault` tool with namespace='default' "
            f"to answer any question about the uploaded document. "
            f"Do NOT answer from memory. Call the tool first.]"
        )
    else:
        augmented_input = (
            f"{user_input}\n\n"
            f"[SYSTEM: No document has been uploaded this session. "
            f"Do NOT call query_vault — it will return stale data.]"
        )

    st.session_state["messages"].append(HumanMessage(content=augmented_input))
    ai_message = asyncio.run(process_chat())
    st.session_state["messages"].append(ai_message)
    st.rerun()