from pathlib import Path
from fastmcp import FastMCP
import asyncio
import aiofile


mcp = FastMCP("File Handling System")

@mcp.tool()
async def read_file(filepath: str) ->str:
    try:

        p = Path(filepath)
        if not p.is_file():
            return "Not a Readable File!"
        
        async with aiofile.async_open(p, mode='r',encoding = "UTF-8") as f:
            content = await f.read()
        
        return content
    except Exception as e:
        return f"Error Reading the file: {str(e)}"

@mcp.tool()
async def write_file(filepath:str, content:str) ->str:
    try:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofile.async_open(p, mode='w',encoding = "UTF-8") as f:
            await f.write(content)
        return "Data Successfully entered!"
    except Exception as e:
        return f"Error Writing the file: {str(e)}"
    
if __name__ == '__main__':
    mcp.run()