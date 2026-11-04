from fastapi import FastAPI

from src.api.routes.workflows import workflows_router


app = FastAPI()

app.include_router(workflows_router)