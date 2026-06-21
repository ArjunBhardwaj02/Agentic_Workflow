from pathlib import Path
from fastmcp import FastMCP
import asyncio
import aiofile
import os


mcp = FastMCP("File Handling System")

@mcp.tool()
async def read_file(filepath: str) ->str:
    """Read a specific file"""
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
    """Edit an existing file or create a new file if not exist with the detail user asks. """
    try:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofile.async_open(p, mode='w',encoding = "UTF-8") as f:
            await f.write(content)
        return "Data Successfully entered!"
    except Exception as e:
        return f"Error Writing the file: {str(e)}"
    
@mcp.tool()
async def list_directory(directory_path: str = '.'):
    """List all the files present in the directory"""
    try:
        p = os.path.abspath(directory_path)
        if os.path.isdir(p):
            return '\n'.join(os.listdir(p))
        else:
            return f"Error: Provided path is not a directory!"
    except Exception as e:
        return f"Error Reading the directory: {str(e)}"

if __name__ == '__main__':
    mcp.run()