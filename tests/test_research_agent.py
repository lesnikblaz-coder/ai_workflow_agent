import pytest
import json

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.workflow_service import WorkflowService
from src.worker.main import process_one_workflow
from src.enums import WorkflowStatus
from src.exceptions.custom import WorkflowFailedError
from src.schemas.research import ResearchPlan


async def test_agent_produces_valid_plan(
        mock_gemini_client,
        mock_research_agent
):
    interaction = SimpleNamespace(
        output_text=json.dumps({
            "topic": "FastAPI vs Django",
            "research_questions": [
                "How do both frameworks support asynchronous operations?"
            ],
            "search_queries": [
                "FastAPI official documentation async",
                "Django official documentation async"
            ]
        })
    )

    mock_gemini_client.interactions.create.return_value = interaction

    result = await mock_research_agent.run("Compare FastAPI and Django")

    plan = ResearchPlan.model_validate_json(result)

    assert plan.topic == "FastAPI vs Django"
    assert len(plan.research_questions) == 1
    assert len(plan.search_queries) == 2

    mock_gemini_client.interactions.create.assert_called_once()

    call_kwargs = mock_gemini_client.interactions.create.call_args.kwargs

    assert call_kwargs["input"] == "Compare FastAPI and Django"

async def test_worker_executes_agent(
        mock_research_agent,
        test_session_factory
):
    # create a workflow
    service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await service.create(instruction="Compare FastAPI and Django")
    workflow_id = workflow.id

    mock_research_agent.run = AsyncMock(return_value='{"topic":"FastAPI vs Django", ...}')

    result = await process_one_workflow(
        service=service,
        agent=mock_research_agent
    )

    assert result == True

    db_result = await service.get(workflow_id)

    assert db_result.status == WorkflowStatus.COMPLETED
    assert db_result.result == '{"topic":"FastAPI vs Django", ...}'


async def test_worker_executes_agent_exception(
        mock_research_agent,
        mock_gemini_client,
        test_session_factory
):
    # create a workflow
    service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await service.create(instruction="Compare FastAPI and Django")
    workflow_id = workflow.id

    mock_gemini_client.interactions.create.return_value = SimpleNamespace(output_text="")

    with pytest.raises(WorkflowFailedError):
        await process_one_workflow(
            service=service,
            agent=mock_research_agent
        )

    db_result = await service.get(workflow_id)

    assert db_result.status == WorkflowStatus.FAILED
