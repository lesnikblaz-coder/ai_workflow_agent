from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from src.db.models.workflow import Workflow
from src.schemas.workflow import ClaimedWorkflow
from src.enums import WorkflowStatus


class WorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workflow: Workflow) -> Workflow:
        self.session.add(workflow)

        await self.session.flush()

        return workflow

    async def get(self, workflow_id: UUID) -> Workflow | None:
        stmt = select(Workflow).where(Workflow.id == workflow_id)

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def claim_next(self) -> ClaimedWorkflow | None:
        stmt = (
            select(Workflow)
            .where(Workflow.status == WorkflowStatus.QUEUED)
            .order_by(Workflow.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        result = await self.session.execute(stmt)

        workflow: Workflow | None = result.scalar_one_or_none()

        if workflow is None:
            return None

        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now(timezone.utc)

        return ClaimedWorkflow(
            id=workflow.id,
            instruction=workflow.instruction
        )

    async def workflow_completion(self, workflow_id: UUID, result: str) -> Workflow | None:
        workflow = await self._get_workflow_by_id(workflow_id)

        if (
                workflow is None
                or workflow.status != WorkflowStatus.RUNNING
        ):
            return None

        workflow.status = WorkflowStatus.COMPLETED
        workflow.result = result
        workflow.finished_at = datetime.now(timezone.utc)

        return workflow

    async def workflow_fail(self, workflow_id: UUID, error_msg: str) -> Workflow | None:
        workflow = await self._get_workflow_by_id(workflow_id)

        if (
                workflow is None
                or workflow.status != WorkflowStatus.RUNNING
        ):
            return None

        workflow.status = WorkflowStatus.FAILED
        workflow.error_message = error_msg
        workflow.finished_at = datetime.now(timezone.utc)

        return workflow


    async def _get_workflow_by_id(self, workflow_id: UUID) -> Workflow | None:
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
        )

        result = await self.session.execute(stmt)

        workflow: Workflow | None = result.scalar_one_or_none()

        return workflow