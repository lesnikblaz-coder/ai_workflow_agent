import pytest
import asyncio

from uuid import uuid4
from unittest.mock import AsyncMock

from src.worker.heartbeat import heartbeat_loop
from src.services.workflow_service import WorkflowService
from src.exceptions.custom import LeaseRenewalRejectedError


async def test_heartbeat_renews_multiple_times() -> None:
    """Tests successful heartbeat lease renewal multiple times."""
    mock_workflow_service = AsyncMock(spec=WorkflowService)

    workflow_id = uuid4()
    claim_token = uuid4()

    three_renewals = asyncio.Event()

    renewal_count = 0

    async def mock_renew_lease(**kwargs):
        nonlocal renewal_count

        renewal_count += 1

        if renewal_count >= 3:
            three_renewals.set()

    mock_workflow_service.renew_lease.side_effect = mock_renew_lease

    task = asyncio.create_task(
        heartbeat_loop(
            service=mock_workflow_service,
            workflow_id=workflow_id,
            claim_token=claim_token,
            heartbeat_interval=0.001
        )
    )

    try:
        await asyncio.wait_for(
            three_renewals.wait(),
            timeout=2
        )

        assert mock_workflow_service.renew_lease.await_count >= 3

        mock_workflow_service.renew_lease.assert_awaited_with(
            workflow_id=workflow_id,
            claim_token=claim_token
        )

    finally:
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


async def test_heartbeat_cancellation() -> None:
    """Heartbeat task correctly cancels while sleeping and doesn't execute additional renewals afterward."""
    mock_workflow_service = AsyncMock(spec=WorkflowService)

    workflow_id = uuid4()
    claim_token = uuid4()

    task = asyncio.create_task(
        heartbeat_loop(
            service=mock_workflow_service,
            workflow_id=workflow_id,
            claim_token=claim_token,
            heartbeat_interval=10
        )
    )

    # Give the event loop an opportunity to run the heartbeat task so it reaches its sleep
    await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    mock_workflow_service.renew_lease.assert_not_awaited()


async def test_heartbeat_loop_stops_when_renewal_rejected(
        test_session_factory
) -> None:
    """Heartbeat loop stops when the lease renewal is rejected (invalid claim_token)."""
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create("test")

    assert workflow is not None

    task = asyncio.create_task(
        heartbeat_loop(
            service=workflow_service,
            workflow_id=workflow.id,
            claim_token=uuid4(),
            heartbeat_interval=0.001
        )
    )

    with pytest.raises(LeaseRenewalRejectedError):
        await asyncio.wait_for(
            task,
            timeout=0.5
        )