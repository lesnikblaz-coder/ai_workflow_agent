from pydantic import HttpUrl

from src.schemas.search import SearchResult

KWARGS = {
    "title": "test title",
    "url": HttpUrl("https://test"),
    "snippet": "test snippet"
}

MOCKED_SEARCH_RESULTS = {
    "query_1": [
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
    ],
    "query_2": [
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
    ],
    "query_3": [
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
        SearchResult(**KWARGS),
    ]
}


async def test_source_id_assignment(
        mock_research_service
):
    """Test that checks source_id assignment correctness to each source of each query web tool search execution."""

    sources = mock_research_service._build_sources(MOCKED_SEARCH_RESULTS)

    assert [s.source_id for s in sources] == [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"
    ]

    assert [s.search_query for s in sources[:3]] == [
        "query_1", "query_1", "query_1"
    ]

    assert [s.search_query for s in sources[3:6]] == [
        "query_2", "query_2", "query_2"
    ]
    assert [s.search_query for s in sources[6:9]] == [
        "query_3", "query_3", "query_3"
    ]