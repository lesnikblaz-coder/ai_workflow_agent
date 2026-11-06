import asyncio

from src.logging_config import logger
from src.db.base import AsyncSessionLocal, engine
from src.services.workflow_service import WorkflowService


async def process_one_workflow(service: WorkflowService) -> bool:
    workflow = await service.claim_next()

    if workflow is None:
        return False

    try:
        result = f"Research completed for: {workflow.instruction}"

        await service.complete(
            workflow_id=workflow.id,
            result=result
        )

        logger.info("Completed workflow %s", workflow.id)

    except Exception:
        logger.exception("Workflow %s failed", workflow.id)

        error_msg = f"Workflow {workflow.id} failed."

        await service.fail(workflow.id, error_msg)

    return True

async def main():
    service = WorkflowService(session_factory=AsyncSessionLocal)

    try:
        while True:
            logger.info("Checking database for work...")
            processed = await process_one_workflow(service)

            if not processed:
                await asyncio.sleep(2)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Worker stopped.")