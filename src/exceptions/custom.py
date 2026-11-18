from uuid import UUID

from src.exceptions.base import AppException


class WorkflowFailedError(AppException):
    status_code = 500
    detail = "An unexpected exception occurred during workflow execution."


class LLMEmptyOutputError(AppException):
    status_code = 502
    detail = "LLM provider returned an empty output."


class CitationValidationError(AppException):
    status_code = 502
    detail = "LLM response failed citation validation."


class WorkflowOwnershipLostError(AppException):
    status_code = 409

    def __init__(self, workflow_id: UUID):
        detail = (
            f"Workflow {workflow_id} completion rejected: "
            "state or claim ownership mismatch."
        )

        super().__init__(detail)


class LeaseRenewalRejectedError(AppException):
    def __init__(self, workflow_id: UUID):
        detail = (
            f"Workflow {workflow_id} lease renewal rejected: "
            "mismatch in either state, claim ownership or the lease is already expired."
        )

        super().__init__(detail)