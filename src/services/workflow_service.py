from sqlalchemy.ext.asyncio import async_sessionmaker


from src.repositories.workflow_repository import WorkflowRepository
from src.db.models.workflow import Workflow
from src.enums import WorkflowStatus
from src.schemas.workflow import WorkflowResponse


class WorkflowService:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def create(self, instruction: str) -> WorkflowResponse:
        workflow = Workflow(
            instruction=instruction,
            status=WorkflowStatus.QUEUED
        )

        async with self.session_factory.begin() as session:
            repo = WorkflowRepository(session)

            workflow = await repo.create(workflow)

        return WorkflowResponse(
            id=workflow.id,
            status=workflow.status
        )