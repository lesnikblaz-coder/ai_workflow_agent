import asyncio
import pytest

from datetime import timedelta, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import delete, update
from unittest.mock import AsyncMock, Mock

from src.db.models.workflow import Workflow
from src.enums import WorkflowStatus
from src.exceptions.custom import WorkflowOwnershipLostError, LeaseRenewalRejectedError
from src.repositories.workflow_repository import WorkflowRepository
from src.schemas.research import ResearchReportWithSources
from src.schemas.workflow import ClaimedWorkflow
from src.services.research_service import ResearchService
from src.services.workflow_service import WorkflowService
from src.worker.main import process_one_workflow
from tests.conftest import TestAsyncSessionLocal


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
        error_msg="failed",
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
        error_msg="failed",
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

    with pytest.raises(WorkflowOwnershipLostError):
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

    with pytest.raises(WorkflowOwnershipLostError):
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

    with pytest.raises(WorkflowOwnershipLostError):
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


async def test_correct_token_failure_succeeds(
        test_session_factory
) -> None:
    """Verify workflow failure succeeds with valid claim token."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    await workflow_service.fail(
        workflow_id=workflow.id,
        error_msg="workflow failed",
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
        assert db_workflow.status == WorkflowStatus.FAILED
        assert db_workflow.error_message is not None


async def test_incorrect_token_failure_rejected_db_unchanged(
        test_session_factory
) -> None:
    """Verify workflow failure is rejected with invalid claim token."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    with pytest.raises(WorkflowOwnershipLostError):
        await workflow_service.fail(
            workflow_id=workflow.id,
            error_msg="workflow failed",
            claim_token=uuid4()  # Incorrect claim token
        )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(
            workflow.id
        )

        assert db_workflow is not None
        assert db_workflow.claim_token is not None
        assert db_workflow.id == claimed_workflow.id == workflow.id
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.error_message is None


async def test_stale_token_cannot_fail_workflow_owned_by_another_worker(
        test_session_factory
) -> None:
    """Ensure stale/old claim token cannot fail a workflow owned by another worker."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    # Simulate ownership changing
    stale_claim_token = claimed_workflow.claim_token
    fresh_claim_token = uuid4()

    async with test_session_factory.begin() as session:
        stmt = (
            update(Workflow)
            .where(Workflow.id == workflow.id)
            .values(claim_token=fresh_claim_token)
        )

        await session.execute(stmt)

    with pytest.raises(WorkflowOwnershipLostError):
        await workflow_service.fail(
            workflow_id=workflow.id,
            error_msg="workflow failed",
            claim_token=stale_claim_token
        )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(
            session=session
        )

        db_workflow = await repo.get(workflow.id)

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.claim_token == fresh_claim_token
        assert db_workflow.error_message is None


async def test_valid_token_active_lease_successful_extension(
        test_session_factory
) -> None:
    """Valid claim token with an active lease successfully extends lease expiry."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        db_workflow = await repo.get(workflow.id)

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.lease_expires_at is not None

    await workflow_service.renew_lease(
        workflow_id=workflow.id,
        claim_token=claimed_workflow.claim_token
    )

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        renewed_lease_db_workflow = await repo.get(workflow.id)

        assert renewed_lease_db_workflow
        assert renewed_lease_db_workflow.status == WorkflowStatus.RUNNING
        assert renewed_lease_db_workflow.lease_expires_at is not None

        assert renewed_lease_db_workflow.lease_expires_at > db_workflow.lease_expires_at


async def test_incorrect_token_rejects_lease_extension(
        test_session_factory
) -> None:
    """Invalid claim token with an active lease rejects lease expiry extension."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        db_workflow = await repo.get(workflow.id)

        assert db_workflow
        assert db_workflow.status == WorkflowStatus.RUNNING
        assert db_workflow.lease_expires_at is not None

    with pytest.raises(LeaseRenewalRejectedError):
        await workflow_service.renew_lease(
            workflow_id=workflow.id,
            claim_token=uuid4()  # Invalid claim token
        )

    # DB workflow remains unchanged
    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        rejected_db_workflow = await repo.get(workflow.id)

        assert rejected_db_workflow
        assert rejected_db_workflow.status == WorkflowStatus.RUNNING
        assert rejected_db_workflow.lease_expires_at is not None

        assert rejected_db_workflow.lease_expires_at == db_workflow.lease_expires_at


async def test_completed_workflow_rejects_lease_extension(
        test_session_factory
) -> None:
    """Workflow that is already completed rejects the lease extension execution."""
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

    with pytest.raises(LeaseRenewalRejectedError):
        await workflow_service.renew_lease(
            workflow_id=workflow.id,
            claim_token=claimed_workflow.claim_token
        )

    # DB workflow remains unchanged
    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        rejected_db_workflow = await repo.get(workflow.id)

        assert rejected_db_workflow
        assert rejected_db_workflow.status == WorkflowStatus.COMPLETED
        assert rejected_db_workflow.lease_expires_at is None


async def test_expired_lease_rejects_lease_extension(
        test_session_factory
) -> None:
    """An already expired lease rejects lease extension request."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    claimed_workflow = await workflow_service.claim_next()

    assert claimed_workflow is not None
    assert claimed_workflow.id == workflow.id
    assert claimed_workflow.claim_token is not None

    # Manually expire the current lease
    async with test_session_factory.begin() as session:
        _started_at_before_expired_datetime_obj = datetime.now(timezone.utc) - timedelta(minutes=5)
        _expired_datetime_obj = datetime.now(timezone.utc) - timedelta(minutes=3)

        stmt = (
            update(Workflow)
            .where(
                Workflow.id == workflow.id,
                Workflow.claim_token == claimed_workflow.claim_token,
                Workflow.status == WorkflowStatus.RUNNING
            )
            .values(
                started_at=_started_at_before_expired_datetime_obj,
                lease_expires_at=_expired_datetime_obj
            )
        )

        await session.execute(stmt)

    with pytest.raises(LeaseRenewalRejectedError):
        await workflow_service.renew_lease(
            workflow_id=workflow.id,
            claim_token=claimed_workflow.claim_token
        )

    # DB workflow remains unchanged
    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session)

        rejected_db_workflow = await repo.get(workflow.id)

        assert rejected_db_workflow
        assert rejected_db_workflow.status == WorkflowStatus.RUNNING
        assert rejected_db_workflow.lease_expires_at == _expired_datetime_obj


