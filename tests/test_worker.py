import asyncio

from sqlalchemy import delete
from types import SimpleNamespace

from src.enums import WorkflowStatus
from src.services.workflow_service import WorkflowService
from src.services.research_service import ResearchService
from tests.conftest import TestAsyncSessionLocal
from src.db.models.workflow import Workflow
from src.worker.main import process_one_workflow


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
