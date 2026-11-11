import time

from src.agents.research_agent import ResearchAgent
from src.schemas.search import SearchResult
from src.schemas.research import ResearchPlan
from src.tools.web_search import WebSearchTool
from src.logging_config import logger


class ResearchService:
    def __init__(self, agent: ResearchAgent, search_tool: WebSearchTool):
        self.agent = agent
        self.search_tool = search_tool

    async def research(self, instruction: str) -> tuple[ResearchPlan, dict[str, list[SearchResult]]]:
        """
        Coordinates the research process.

        Generate research plan -> read search_queries -> execute searches
        -> collect search results -> return plan + collected evidence
        :param instruction:
        :return:
        """

        # Generate research plan
        research_start = time.perf_counter()

        research_plan = await self.agent.run(instruction)

        duration_1 = time.perf_counter() - research_start
        logger.info("Research planning: %.2f s", duration_1)

        search_results: dict[str, list[SearchResult]] = {}

        # Execute 3 unique search queries
        for i, query in enumerate(research_plan.search_queries[:3], start=1):
            start = time.perf_counter()

            search_results[query] = await self.search_tool.search(
                query=query,
                max_results=3
            )

            duration_2 = time.perf_counter() - start
            logger.info(
                "Search query %s: %.2f s",
                i,
                duration_2
            )

        duration_3 = time.perf_counter() - research_start
        logger.info("Research planning + retrieval: %.2f s", duration_3)

        return research_plan, search_results
