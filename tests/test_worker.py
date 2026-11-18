import asyncio
import pytest

from uuid import uuid4
from sqlalchemy import delete
from types import SimpleNamespace
from datetime import timedelta

from src.enums import WorkflowStatus
from src.services.workflow_service import WorkflowService
from src.services.research_service import ResearchService
from tests.conftest import TestAsyncSessionLocal
from src.db.models.workflow import Workflow
from src.worker.main import process_one_workflow
from src.repositories.workflow_repository import WorkflowRepository


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

        claimed = [r for r in results if r is not None]

        assert len(claimed) == 1
        assert claimed[0].id == workflow_id

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

    claimed_workflow = await service.claim_next()

    assert claimed_workflow

    # complete the workflow
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    await service.complete(
        workflow_id=workflow_id,
        result="Research completed for: Compare FastAPI and Django",
        claim_token=claimed_workflow.claim_token
    )

    # assert workflow correctly updated
    service = WorkflowService(
        session_factory=TestAsyncSessionLocal
    )

    db_workflow = await service.get(workflow_id)

    assert db_workflow.status == WorkflowStatus.COMPLETED
    assert db_workflow.result == "Research completed for: Compare FastAPI and Django"


async def test_worker_exception_sets_workflow_status_to_failed(
        mock_research_agent,
        mock_gemini_client,
        mock_web_search_tool,
        test_session_factory
):
    # create a workflow
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(instruction="Compare FastAPI and Django")
    workflow_id = workflow.id

    mock_gemini_client.interactions.create.return_value = SimpleNamespace(output_text="")

    research_service = ResearchService(
        agent=mock_research_agent,
        search_tool=mock_web_search_tool
    )

    await process_one_workflow(
        workflow_service=workflow_service,
        research_service=research_service
    )

    db_result = await workflow_service.get(workflow_id)

    assert db_result.status == WorkflowStatus.FAILED


async def test_running_workflow_is_not_reclaimed(
        test_session_factory
):
    """
    Running worker crashes -> current workflow status running is not reclaimed.
    """

    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    # Create a workflow
    workflow = await workflow_service.create(
        instruction="Test instruction"
    )

    # Check saved workflow
    db_workflow = await workflow_service.get(
        workflow_id=workflow.id
    )

    assert db_workflow
    assert db_workflow.status == WorkflowStatus.QUEUED
    assert db_workflow.result is None

    # First claim_next() correctly claims the queued workflow
    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow
    assert claimed_workflow.id == workflow.id

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        # Assert same workflow is now updated: status=RUNNING, started_at is populated
        claimed_db_workflow = await repo.get(
            workflow_id=claimed_workflow.id
        )

        assert claimed_db_workflow
        assert claimed_db_workflow.status == WorkflowStatus.RUNNING
        assert claimed_db_workflow.result is None
        assert claimed_db_workflow.started_at is not None

    # A subsequent claim_next() does not reclaim that workflow
    # The workflow remains RUNNING
    subsequent_claimed_workflow = await workflow_service.claim_next()

    assert subsequent_claimed_workflow is None

    workflow = await workflow_service.get(workflow.id)

    assert workflow.status == WorkflowStatus.RUNNING


async def test_newly_created_workflow_has_no_lease_expiration(
        test_session_factory
):
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "Test"
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(workflow.id)

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.QUEUED
        assert db_workflow.lease_expires_at is None


async def test_claiming_workflow_populates_lease(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_claimed_workflow = await repo.get(claimed_workflow.id)

        assert db_claimed_workflow is not None
        assert db_claimed_workflow.id == workflow.id
        assert db_claimed_workflow.status == WorkflowStatus.RUNNING
        assert db_claimed_workflow.started_at is not None
        assert db_claimed_workflow.lease_expires_at is not None

        actual_duration = (
                db_claimed_workflow.lease_expires_at
                - db_claimed_workflow.started_at
        )

        expected_duration = timedelta(minutes=2)

        tolerance = timedelta(seconds=5)

        assert abs(actual_duration - expected_duration) <= tolerance


async def test_completed_workflow_clears_active_lease(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id

    await workflow_service.complete(
        workflow_id=workflow.id,
        result="completed",
        claim_token=claimed_workflow.claim_token
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.COMPLETED
        assert db_workflow.lease_expires_at is None


async def test_failed_workflow_clears_active_lease(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id

    await workflow_service.fail(
        workflow_id=workflow.id,
        error_msg="failed"
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.FAILED
        assert db_workflow.lease_expires_at is None


async def test_newly_created_workflow_has_no_claim_token(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.QUEUED
        assert db_workflow.claim_token is None


async def test_claiming_workflow_populates_claim_token(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    # Assert it also exists in the database
    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(workflow.id)

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.claim_token is not None
        assert db_workflow.claim_token == claimed_workflow.claim_token


async def test_completed_workflow_clears_claim_token(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    await workflow_service.complete(
        workflow_id=workflow.id,
        result="completed",
        claim_token=claimed_workflow.claim_token
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.COMPLETED
        assert db_workflow.claim_token is None


async def test_failed_workflow_clears_claim_token(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(
        "test"
    )

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    await workflow_service.fail(
        workflow_id=workflow.id,
        error_msg="failed"
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.FAILED
        assert db_workflow.claim_token is None


async def test_correct_claim_token_completes_workflow(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    await workflow_service.complete(
        workflow_id=workflow.id,
        result="completed",
        claim_token=claimed_workflow.claim_token
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow is not None
        assert db_workflow.claim_token is None
        assert db_workflow.id == claimed_workflow.id == workflow.id
        assert db_workflow.status == WorkflowStatus.COMPLETED


async def test_incorrect_claim_token_rejects_workflow_completion(
        test_session_factory,
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    with pytest.raises(RuntimeError):
        await workflow_service.complete(
            workflow_id=workflow.id,
            result="completed",
            claim_token=uuid4()  # incorrect claim token
        )


async def test_correct_claim_token_rejects_completed_workflow_completion(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    await workflow_service.complete(
        workflow_id=workflow.id,
        result="complete",
        claim_token=claimed_workflow.claim_token
    )

    with pytest.raises(RuntimeError):
        await workflow_service.complete(
            workflow_id=workflow.id,
            result="completed",
            claim_token=claimed_workflow.claim_token
        )


async def test_rejected_completion_keeps_existing_data_unchanged(
        test_session_factory
) -> None:
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    with pytest.raises(RuntimeError):
        await workflow_service.complete(
            workflow_id=workflow.id,
            result="completed",
            claim_token=uuid4()  # incorrect claim token
        )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow is not None
        assert db_workflow.id == workflow.id == claimed_workflow.id
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.result is None
        assert db_workflow.claim_token == claimed_workflow.claim_token
        assert db_workflow.started_at is not None
        assert db_workflow.lease_expires_at is not None
        assert db_workflow.error_message is None
        assert db_workflow.finished_at is None