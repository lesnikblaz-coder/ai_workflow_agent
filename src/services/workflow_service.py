from uuid import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker


from src.repositories.workflow_repository import WorkflowRepository
from src.db.models.workflow import Workflow
from src.enums import WorkflowStatus


class WorkflowService:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def create(self, instruction: str) -> tuple[UUID, WorkflowStatus]:
        workflow = Workflow(
            instruction=instruction,
            status=WorkflowStatus.QUEUED
        )

        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            workflow = await repo.create(workflow)

        return workflow.id, workflow.status