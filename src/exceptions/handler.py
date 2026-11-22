from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.exceptions.base import AppException
from src.logging_config import logger


def register_exception_handlers(app: FastAPI):

    @app.exception_handler(AppException)
    async def app_exception_handler(
            request: Request,
            exc: AppException
    ):
        logger.exception(
            "Exception on %s %s: HTTP %s - %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail
            }
        )