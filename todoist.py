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
    You MUST use the Task ID to complete a task.
    """
    try:
        tasks = api.get_tasks()
        if not tasks:
            return "No active tasks found."
        
        output = "Active Tasks:\n"
        for task in tasks:
            if task.due:
                due = task.due.string if task.due else "No due date"
                # Crucial update: We must expose the task.id to the LLM
                output += f"- [ID: {task.id}] {task.content} (Due: {due})\n"
            else:
                print(f'Task: {task.content} has no due date')
        return output
    except Exception as e:
        return f"Error fetching tasks: {str(e)}"

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