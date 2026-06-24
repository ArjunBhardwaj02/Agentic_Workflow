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
You are a highly capable Multi-Agent Orchestrator. You have access to tools for RAG retrieval, local file handling, and Google Workspace operations.

CRITICAL RULES FOR GOOGLE WORKSPACE:
1. When creating a new Google Sheet using `create_sheet`, the system will automatically generate a default tab named "Sheet1".
2. If you need to immediately write data to a newly created sheet, you MUST use "Sheet1" as the `range_name` parameter for the `write_sheet` tool.
3. Structure all row data clearly as a list of strings.
"""

async def build_graph(checkpointer: BaseCheckpointSaver = None):
    #Declaring the Servers
    SERVERS = {
    "filesystem":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "./filesystem.py"
       ]
    },
    "ragsystem":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "./ragsystem.py"
       ]
    },
    "google-workspace":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "./custom_doc_and_sheet.py"
       ]
    },
    "duckduckgo-search": {
        "transport": "stdio",
        "command": "uvx",
        "args": [
            "--quiet", # avoid downloading status logs
            "duckduckgo-mcp-server"
        ]
    },
    "notion": {
    "transport": "stdio",
    # "command": "npx.cmd", #for windows
    "command" : "npx", #for linux
    "args": ["-y", "@notionhq/notion-mcp-server"],
    "env": {
        "OPENAPI_MCP_HEADERS": json.dumps({
            "Authorization": f"Bearer {os.getenv('NOTION_API_TOKEN')}",
            "Notion-Version": "2022-06-28"
        })
    }
},
    "todoist": {
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "python",
            "./todoist.py"
        ]
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