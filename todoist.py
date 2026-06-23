import os
from fastmcp import FastMCP
from todoist_api_python.api import TodoistAPI
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("todoist-server")
api = TodoistAPI(os.getenv("TODOIST_API_TOKEN"))

@mcp.tool()
async def add_task(content: str, due_string: str = "today", priority: int = 1) -> str:
    """
    Adds a new task to the user's Todoist Inbox.
    Args:
        content: The name of the task.
        due_string: Natural language date (e.g., 'tomorrow at 12pm', 'next Monday', 'every day').
        priority: 1 (Normal), 2 (Medium), 3 (High), 4 (Urgent).
    """
    try:
        task = api.add_task(
            content=content,
            due_string=due_string,
            priority=priority
        )
        return f"Success: Task '{content}' added successfully. Task ID: {task.id}"
    except Exception as e:
        return f"Error adding task: {str(e)}"

@mcp.tool()
async def get_active_tasks() -> str:
    """
    Fetches the user's current active tasks from Todoist.
    Returns the Task ID, Content, and Due Date. 
    """
    try:
        raw_response = api.get_tasks()
        
        # The Flattener: Unpack the paginator pages into a single list
        tasks = []
        if raw_response:
            for item in raw_response:
                # If the item is a page (a list of tasks), extend our main list
                if isinstance(item, list):
                    tasks.extend(item)
                # If the item is just a raw task, append it
                else:
                    tasks.append(item)
                    
        if not tasks:
            return "No active tasks found in the database."
            
        output = f"Active Tasks ({len(tasks)} found):\n"
        
        for index, task in enumerate(tasks):
            try:
                due = task.due.string if getattr(task, 'due', None) else "No due date"
                content = getattr(task, 'content', 'Unknown Content')
                task_id = getattr(task, 'id', 'Unknown ID')
                priority = getattr(task, 'priority', 'Unknown')
                
                output += f"{index + 1}. [ID: {task_id}] {content} (Due: {due}, Priority: {priority})\n"
            except Exception as loop_error:
                output += f"- Error reading task at index {index}: {str(loop_error)}\n"
                
        return output
        
    except Exception as e:
        return f"Error connecting to Todoist: {str(e)}"

@mcp.tool()
async def complete_task(task_id: str) -> str:
    """
    Marks a specific Todoist task as completed.
    You MUST pass the exact Task ID (retrieved from get_active_tasks).
    """
    try:
        # The Todoist API uses close_task to mark it as done
        is_success = api.close_task(task_id=task_id)
        if is_success:
            return f"Success: Task {task_id} has been marked as completed."
        else:
            return f"Error: Failed to complete task {task_id}."
    except Exception as e:
        return f"Error completing task: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")