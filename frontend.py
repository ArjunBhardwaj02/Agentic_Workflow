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

# ==========================================
# 2.5. USER NAMESPACE HELPER
# ==========================================
def get_user_namespace() -> str:
    """
    Returns a Pinecone namespace tied to the logged-in user's email.
    - Logged-in users: stable namespace across sessions (user_name_domain_com)
    - Guest users: session-scoped namespace (guest_{uuid})
    - Sanitized to be Pinecone-safe (no @ or . characters)
    """
    is_logged_in = getattr(st.user, "is_logged_in", False)
    if is_logged_in and getattr(st.user, "email", None):
        safe_email = st.user.email.replace("@", "_").replace(".", "_")
        return f"user_{safe_email}"
    return st.session_state.get("user_thread_id", "guest_default")

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
        # Scopes are configured via client_kwargs in .streamlit/secrets.toml
        if st.button("🔗 Log in with Google"):
            st.login("google")
            st.stop()
    else:
        st.success(f"Connected as {st.user.name}")
        if "access" in st.user.tokens:
            st.session_state["google_token"] = st.user.tokens["access"]
        if st.button("Disconnect"):
            st.logout()

        # Re-bind thread_id to email now that we know it
        if getattr(st.user, "email", None):
            email_thread = f"user_{st.user.email}"
            if st.session_state.get("user_thread_id") != email_thread:
                st.session_state["user_thread_id"] = email_thread

    st.markdown("---")

    # KNOWLEDGE VAULT (AUTOMATED INGESTION)
    st.header("🗄️ Knowledge Vault")
    uploaded_file = st.file_uploader("Stage Document", type=["pdf", "txt", "md"])

    if uploaded_file is not None:
        if not os.environ.get("GOOGLE_API_KEY"):
            st.warning("⚠️ Enter your **Gemini API Key** above before uploading a document.")
        else:
            file_id = str(uuid.uuid4())
            safe_filename = f"{file_id}_{uploaded_file.name}"
            staging_file_path = UPLOAD_DIR / safe_filename

            if (
                "last_processed_file" not in st.session_state
                or st.session_state["last_processed_file"] != uploaded_file.name
            ):
                with open(staging_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.success("✅ File securely staged!")

                # Get the user's personal namespace — isolates their data in Pinecone
                # and auto-deletes their previous document on new upload
                user_namespace = get_user_namespace()

                ingest_command = (
                    f"CRITICAL SYSTEM COMMAND: Execute the `ingest_document` tool. "
                    f"You MUST pass BOTH parameters exactly: "
                    f"filepath='{staging_file_path}', namespace='{user_namespace}'. "
                    f"Reply ONLY with the exact raw text returned by the tool. "
                    f"If the tool returns an error, output the exact error. "
                    f"Do not summarize or hallucinate."
                )

                st.session_state["messages"].append(HumanMessage(content=ingest_command))
                ai_message = asyncio.run(process_chat())
                st.session_state["messages"].append(ai_message)
                st.session_state["last_processed_file"] = uploaded_file.name
                st.rerun()

# ==========================================
# 6. RENDER CHAT HISTORY
# ==========================================
for msg in st.session_state["messages"]:
    if "CRITICAL SYSTEM COMMAND:" in getattr(msg, "content", ""):
        continue
    if isinstance(msg, HumanMessage):
        st.chat_message("user").write(msg.content)
    elif isinstance(msg, AIMessage) and msg.content:
        st.chat_message("assistant").write(msg.content)

# ==========================================
# 7. USER CHAT TRIGGER
# ==========================================
is_chat_enabled = bool(os.environ.get("GOOGLE_API_KEY"))

if not is_chat_enabled:
    st.info("👈 Please enter your **Gemini API Key** in the sidebar to unlock the chat interface.")

user_input = st.chat_input("Command your agents...", disabled=not is_chat_enabled)

if user_input:
    st.chat_message("user").write(user_input)

    # Inject namespace hint so agent always searches the correct user's vault
    user_namespace = get_user_namespace()
    augmented_input = (
        f"{user_input}\n\n"
        f"[SYSTEM: If you need to search the knowledge vault, "
        f"always use namespace='{user_namespace}']"
    )

    st.session_state["messages"].append(HumanMessage(content=augmented_input))
    ai_message = asyncio.run(process_chat())
    st.session_state["messages"].append(ai_message)
    st.rerun()