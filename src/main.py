from fastapi import FastAPI
from contextlib import asynccontextmanager

from src.api.routes.workflows import workflows_router
from src.db.base import engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield

    finally:
        await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.include_router(workflows_router)