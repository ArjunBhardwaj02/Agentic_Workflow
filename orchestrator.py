from typing import TypedDict,Sequence,Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage,SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
import os,asyncio,json
from dotenv import load_dotenv
load_dotenv()

class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


#system instruction for excel sheet mcp server
SYSTEM_INSTRUCTIONS = """
You are a highly capable Multi-Agent Orchestrator. You have access to tools for RAG retrieval, local file handling, Todoist, and Google Workspace operations.

CRITICAL ROUTING RULES:
1. THE SEMANTIC VAULT (RAG): If the user mentions "the uploaded PDF", "the vault", "the document I just provided", or asks a general question about file context without specifying Google Drive, you MUST use the `query_vault` tool. Do not guess; search the vault.
2. GOOGLE WORKSPACE: When creating a new Google Sheet using `create_sheet`, the system will automatically generate a default tab named "Sheet1". If you need to immediately write data to a newly created sheet, you MUST use "Sheet1" as the `range_name` parameter for the `write_sheet` tool. Structure all row data clearly as a list of strings.
3. AMBIGUITY: If the user asks about a file but you don't know if it's in the Vault or Google Drive, ask them to clarify which system to search.
"""

async def build_graph(checkpointer: BaseCheckpointSaver = None):
    #Declaring the Servers
    SERVERS = {
        "filesystem": {
            "transport": "stdio",
            "command": "fastmcp",
            "args": ["run", "./filesystem.py"],
            "env": {**os.environ}
        },
        "ragsystem": {
            "transport": "stdio",
            "command": "fastmcp",
            "args": ["run", "./ragsystem.py"],
            "env": {**os.environ}
        },
        "google-workspace": {
            "transport": "stdio",
            "command": "fastmcp",
            "args": ["run", "./custom_doc_and_sheet.py"],
            "env": {**os.environ}
        },
        "duckduckgo-search": {
            "transport": "stdio",
            "command": "duckduckgo-mcp-server",
            "args": []
        },
        "notion": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {
                "OPENAPI_MCP_HEADERS": json.dumps({
                    "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
                    "Notion-Version": "2022-06-28"
                })
            }
        },
        "todoist": {
            "transport": "stdio",
            "command": "python",
            "env": {**os.environ},
            "args": ["./todoist.py"]
        }
    }



    model = ChatGoogleGenerativeAI(api_key = os.getenv("GOOGLE_API_KEY"),model = "gemma-4-31b-it")
    client = MultiServerMCPClient(SERVERS)
    tool = await client.get_tools()
    bound_model = model.bind_tools(tool)

    async def agent_node(state: GraphState):
        """The Brain: It reads the state and invoke the LLM"""
        messages = state['messages']
        if not messages or getattr(messages[0], "type", "") != "system":
            messages = [SystemMessage(content=SYSTEM_INSTRUCTIONS)] + list(messages)
        response = await bound_model.ainvoke(messages)

        return {"messages": [response]}
        
    tool_node = ToolNode(tool)

    workflow = StateGraph(GraphState)

    workflow.add_node("agent",agent_node)
    workflow.add_node("tools",tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent",tools_condition)
    workflow.add_edge("tools","agent")

    app = workflow.compile()

    print("Graph Compiled")
    
    app = workflow.compile(checkpointer=checkpointer)
    return app

async def run_terminal(query:str):
    app =await build_graph()
    input = {"messages":[("user",f"{query}")]}

    async for event in app.astream(input=input, stream_mode="values"):
        message = event['messages'][-1]
        message.pretty_print()

if __name__ =='__main__':
    asyncio.run(run_terminal("Check my current active tasks in Todoist"))