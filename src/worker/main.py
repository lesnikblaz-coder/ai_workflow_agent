import asyncio
import httpx

from google import genai

from src.logging_config import logger
from src.db.base import AsyncSessionLocal, engine
from src.schemas.workflow import ClaimedWorkflow
from src.schemas.research import ResearchReportWithSources
from src.services.workflow_service import WorkflowService
from src.services.research_service import ResearchService
from src.agents.research_agent import ResearchAgent
from src.config import settings
from src.tools.web_search import WebSearchTool
from src.exceptions.custom import WorkflowOwnershipLostError, LeaseRenewalRejectedError
from src.worker.heartbeat import heartbeat_loop


async def run_research_with_heartbeat(
        workflow: ClaimedWorkflow,
        workflow_service: WorkflowService,
        research_service: ResearchService
) -> ResearchReportWithSources:
    """
    Execute a research task while continuously renewing the workflow's claim lease.

    The research task and heartbeat run concurrently. If the heartbeat terminates
    unexpectedly, the research task is canceled to prevent execution without
    valid workflow ownership.
    """
    research_task = asyncio.create_task(
        research_service.research(
            workflow.instruction
        )
    )

    heartbeat_task = asyncio.create_task(
        heartbeat_loop(
            service=workflow_service,
            workflow_id=workflow.id,
            claim_token=workflow.claim_token,
            heartbeat_interval=30
        )
    )

    try:
        done, _ = await asyncio.wait(
            {research_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        # A completed heartbeat task indicates that lease renewal is no longer active
        if heartbeat_task in done:
            await heartbeat_task

            # The heartbeat must remain active throughout the research task.
            # Unexpected termination invalidates the worker's execution guarantee.
            raise RuntimeError(
                "Heartbeat stopped unexpectedly"
            )

        return await research_task

    finally:
        for task in (research_task, heartbeat_task):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            research_task,
            heartbeat_task,
            return_exceptions=True
        )


async def process_one_workflow(
        workflow_service: WorkflowService,
        research_service: ResearchService
) -> bool:
    """
    Claim and process a single available workflow.

    Execute the
    research task, persist its result, and handle any execution failures
    or loss of workflow ownership.

    :param workflow_service: WorkflowService
    :param research_service: ResearchService
    :returns: bool: True if a workflow is claimed and processed, False if
    no workflow was available
    """
    workflow: ClaimedWorkflow | None = await workflow_service.claim_next()

    if workflow is None:
        return False

    logger.info("Workflow %s picked up", workflow.id)

    try:
        report = await run_research_with_heartbeat(
            workflow=workflow,
            workflow_service=workflow_service,
            research_service=research_service
        )

        await workflow_service.complete(
            workflow_id=workflow.id,
            result=report.model_dump_json(),
            claim_token=workflow.claim_token
        )

        logger.info("Completed workflow %s", workflow.id)

    except (WorkflowOwnershipLostError, LeaseRenewalRejectedError):
        logger.warning(
            "Workflow %s lost execution ownership",
            workflow.id,
        )

        return True

    except Exception:
        logger.exception("Workflow %s failed", workflow.id)

        error_msg = f"Workflow {workflow.id} failed."

        try:
            await workflow_service.fail(
                workflow_id=workflow.id,
                error_msg=error_msg,
                claim_token=workflow.claim_token
            )

        except WorkflowOwnershipLostError:
            logger.warning(
                "Workflow %s lost execution ownership",
                workflow.id,
            )

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
