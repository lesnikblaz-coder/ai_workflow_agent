from pydantic import BaseModel

from src.schemas.search import SearchResult


class ResearchPlan(BaseModel):
    topic: str
    research_questions: list[str]
    search_queries: list[str]


class ResearchEvidence(BaseModel):
    plan: ResearchPlan
    search_results: dict[str, list[SearchResult]]