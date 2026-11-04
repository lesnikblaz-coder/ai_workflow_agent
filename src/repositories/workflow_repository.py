from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.workflow import Workflow


class WorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workflow: Workflow) -> Workflow:
        self.session.add(workflow)
        await self.session.flush()
        return workflow