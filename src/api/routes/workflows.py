from fastapi import APIRouter, status
from uuid import UUID

from src.schemas import workflow as wf
from src.api import dependencies as deps

workflows_router = APIRouter(
    prefix="/v1/workflows",
    tags=["Workflows"]
)


@workflows_router.post("", response_model=wf.WorkflowPostResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_workflow(request: wf.WorkflowCreateRequest,
                          service: deps.WorkflowServiceDep) -> wf.WorkflowPostResponse:
    return await service.create(instruction=request.instruction)


@workflows_router.get("/{workflow_id}", response_model=wf.WorkflowGetResponse)
async def get_workflow(workflow_id: UUID, service: deps.WorkflowServiceDep) -> wf.WorkflowGetResponse:
    return await service.get(workflow_id)