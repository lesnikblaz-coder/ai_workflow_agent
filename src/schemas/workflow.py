from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=300)