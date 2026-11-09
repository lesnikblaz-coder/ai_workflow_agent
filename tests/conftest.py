import pytest_asyncio
import os
import httpx

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock
from google.genai.client import AsyncClient

from src.agents.research_agent import ResearchAgent
from src.db.base import Base
from src.main import app
from src.api import dependencies as deps
from src.services.workflow_service import WorkflowService
from src.schemas.workflow import WorkflowPostResponse

TEST_DATABASE_URL = (f"postgresql+asyncpg://"
                     f"{os.getenv('TEST_DB_USER')}:"
                     f"{os.getenv('TEST_DB_PASSWORD')}@"
                     f"{os.getenv('TEST_DB_HOST')}:"
                     f"{os.getenv('TEST_DB_PORT')}/"
                     f"{os.getenv('TEST_DB_NAME')}")  # test database

test_engine = create_async_engine(
    url=TEST_DATABASE_URL,
    poolclass=NullPool
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        # Safety check
        database_name = await conn.exec_driver_sql(
            "SELECT current_database()"
        )
        database_name = database_name.scalar_one()

        if database_name != os.getenv("TEST_DB_NAME"):
            raise RuntimeError(
                f"Wrong database! Connected to: {database_name}"
            )

        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_session_factory():
    async with test_engine.connect() as connection:
        transaction = await connection.begin()

        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint"
        )

        try:
            yield session_factory
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def client(test_session_factory):
    def override_workflow_service():
        return WorkflowService(
            session_factory=test_session_factory
        )

    app.dependency_overrides[deps._get_workflow_service] = override_workflow_service

    try:
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test"
        ) as client_:
            yield client_

    finally:
        app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def workflow_create(test_session_factory):
    service = WorkflowService(
        session_factory=test_session_factory
    )

    workflow_post_response: WorkflowPostResponse = await service.create(instruction="test instruction")
    return workflow_post_response

@pytest_asyncio.fixture
async def mock_gemini_client():
    client = MagicMock(spec=AsyncClient)
    client.interactions.create = AsyncMock()
    return client

@pytest_asyncio.fixture
async def mock_research_agent(mock_gemini_client):
    return ResearchAgent(
        client=mock_gemini_client
    )
