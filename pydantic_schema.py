# Pydantic Schema for backend - FastAPI

from pydantic import BaseModel, Field
from typing import List, Any

class Structure(BaseModel):
    server_target: str = Field(description="Contain  the servers needed by the llm for performing the task.")
    method_name: str = Field(description="The methods/ tools required for the task")
    arguments: dict[str, Any] = Field(default={}, description="A Dictionary that contains all the arguments that needs to be send to the server in a key - value pair.") 