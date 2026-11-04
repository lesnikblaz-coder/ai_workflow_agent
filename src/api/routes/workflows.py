from fastapi import APIRouter

from src.schemas import workflow as wf
from src.api import dependencies as deps


workflows_router = APIRouter(
    prefix="/v1/workflows",
    tags=["Workflows"]
)

@workflows_router.post("", response_model=wf.WorkflowResponse)
async def create_workflow(request: wf.WorkflowCreateRequest, service: deps.WorkflowServiceDep) -> wf.WorkflowResponse:
    return await service.create(instruction=request.instruction)