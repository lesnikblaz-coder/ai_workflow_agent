from fastapi import APIRouter

from src.schemas import workflow as wf
from src.api import dependencies as deps


workflows_router = APIRouter(
    prefix="/v1/workflows",
    tags=["Workflows"]
)

@workflows_router.post("")
async def create_workflow(request: wf.WorkflowCreateRequest, service: deps.WorkflowServiceDep):
    return service.create(instruction=request.instruction)