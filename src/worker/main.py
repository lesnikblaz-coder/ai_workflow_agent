import asyncio
import httpx

from google import genai

from src.logging_config import logger
from src.db.base import AsyncSessionLocal, engine
from src.services.workflow_service import WorkflowService
from src.services.research_service import ResearchService
from src.agents.research_agent import ResearchAgent
from src.config import settings
from src.tools.web_search import WebSearchTool


async def process_one_workflow(
        workflow_service: WorkflowService,
        research_service: ResearchService
) -> bool:
    workflow = await workflow_service.claim_next()

    if workflow is None:
        return False

    logger.info("Workflow %s picked up", workflow.id)

    try:
        report = await research_service.research(workflow.instruction)

        await workflow_service.complete(
            workflow_id=workflow.id,
            result=report.model_dump_json()
        )

        logger.info("Completed workflow %s", workflow.id)

    except Exception:
        logger.exception("Workflow %s failed", workflow.id)

        error_msg = f"Workflow {workflow.id} failed."

        await workflow_service.fail(workflow.id, error_msg)

        return True

    return True


async def main():
    workflow_service = WorkflowService(session_factory=AsyncSessionLocal)

    aclient = genai.Client(
        api_key=settings.GEMINI_API_KEY
    ).aio

    try:
        agent = ResearchAgent(aclient)

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            search_tool = WebSearchTool(
                client=http_client,
                api_key=settings.TAVILY_API_KEY
            )

            research_service = ResearchService(
                agent=agent,
                search_tool=search_tool
            )

            while True:
                logger.info("Checking database for work...")

                processed = await process_one_workflow(
                    workflow_service=workflow_service,
                    research_service=research_service
                )

                if not processed:
                    await asyncio.sleep(2)

    finally:
        logger.info("Cleaning up resources...")

        await engine.dispose()
        await aclient.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Worker stopped.")