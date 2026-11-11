from src.agents.research_agent import ResearchAgent
from src.schemas.search import SearchResult
from src.schemas.research import ResearchPlan
from src.tools.web_search import WebSearchTool


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
        research_plan = await self.agent.run(instruction)

        search_results: dict[str, list[SearchResult]] = {}

        # Execute 3 unique search queries
        for query in research_plan.search_queries[:3]:
            search_results[query] = await self.search_tool.search(
                query=query,
                max_results=3
            )

        return research_plan, search_results