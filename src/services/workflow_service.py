from sqlalchemy.ext.asyncio import async_sessionmaker
from uuid import UUID
from fastapi import HTTPException, status

from src.repositories.workflow_repository import WorkflowRepository
from src.db.models.workflow import Workflow
from src.enums import WorkflowStatus
from src.schemas.workflow import WorkflowPostResponse, WorkflowGetResponse, ClaimedWorkflow


class WorkflowService:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def create(self, instruction: str) -> WorkflowPostResponse:
        workflow = Workflow(
            instruction=instruction,
            status=WorkflowStatus.QUEUED
        )

        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            workflow = await repo.create(workflow)

        return WorkflowPostResponse(
            id=workflow.id,
            status=workflow.status
        )

    async def get(self, workflow_id: UUID) -> WorkflowGetResponse:
        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)
            workflow = await repo.get(workflow_id)

        if not workflow:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return WorkflowGetResponse(
            status=workflow.status,
            result=workflow.result
        )

    async def claim_next(self) -> ClaimedWorkflow | None:
        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            return await repo.claim_next()

    async def complete(self, workflow_id: UUID, result: str):
        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            await repo.workflow_completion(workflow_id, result)

    async def fail(self, workflow_id: UUID):
        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            await repo.workflow_fail(workflow_id)