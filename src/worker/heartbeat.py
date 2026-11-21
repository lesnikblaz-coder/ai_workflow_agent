import asyncio

from uuid import UUID

from src.services.workflow_service import WorkflowService
from src.exceptions.custom import LeaseRenewalRejectedError
from src.logging_config import logger


async def heartbeat_loop(
        service: WorkflowService,
        workflow_id: UUID,
        claim_token: UUID,
        heartbeat_interval: float = 30
) -> None:

    while True:
        try:
            await asyncio.sleep(heartbeat_interval)

            await service.renew_lease(
                workflow_id=workflow_id,
                claim_token=claim_token
            )

        except LeaseRenewalRejectedError:
            logger.warning(
                "Workflow %s lease renewal rejected",
                workflow_id
            )
            raise

        except asyncio.CancelledError:
            logger.info(
                "Heartbeat task cancelled for workflow %s",
                workflow_id
            )
            raise

        except Exception:
            logger.exception(
                "Unexpected error renewing lease for workflow %s",
                workflow_id
            )
            raise