async def test_research_succeeds_heartbeat_stops(
        monkeypatch
) -> None:
    workflow_service = AsyncMock(spec=WorkflowService)
    research_service = AsyncMock(spec=ResearchService)

    workflow = ClaimedWorkflow(
        id=uuid4(),
        instruction="test",
        claim_token=uuid4()
    )

    workflow_service.claim_next.return_value = workflow

    report = Mock(spec=ResearchReportWithSources)
    report.model_dump_json.return_value = '{}'

    heartbeat_started = asyncio.Event()
    heartbeat_stopped = asyncio.Event()

    async def mock_heartbeat(*args, **kwargs):
        heartbeat_started.set()

        try:
            # Event that nobody ever signals
            # Suspends indefinitely until something cancels it
            await asyncio.Event().wait()
        finally:
            heartbeat_stopped.set()

    monkeypatch.setattr(
        "src.worker.main.heartbeat_loop",
        mock_heartbeat
    )

    # Waits until the heartbeat signals that it's
    # running before returning the mocked report
    async def mock_research(instruction):
        await heartbeat_started.wait()
        return report

    research_service.research.side_effect = mock_research

    async def mock_complete(**kwargs):
        assert heartbeat_stopped.is_set()

    workflow_service.complete.side_effect = mock_complete

    # Execute the actual worker
    processed = await asyncio.wait_for(
        process_one_workflow(
            workflow_service=workflow_service,
            research_service=research_service
        ),
        timeout=2
    )

    assert processed is True
    assert heartbeat_started.is_set()
    assert heartbeat_stopped.is_set()

    research_service.research.assert_awaited_once_with(
        workflow.instruction
    )

    workflow_service.complete.assert_awaited_once_with(
        workflow_id=workflow.id,
        result='{}',
        claim_token=workflow.claim_token
    )

    workflow_service.fail.assert_not_awaited()


async def test_failed_research_stops_heartbeat(
        monkeypatch
) -> None:
    workflow_service = AsyncMock(spec=WorkflowService)
    research_service = AsyncMock(spec=ResearchService)

    workflow = ClaimedWorkflow(
        id=uuid4(),
        instruction="test",
        claim_token=uuid4()
    )

    workflow_service.claim_next.return_value = workflow

    heartbeat_started = asyncio.Event()
    heartbeat_stopped = asyncio.Event()

    async def mock_heartbeat(*args, **kwargs):
        heartbeat_started.set()

        try:
            # Event that nobody ever signals
            # Suspends indefinitely until something cancels it
            await asyncio.Event().wait()
        finally:
            heartbeat_stopped.set()

    monkeypatch.setattr(
        "src.worker.main.heartbeat_loop",
        mock_heartbeat
    )

    async def mock_research(instruction):
        # Assert heartbeat starts before the research
        await heartbeat_started.wait()
        raise RuntimeError("Simulated research failure")

    research_service.research.side_effect = mock_research

    async def mock_fail(**kwargs):
        assert heartbeat_stopped.is_set()

    workflow_service.fail.side_effect = mock_fail

    processed = await asyncio.wait_for(
        process_one_workflow(
            workflow_service,
            research_service
        ),
        timeout=2
    )

    assert processed is True
    assert heartbeat_started.is_set()
    assert heartbeat_stopped.is_set()

    research_service.research.assert_awaited_once_with(
        workflow.instruction
    )

    workflow_service.fail.assert_awaited_once_with(
        workflow_id=workflow.id,
        error_msg=f"Workflow {workflow.id} failed.",
        claim_token=workflow.claim_token
    )

    workflow_service.complete.assert_not_awaited()