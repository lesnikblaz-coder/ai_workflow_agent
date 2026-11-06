from pydantic import BaseModel, Field
from uuid import UUID

from src.enums import WorkflowStatus


class WorkflowCreateRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=300)


class WorkflowPostResponse(BaseModel):
    id: UUID
    status: WorkflowStatus


class WorkflowGetResponse(BaseModel):
    status: WorkflowStatus
    result: str | None

class ClaimedWorkflow(BaseModel):
    id: UUID
    instruction: str