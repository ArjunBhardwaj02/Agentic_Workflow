import streamlit as st
import asyncio
import uuid
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage

# Import components from your newly refactored orchestrator module
from orchestrator import build_graph

# 1. Page Configuration & Staging Setup
# Changed layout to "wide" to accommodate the sidebar
st.set_page_config(page_title="Multi-Agent Orchestrator", page_icon="🧠", layout="wide")
st.title("🧠 Multi-Agent MCP Orchestrator")

# Define an absolute staging path
UPLOAD_DIR = Path("E:/agentic_workflow/staging_vault")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 2. Sidebar: The File Ingestion Gateway
with st.sidebar:
    st.header("🗄️ Knowledge Vault")
    st.markdown("Upload documents to staging for AI ingestion.")
    
    # The file uploader widget
    uploaded_file = st.file_uploader("Select Document", type=["pdf", "txt", "md"])

    if uploaded_file is not None:
        # The Collision Fix: Prepend a UUID to the filename
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{uploaded_file.name}"
        staging_file_path = UPLOAD_DIR / safe_filename
        
        # Flush the volatile RAM buffer to the physical disk
        with open(staging_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        st.success("✅ File securely staged!")
        st.caption("Tell your agent to ingest this exact path:")
        # Provide the path in a copyable code block
        st.code(str(staging_file_path), language="text")

# 3. Session Memory Initialization
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# 4. Render Historical Chat
for msg in st.session_state["messages"]:
    if isinstance(msg, HumanMessage):
        st.chat_message("user").write(msg.content)
    elif isinstance(msg, AIMessage) and msg.content:
        st.chat_message("assistant").write(msg.content)

# 5. Input Trigger
user_input = st.chat_input("Command your agents...")

if user_input:
    # Render user prompt immediately
    st.chat_message("user").write(user_input)
    st.session_state["messages"].append(HumanMessage(content=user_input))

    # 6. Async Graph Execution Engine
    async def process_chat():
        # Initialize the shared graph instance using your modular backend factory
        app = await build_graph()
        
        with st.chat_message("assistant"):
            # Create a collapsible real-time status widget
            status_container = st.status("Agents are analyzing the task...", expanded=True)
            final_response = ""
            
            inputs = {"messages": st.session_state["messages"]}
            
            # Stream the updates state mode to isolate individual step updates
            async for event in app.astream(inputs, stream_mode="updates"):
                for node_name, node_state in event.items():
                    if node_name == "agent":
                        msg = node_state["messages"][-1]
                        
                        # Look for pending tool calls emitted by the core model execution
                        if msg.tool_calls:
                            for tool in msg.tool_calls:
                                status_container.write(f"⚙️ **Action:** Requesting tool `{tool['name']}`...")
                        
                        # Safely extract the final text response, ignoring internal "thinking" blocks
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
                        status_container.write("✅ **Tools Execution:** Results returned to the brain.")

            # Collapse the thinking box cleanly when execution ends
            status_container.update(label="Execution Complete!", state="complete", expanded=False)
            st.write(final_response)
            
            return AIMessage(content=final_response)

    # 7. Bridge Sync Streamlit with Async Graph
    ai_message = asyncio.run(process_chat())
    st.session_state["messages"].append(ai_message)