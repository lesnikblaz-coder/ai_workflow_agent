from src.schemas.research import ResearchReport, ResearchSource
from src.exceptions.custom import CitationValidationError


def validate_citations(
        llm_report: ResearchReport,
        provided_sources: list[ResearchSource]
) -> None:
    """
    Validates source citations in research report findings.

    - Findings must reference at least one valid source ID.
    - All referenced source IDs must exist in the provided sources.
    - Empty findings lists are allowed.
    """

    valid_source_ids = {
        source.source_id
        for source in provided_sources
    }

    for finding in llm_report.findings:
        unknown_ids = (
                set(finding.source_ids) - valid_source_ids
        )

        if unknown_ids or not finding.source_ids:
            raise CitationValidationError()