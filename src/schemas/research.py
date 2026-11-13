from pydantic import BaseModel

from src.schemas.search import SearchResult


class ResearchPlan(BaseModel):
    topic: str
    research_questions: list[str]
    search_queries: list[str]


class ResearchEvidence(BaseModel):
    plan: ResearchPlan
    sourced_results: list[ResearchSource]


class ResearchSource(BaseModel):
    source_id: str
    search_query: str
    result: SearchResult