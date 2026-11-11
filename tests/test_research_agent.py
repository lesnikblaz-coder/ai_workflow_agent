import pytest
import json

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.workflow_service import WorkflowService
from src.services.research_service import ResearchService
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

    plan = await mock_research_agent.run("Compare FastAPI and Django")

    assert plan.topic == "FastAPI vs Django"
    assert len(plan.research_questions) == 1
    assert len(plan.search_queries) == 2

    mock_gemini_client.interactions.create.assert_called_once()

    call_kwargs = mock_gemini_client.interactions.create.call_args.kwargs

    assert call_kwargs["input"] == "Compare FastAPI and Django"


async def test_worker_executes_agent(
        mock_research_agent,
        mock_web_search_tool,
        test_session_factory
):
    # create a workflow
    workflow_service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow = await workflow_service.create(instruction="Compare FastAPI and Django")
    workflow_id = workflow.id

    mock_research_agent.run = AsyncMock(
        return_value=ResearchPlan(
            topic="FastAPI vs Django",
            research_questions=[
                "How do both frameworks support asynchronous operations?"
            ],
            search_queries=[
                "FastAPI official documentation async",
                "Django official documentation async"
            ]
        )
    )

    research_service = ResearchService(
        agent=mock_research_agent,
        search_tool=mock_web_search_tool
    )

    result = await process_one_workflow(
        workflow_service=workflow_service,
        research_service=research_service
    )

    assert result == True

    db_result = await workflow_service.get(workflow_id)

    assert db_result.status == WorkflowStatus.COMPLETED
    assert db_result.result is not None


async def test_worker_executes_agent_exception(
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

    with pytest.raises(WorkflowFailedError):
        await process_one_workflow(
            workflow_service=workflow_service,
            research_service=research_service
        )

    db_result = await workflow_service.get(workflow_id)

    assert db_result.status == WorkflowStatus.FAILED
