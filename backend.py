from fastapi import FastAPI, HTTPException
from pydantic_schema import Structure
from langchain_mcp_adapters.client import MultiServerMCPClient
import os,json
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="MCP Orcherstrator Gateway")
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

@app.post('/api/v1/execute')
async def execute_tool(request:Structure):
    #check the server name if it is present in the SERVERS
    if request.server_target in SERVERS:
        #instead of sending all the servers to the MultiServerMCPClient, we are creating a new mini dictionary of only required tool and sending it

        #create dictionary that contain only required server
        target_config = {request.server_target : SERVERS[request.server_target]}

        #instiate the MultiServerMCPClient and pass the dictionary
        client = MultiServerMCPClient(target_config)
        # retrieve the langchain tools
        tools = await client.get_tools()
        # check if the tool name matches with our method name
        for tool in tools:
            if tool.name == request.method_name:
            #tool found execute with ainvoke by passing the arguments 
                output = await tool.ainvoke(request.arguments)
            #return json response
                return {"status": "success", "data": output}
        else:
            #no tool match than error 404
            raise HTTPException(status_code=404, detail="Tool was not Found!")
    else:
        raise HTTPException(status_code=404,detail=f"Target Server '{request.server_target}' is not present")