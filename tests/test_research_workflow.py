from pydantic import HttpUrl
from unittest.mock import AsyncMock

from src.schemas.search import SearchResult
from src.schemas.research import ResearchPlan, ResearchReport, ResearchFinding, ResearchReportWithSources
from src.services.research_service import ResearchService
from src.services.workflow_service import WorkflowService
from src.agents.research_agent import ResearchAgent
from src.worker.main import process_one_workflow
from src.enums import WorkflowStatus
from src.repositories.workflow_repository import WorkflowRepository


async def test_complete_successful_workflow(
        client,
        test_session_factory,
        mock_web_search_tool
):
    # Setup needed services and mocked return values instead of real external API calls
    mock_research_agent = AsyncMock(spec=ResearchAgent)

    mock_workflow_service = WorkflowService(
        session_factory=test_session_factory
    )
    mock_research_service = ResearchService(
        agent=mock_research_agent,
        search_tool=mock_web_search_tool
    )

    mock_research_agent.run.return_value = ResearchPlan(
        topic="FastAPI vs Django",
        research_questions=[
            "How do these frameworks support asynchronous operations?"
        ],
        search_queries=[
            "FastAPI async documentation",
            "Django async documentation"
        ]
    )

    mock_web_search_tool.search.side_effect = [
        [
            SearchResult(
                title="FastAPI Documentation",
                url=HttpUrl("https://fastapi.tiangolo.com/"),
                snippet="FastAPI supports asynchronous route handlers."
            )
        ],
        [
            SearchResult(
                title="Django Documentation",
                url=HttpUrl("https://www.djangoproject.com/"),
                snippet="Django supports asynchronous route handlers."
            )
        ],
    ]

    mock_research_agent.synthesize.return_value = ResearchReport(
        title="FastAPI and Django async",
        summary="Both frameworks support asynchronous operations.",
        findings=[
            ResearchFinding(
                claim="FastAPI supports asynchronous operations.",
                source_ids=["S1"]
            ),
            ResearchFinding(
                claim="Django supports asynchronous operations.",
                source_ids=["S2"]
            )
        ],
        limitations=[]
    )

    # Workflow execution
    base_workflow_router_url = "/v1/workflows"

    response_post = await client.post(
        url=base_workflow_router_url,
        json={
            "instruction": "Compare FastAPI and Django frameworks. "
                           "Which supports asynchronous operations?"
        }
    )

    assert response_post.status_code == 202

    workflow_id = response_post.json()["id"]

    await process_one_workflow(
        workflow_service=mock_workflow_service,
        research_service=mock_research_service
    )

    response_get = await client.get(
        url=base_workflow_router_url + f"/{workflow_id}",
    )

    assert response_get.status_code == 200

    result = response_get.json()

    assert result["status"] == WorkflowStatus.COMPLETED

    ResearchReportWithSources.model_validate_json(result["result"])

    mock_research_agent.run.assert_awaited_once_with(
        "Compare FastAPI and Django frameworks. "
        "Which supports asynchronous operations?"
    )


async def test_incomplete_failed_workflow(
        client,
        test_session_factory,
        mock_web_search_tool
):
    # Setup needed services and mocked return values instead of real external API calls
    mock_research_agent = AsyncMock(spec=ResearchAgent)

    mock_workflow_service = WorkflowService(
        session_factory=test_session_factory
    )
    mock_research_service = ResearchService(
        agent=mock_research_agent,
        search_tool=mock_web_search_tool
    )

    mock_research_agent.run.return_value = ResearchPlan(
        topic="FastAPI vs Django",
        research_questions=[
            "How do these frameworks support asynchronous operations?"
        ],
        search_queries=[
            "FastAPI async documentation",
            "Django async documentation"
        ]
    )

    mock_web_search_tool.search.side_effect = [
        [
            SearchResult(
                title="FastAPI Documentation",
                url=HttpUrl("https://fastapi.tiangolo.com/"),
                snippet="FastAPI supports asynchronous route handlers."
            )
        ],
        [
            SearchResult(
                title="Django Documentation",
                url=HttpUrl("https://www.djangoproject.com/"),
                snippet="Django supports asynchronous route handlers."
            )
        ],
    ]

    mock_research_agent.synthesize.return_value = ResearchReport(
        title="FastAPI and Django async",
        summary="Both frameworks support asynchronous operations.",
        findings=[
            ResearchFinding(
                claim="FastAPI supports asynchronous operations.",
                source_ids=["S1"]
            ),
            ResearchFinding(
                claim="Django supports asynchronous operations.",
                source_ids=["S999"]
            )
        ],
        limitations=[]
    )

    # Workflow execution
    base_workflow_router_url = "/v1/workflows"

    response_post = await client.post(
        url=base_workflow_router_url,
        json={
            "instruction": "Compare FastAPI and Django frameworks. "
                           "Which supports asynchronous operations?"
        }
    )

    assert response_post.status_code == 202

    workflow_id = response_post.json()["id"]

    # Should produce a FAILED WORKFLOW due to invalid LLM citation above (S999)
    await process_one_workflow(
        workflow_service=mock_workflow_service,
        research_service=mock_research_service
    )

    response_get = await client.get(
        url=base_workflow_router_url + f"/{workflow_id}",
    )

    assert response_get.status_code == 200

    result = response_get.json()

    assert result["status"] == WorkflowStatus.FAILED
    assert result["result"] is None

    # Assert workflow has non-empty error message
    async with test_session_factory.begin() as session:
        repo = WorkflowRepository(session=session)
        claimed_workflow = await repo.get(workflow_id)
        assert claimed_workflow
        assert claimed_workflow.error_message is not None