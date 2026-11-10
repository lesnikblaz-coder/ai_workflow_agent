import httpx
import pytest

from pydantic import HttpUrl, ValidationError

from src.tools.web_search import WebSearch
from src.schemas.search import SearchResult


def mock_search_response(request: httpx.Request):
    assert request.method == "POST"
    assert request.url.path == "/search"

    return httpx.Response(
        status_code=200,
        json={
            "results": [
                {
                    "title": "FastAPI Documentation",
                    "url": "https://fastapi.tiangolo.com/",
                    "content": "FastAPI supports asynchronous endpoints.",
                }
            ]
        }
    )


async def test_web_search_success():
    transport = httpx.MockTransport(mock_search_response)

    async with httpx.AsyncClient(transport=transport) as client:
        tool = WebSearch(
            client=client,
            api_key="fake-test-key"
        )

        results = await tool.search("FastAPI async")

        assert all(isinstance(result, SearchResult) for result in results)
        assert results[0].url == HttpUrl("https://fastapi.tiangolo.com/")
        assert results[0].title == "FastAPI Documentation"
        assert results[0].snippet == "FastAPI supports asynchronous endpoints."


def mock_empty_search_response(request: httpx.Request):
    assert request.method == "POST"
    assert request.url.path == "/search"

    return httpx.Response(
        status_code=200,
        json={
            "results": []
        }
    )


async def test_web_search_empty_results():
    transport = httpx.MockTransport(mock_empty_search_response)

    async with httpx.AsyncClient(transport=transport) as client:
        tool = WebSearch(
            client=client,
            api_key="fake-test-key"
        )

        results = await tool.search("FastAPI async")

        assert results == []


def mock_unsuccessful_search_response(request: httpx.Request):
    assert request.method == "POST"
    assert request.url.path == "/search"

    return httpx.Response(
        status_code=401,
        json={
            "results": []
        }
    )


async def test_unsuccessful_web_search_raises():
    transport = httpx.MockTransport(mock_unsuccessful_search_response)

    async with httpx.AsyncClient(transport=transport) as client:
        tool = WebSearch(
            client=client,
            api_key="fake-test-key"
        )

        with pytest.raises(httpx.HTTPStatusError):
            await tool.search("FastAPI async")


def mock_invalid_provider_data(request: httpx.Request):
    assert request.method == "POST"
    assert request.url.path == "/search"

    # invalid DATA
    return httpx.Response(
        status_code=200,
        json={
            "results": [
                {
                    "title": "FastAPI Documentation",
                    "url": "random-invalid-url",
                    "content": "FastAPI supports asynchronous endpoints.",
                }
            ]
        }
    )


async def test_invalid_provider_data_missing_url():
    transport = httpx.MockTransport(mock_invalid_provider_data)

    async with httpx.AsyncClient(transport=transport) as client:
        tool = WebSearch(
            client=client,
            api_key="fake-test-key"
        )

        with pytest.raises(ValidationError):
            await tool.search("FastAPI async")


def mock_missing_provider_data(request: httpx.Request):
    assert request.method == "POST"
    assert request.url.path == "/search"

    # missing DATA
    return httpx.Response(
        status_code=200,
        json={
            "results": [
                {
                    "title": "FastAPI Documentation",
                    "content": "FastAPI supports asynchronous endpoints.",
                }
            ]
        }
    )


async def test_missing_provider_data():
    transport = httpx.MockTransport(mock_missing_provider_data)

    async with httpx.AsyncClient(transport=transport) as client:
        tool = WebSearch(
            client=client,
            api_key="fake-test-key"
        )

        with pytest.raises(KeyError):
            await tool.search("FastAPI async")