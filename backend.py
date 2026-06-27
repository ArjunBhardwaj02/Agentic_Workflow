from fastapi import FastAPI, HTTPException
from pydantic_schema import Structure
from langchain_mcp_adapters.client import MultiServerMCPClient
import os,json
import uvicorn
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="MCP Orcherstrator Gateway")
SERVERS = {
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

@app.post('/api/v1/execute')
async def execute_tool(request:Structure):
    #check the server name if it is present in the SERVERS
    if request.server_target in SERVERS:
        #instead of sending all the servers to the MultiServerMCPClient, we are creating a new mini dictionary of only required tool and sending it

        #create dictionary that contain only required server
        target_config = {request.server_target : SERVERS[request.server_target]}

        if request.server_target == "notion" and os.getenv("NOTION_API_KEY"):
            target_config["notion"]["env"]["OPENAPI_MCP_HEADERS"] = json.dumps({
                "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
                "Notion-Version": "2022-06-28"
            })

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
    
if __name__ == "__main__":
    # If deployment environment mandates port 8080, run here.
    # Uvicorn binds to 0.0.0.0 to accept external traffic in cloud containers.
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)