import pytest

from pydantic import HttpUrl

from src.exceptions.custom import CitationValidationError
from src.schemas.search import SearchResult
from src.schemas.research import ResearchSource, ResearchReport, ResearchFinding
from src.services.citation_validation_service import validate_citations


@pytest.fixture
def provided_sources() -> list[ResearchSource]:
    return [
        ResearchSource(
            source_id="S1",
            search_query="test search query",
            result=SearchResult(
                title="Test source",
                url=HttpUrl("https://example.com"),
                snippet="Test snippet",
            ),
        )
    ]


def create_research_report(source_ids: list[str]) -> ResearchReport:
    return ResearchReport(
        title="Test title",
        summary="Test summary",
        findings=[
            ResearchFinding(
                claim="Test claim",
                source_ids=source_ids,
            )
        ],
        limitations=[],
    )


def test_llm_report_references_existing_source_id(
        provided_sources: list[ResearchSource]
) -> None:
    report = create_research_report(source_ids=["S1"])

    validate_citations(
        llm_report=report,
        provided_sources=provided_sources,
    )


def test_llm_report_references_invalid_source_id(
        provided_sources: list[ResearchSource]
) -> None:
    report = create_research_report(source_ids=["S999"])

    with pytest.raises(CitationValidationError):
        validate_citations(
            llm_report=report,
            provided_sources=provided_sources,
        )


def test_llm_report_references_valid_and_invalid_source_id(
        provided_sources: list[ResearchSource]
) -> None:
    report = create_research_report(source_ids=["S1", "S999"])

    with pytest.raises(CitationValidationError):
        validate_citations(
            llm_report=report,
            provided_sources=provided_sources,
        )


def test_llm_report_contains_finding_with_empty_source_ids_list(
        provided_sources: list[ResearchSource]
) -> None:
    report = create_research_report(source_ids=[])

    with pytest.raises(CitationValidationError):
        validate_citations(
            llm_report=report,
            provided_sources=provided_sources,
        )


def test_llm_report_contains_no_findings(
        provided_sources: list[ResearchSource]
) -> None:
    report = ResearchReport(
        title="Test title",
        summary="Test summary",
        findings=[],
        limitations=["Test limitations"],
    )

    validate_citations(
        llm_report=report,
        provided_sources=provided_sources
    )