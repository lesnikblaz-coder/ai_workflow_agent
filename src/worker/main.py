import asyncio

from google import genai

from src.logging_config import logger
from src.db.base import AsyncSessionLocal, engine
from src.services.workflow_service import WorkflowService
from src.agents.research_agent import ResearchAgent
from src.config import settings
from src.exceptions.custom import WorkflowFailedError


async def process_one_workflow(
        service: WorkflowService,
        agent: ResearchAgent
) -> bool:
    workflow = await service.claim_next()

    if workflow is None:
        return False

    try:
        plan = await agent.run(workflow.instruction)

        await service.complete(
            workflow_id=workflow.id,
            result=plan
        )

        logger.info("Completed workflow %s", workflow.id)

    except Exception:
        logger.exception("Workflow %s failed", workflow.id)

        error_msg = f"Workflow {workflow.id} failed."

        await service.fail(workflow.id, error_msg)

        raise WorkflowFailedError()

    return True


async def main():
    service = WorkflowService(session_factory=AsyncSessionLocal)

    aclient = genai.client.AsyncClient(
        api_client=settings.GEMINI_API_KEY
    )

    try:
        agent = ResearchAgent(aclient)

        while True:
            logger.info("Checking database for work...")

            processed = await process_one_workflow(
                service=service,
                agent=agent
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