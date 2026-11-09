from google import genai

from src.config import settings
from src.schemas.research import ResearchPlan
from src.exceptions.custom import LLMEmptyOutputError
from src.agents.prompts import RESEARCH_PLANNER_INSTRUCTIONS


class ResearchAgent:
    def __init__(self, client: genai.client.AsyncClient):
        self.client = client

    async def run(self, instruction: str) -> str:
        interaction = await self.client.interactions.create(
            model=settings.GEMINI_MODEL,
            system_instruction=RESEARCH_PLANNER_INSTRUCTIONS,
            input=instruction,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": ResearchPlan.model_json_schema()
            }
        )

        if not interaction.output_text:
            raise LLMEmptyOutputError()

        plan = ResearchPlan.model_validate_json(
            interaction.output_text
        )

        return plan.model_dump_json()