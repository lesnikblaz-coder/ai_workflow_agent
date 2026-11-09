from src.exceptions.base import AppException


class WorkflowFailedError(AppException):
    status_code = 500
    detail = "An unexpected exception occurred during workflow execution."


class LLMEmptyOutputError(AppException):
    status_code = 502
    detail = "LLM provider returned an empty output."