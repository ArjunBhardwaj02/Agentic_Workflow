from typing import TypedDict,Sequence,Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
import os,asyncio
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
    }
    
}


model = ChatGoogleGenerativeAI(api_key = os.getenv("GOOGLE_API_KEY"),model = "gemma-4-31b-it")

async def build_and_run_graph():
    client = MultiServerMCPClient(SERVERS)
    tool = await client.get_tools()
    bound_model = model.bind_tools(tool)

    async def agent_node(state: GraphState):
        """The Brain: It reads the state and invoke the LLM"""
        message = state['messages']
        response = await bound_model.ainvoke(message)

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

    
    input = {"messages": [("user", "Query the ragsystem to find the ctc mentioned. Once you have the answer, create a new file in my current directory called 'vault_summary.txt' and write the explanation into that file.")]}

    async for event in app.astream(input, stream_mode="values"):
        message = event["messages"][-1]
        message.pretty_print()

if __name__ =='__main__':
    asyncio.run(build_and_run_graph())