from fastapi import Depends
from typing import Annotated

from src.db.base import AsyncSessionLocal
from src.services.workflow_service import WorkflowService


# SERVICES
async def _get_workflow_service():
    return WorkflowService(
        session_factory=AsyncSessionLocal
    )

WorkflowServiceDep = Annotated[WorkflowService, Depends(_get_workflow_service)]