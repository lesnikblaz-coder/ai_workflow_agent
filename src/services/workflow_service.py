from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID
from fastapi import HTTPException, status

from src.repositories.workflow_repository import WorkflowRepository
from src.db.models.workflow import Workflow
from src.enums import WorkflowStatus
from src.schemas.workflow import WorkflowPostResponse, WorkflowGetResponse, ClaimedWorkflow
from src.exceptions.custom import WorkflowOwnershipLostError, LeaseRenewalRejectedError, DatabaseSaveError


class WorkflowService:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def create(self, instruction: str) -> WorkflowPostResponse:
        try:
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

        except SQLAlchemyError as exc:
            raise DatabaseSaveError() from exc

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
        try:
            async with self.session_factory.begin() as session:
                repo = WorkflowRepository(session)

                return await repo.claim_next()

        except SQLAlchemyError as exc:
            raise DatabaseSaveError() from exc

    async def complete(self, workflow_id: UUID, result: str, claim_token: UUID) -> None:
        try:
            async with self.session_factory.begin() as session:
                repo = WorkflowRepository(session)

                workflow = await repo.workflow_completion(
                    workflow_id=workflow_id,
                    result=result,
                    claim_token=claim_token
                )

                if workflow is None:
                    raise WorkflowOwnershipLostError(
                        workflow_id=workflow_id
                    )

        except SQLAlchemyError as exc:
            raise DatabaseSaveError() from exc

    async def fail(self, workflow_id: UUID, error_msg: str, claim_token: UUID) -> None:
        try:
            async with self.session_factory.begin() as session:
                repo = WorkflowRepository(session)

                workflow = await repo.workflow_fail(
                    workflow_id=workflow_id,
                    error_msg=error_msg,
                    claim_token=claim_token
                )

                if workflow is None:
                    raise WorkflowOwnershipLostError(
                        workflow_id=workflow_id
                    )

        except SQLAlchemyError as exc:
            raise DatabaseSaveError() from exc

    async def renew_lease(self, workflow_id: UUID, claim_token: UUID) -> None:
        try:
            async with self.session_factory.begin() as session:
                repo = WorkflowRepository(session)

                workflow = await repo.renew_lease(
                    workflow_id=workflow_id,
                    claim_token=claim_token
                )

                if not workflow:
                    raise LeaseRenewalRejectedError(
                        workflow_id=workflow_id
                    )

        except SQLAlchemyError as exc:
            raise DatabaseSaveError() from exc