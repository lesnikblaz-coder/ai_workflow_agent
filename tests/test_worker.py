import asyncio

from sqlalchemy import select, delete

from src.enums import WorkflowStatus
from src.services.workflow_service import WorkflowService
from tests.conftest import TestAsyncSessionLocal
from src.db.models.workflow import Workflow


async def test_two_workers_cannot_claim_same_workflow():
    # create one queued workflow and commit it
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    workflow = await service.create(
        instruction="concurrency test"
    )

    workflow_id = workflow.id

    try:

        service_a = WorkflowService(
            session_factory=TestAsyncSessionLocal
        )
        service_b = WorkflowService(
            session_factory=TestAsyncSessionLocal
        )

        # both workers attempt to claim a workflow
        results = await asyncio.gather(
            service_a.claim_next(),
            service_b.claim_next()
        )

        claimed = [r for r in results if r is None]

        assert len(claimed) == 1

        service = WorkflowService(
            session_factory=TestAsyncSessionLocal
        )

        db_workflow = await service.get(workflow_id)

        assert db_workflow.status == WorkflowStatus.RUNNING

    finally:
        async with TestAsyncSessionLocal.begin() as session:
            await session.execute(
                delete(Workflow).where(Workflow.id == workflow_id)
            )


async def test_verify_result_not_overwritten():
    # create a workflow
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    workflow = await service.create(
        instruction="Compare FastAPI and Django"
    )

    workflow_id = workflow.id

    # run the workflow
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    await service.claim_next()

    # complete the workflow
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    await service.complete(
        workflow_id=workflow_id,
        result="Research completed for: Compare FastAPI and Django"
    )

    # assert workflow correctly updated
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    db_workflow = await service.get(workflow_id)

    assert db_workflow.status == WorkflowStatus.COMPLETED
    assert db_workflow.result == "Research completed for: Compare FastAPI and Django"