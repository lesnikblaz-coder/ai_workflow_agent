from src.schemas.research import ResearchReport, ResearchSource
from src.exceptions.custom import CitationValidationError


def validate_citations(
        llm_report: ResearchReport,
        provided_sources: list[ResearchSource]
) -> None:
    """Validates/matches source id's mentioned in the LLM response versus the actual provided source's id's."""

    valid_source_ids = {
        source.source_id
        for source in provided_sources
    }

    for finding in llm_report.findings:
        unknown_ids = (
                set(finding.source_ids) - valid_source_ids
        )

        if unknown_ids:
            raise CitationValidationError()