from pydantic import BaseModel


class ResearchPlan(BaseModel):
    topic: str
    research_questions: list[str]
    search_queries: list[str]