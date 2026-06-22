from typing import TypedDict,Sequence,Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage,SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
import os,asyncio,json
from dotenv import load_dotenv
load_dotenv()

class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

#Declaring the Servers
SERVERS = {
    "filesystem":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "E:/agentic_workflow/filesystem.py"
       ]
    },
    "ragsystem":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "E:/agentic_workflow/ragsystem.py"
       ]
    },
    "google-workspace":{
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "fastmcp",
            "run",
            "E:/agentic_workflow/custom_doc_and_sheet.py"
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
    "command": "npx.cmd",
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
            "E:/agentic_workflow/todoist.py"
        ]
    }
}


model = ChatGoogleGenerativeAI(api_key = os.getenv("GOOGLE_API_KEY"),model = "gemma-4-31b-it")

#system instruction for excel sheet mcp server
SYSTEM_INSTRUCTIONS = """
You are a highly capable Multi-Agent Orchestrator. You have access to tools for RAG retrieval, local file handling, and Google Workspace operations.

CRITICAL RULES FOR GOOGLE WORKSPACE:
1. When creating a new Google Sheet using `create_sheet`, the system will automatically generate a default tab named "Sheet1".
2. If you need to immediately write data to a newly created sheet, you MUST use "Sheet1" as the `range_name` parameter for the `write_sheet` tool.
3. Structure all row data clearly as a list of strings.
"""

async def build_and_run_graph():
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
    # input = {"messages":[("user","What files are in my current Directory ?")]}

    
    # input = {"messages": [("user", "Query the ragsystem to find the ctc mentioned. Once you have the answer, create a new file in my current directory called 'vault_summary.txt' and write the explanation into that file.")]}

#     input = {
#     "messages": [
#         ("user", "Read the Resume file present on google docs and generate a summary of it and save it in new google docs file called 'summary'.")
#     ]
# }

#     input = {
#     "messages": [
#         ("user", "Read the document with name meenal_resume present in google drive. Generate a summary of its contents, create a new Google Doc called 'Resume Summary', and append the summary into that new document.")
#     ]
# }
    
#     input = {
#     "messages": [
#         ("user", "1. Use DuckDuckGo Search to find the latest news regarding the 'OpenAI o1 model' release or capabilities.\n"
#                  "2. Synthesize the search results into a concise summary.\n"
#                  "3. Create a new file in my current directory called 'o1_research.txt' and write the summary into it.")
#     ]
# }
#     input = {
#     "messages": [
#         ("user", "1. Check my calendar for today to see if I am busy this afternoon. 2. I want to spend 2 hours working on my 'Automated AI Exam Grader' project tomorrow starting at 10:00 AM. Create a calendar event for this. 3. Create a draft email to arjunbhardwaj0274@gmail.com with a short summary of my schedule for today, and confirm that tomorrow's project block was successfully scheduled.")
#     ]
# }

    input = {
    "messages": [
        ("user", "1. Check my current active tasks in Todoist.\n"
                 "2. Add a new high-priority task (Priority 4) called 'Master FastMCP and LangGraph' due today.\n"
                 "3. Check my active tasks again to verify it was added and get its Task ID.\n"
                 )
    ]
}

    async for event in app.astream(input, stream_mode="values"):
        message = event["messages"][-1]
        message.pretty_print()

if __name__ =='__main__':
    asyncio.run(build_and_run_graph())