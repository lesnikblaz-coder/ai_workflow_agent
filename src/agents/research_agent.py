from google import genai

from src.config import settings
from src.schemas.research import ResearchPlan, ResearchReport
from src.exceptions.custom import LLMEmptyOutputError
from src.agents import prompts as agent_prompts


class ResearchAgent:
    def __init__(self, client: genai.client.AsyncClient):
        self.client = client

    async def run(self, instruction: str) -> ResearchPlan:
        """Generate a research plan based on the given instruction.

        :param instruction: user's research instructions

        :return: ResearchPlan schema
        """

        interaction = await self.client.interactions.create(
            model=settings.GEMINI_MODEL,
            system_instruction=agent_prompts.RESEARCH_PLANNER_INSTRUCTIONS,
            input=instruction,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": ResearchPlan.model_json_schema()
            }
        )

        if not interaction.output_text:
            raise LLMEmptyOutputError()

        return ResearchPlan.model_validate_json(
            interaction.output_text
        )

    async def synthesize(self, model_input: str) -> ResearchReport:
        """Generates a structured research report based on provided evidence-based research.

        :param model_input: payload which consists of initial user instruction + gathered evidence by WebSearchTool
        in interaction with the research planner LLM

        :return: ResearchReport schema
        """
        interaction = await self.client.interactions.create(
            model=settings.GEMINI_MODEL,
            system_instruction=agent_prompts.SYNTHESIS_INSTRUCTIONS,
            input=model_input,
            response_format={
                "type": "text",
                "mine_type": "application/json",
                "schema": ResearchReport.model_json_schema()
            }
        )

        if not interaction.output_text:
            raise LLMEmptyOutputError()

        return ResearchReport.model_validate_json(
            interaction.output_text
        )