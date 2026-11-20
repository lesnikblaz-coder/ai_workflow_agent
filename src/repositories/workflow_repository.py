from uuid import UUID, uuid4
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from src.db.models.workflow import Workflow
from src.schemas.workflow import ClaimedWorkflow
from src.enums import WorkflowStatus
from src.config import settings


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

        db_now = func.statement_timestamp()

        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = db_now
        workflow.lease_expires_at = db_now + timedelta(minutes=settings.LEASE_EXPIRY_MINUTES)

        # Generate and assign a claim token (changes each execution attempt)
        claim_token = uuid4()
        workflow.claim_token = claim_token

        return ClaimedWorkflow(
            id=workflow.id,
            instruction=workflow.instruction,
            claim_token=claim_token
        )

    async def workflow_completion(self, workflow_id: UUID, result: str, claim_token: UUID) -> Workflow | None:
        """
        Performs an atomic conditional update (completion).
        :param workflow_id: UUID
        :param result: str
        :param claim_token: UUID
        :return: updated Workflow | None
        """

        db_now = func.statement_timestamp()

        stmt = (
            update(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.claim_token == claim_token,
                Workflow.status == WorkflowStatus.RUNNING,
                Workflow.lease_expires_at > db_now
            )
            .values(
                status=WorkflowStatus.COMPLETED,
                result=result,
                finished_at=db_now,
                lease_expires_at=None,
                claim_token=None
            )
            .returning(Workflow)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def workflow_fail(self, workflow_id: UUID, error_msg: str, claim_token: UUID) -> Workflow | None:
        """
        Performs an atomic conditional update (failure).
        :param workflow_id: UUID
        :param error_msg: str
        :param claim_token: UUID
        :return: updated Workflow | None
        """

        db_now = func.statement_timestamp()

        stmt = (
            update(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.status == WorkflowStatus.RUNNING,
                Workflow.claim_token == claim_token,
                Workflow.lease_expires_at > db_now
            )
            .values(
                status=WorkflowStatus.FAILED,
                error_message=error_msg,
                finished_at=db_now,
                lease_expires_at=None,
                claim_token=None
            )
            .returning(Workflow)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def _get_workflow_by_id(self, workflow_id: UUID) -> Workflow | None:
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
        )

        result = await self.session.execute(stmt)

        workflow: Workflow | None = result.scalar_one_or_none()

        return workflow

    async def renew_lease(self, workflow_id: UUID, claim_token: UUID) -> Workflow | None:
        """
        Valid heartbeat operation extends the lease expiry timer.
        :param workflow_id:
        :param claim_token:
        :return: updated Workflow | None
        """

        db_now = func.statement_timestamp()

        stmt = (
            update(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.claim_token == claim_token,
                Workflow.status == WorkflowStatus.RUNNING,
                Workflow.lease_expires_at > db_now
            )
            .values(
                lease_expires_at=(
                        db_now + timedelta(minutes=settings.LEASE_EXPIRY_MINUTES)
                )
            )
            .returning(Workflow)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()