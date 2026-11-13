import time
import asyncio

from src.agents.research_agent import ResearchAgent
from src.schemas.search import SearchResult
from src.schemas.research import ResearchPlan, ResearchEvidence, ResearchSource
from src.tools.web_search import WebSearchTool
from src.logging_config import logger


class ResearchService:
    MAX_SEARCH_QUERIES: int = 3
    MAX_RESULTS_PER_QUERY: int = 3

    def __init__(self, agent: ResearchAgent, search_tool: WebSearchTool):
        self.agent = agent
        self.search_tool = search_tool

    async def research(
            self,
            instruction: str
    ) -> ResearchEvidence:
        """
        Coordinates the research process.

        1. Generate a research plan.
        2. Extract unique search queries.
        3. Execute searches.
        4. Collect and return search results.
        :param instruction:
        :returns: ResearchEvidence
        """

        start_time = time.perf_counter()

        research_plan = await self._generate_plan(instruction)

        unique_queries = self._get_unique_queries(research_plan.search_queries)

        search_results = await self._execute_search(unique_queries)

        sourced_results = self._build_sources(search_results)

        total_duration = time.perf_counter() - start_time

        logger.info("Research pipeline duration: %.2f s", total_duration)

        evidence = ResearchEvidence(
            plan=research_plan,
            sourced_results=sourced_results
        )

        """report = ...

        return report"""

        return evidence

    async def _generate_plan(self, instruction) -> ResearchPlan:
        """Generate a research plan using the research agent."""
        start_time = time.perf_counter()

        research_plan = await self.agent.run(instruction)

        duration = time.perf_counter() - start_time

        logger.info("Research planning: %.2f s", duration)

        return research_plan

    def _get_unique_queries(self, search_queries: list[str]) -> list[str]:
        """Remove duplicate search queries and enforce the search limit."""
        return list(dict.fromkeys(search_queries))[:self.MAX_SEARCH_QUERIES]

    async def _execute_search(self, queries: list[str]) -> dict[str, list[SearchResult]]:
        """Execute all search queries concurrently."""
        start_time = time.perf_counter()

        search_tasks = [
            self.search_tool.search(
                query=query,
                max_results=self.MAX_RESULTS_PER_QUERY
            )
            for query in queries
        ]

        results = await asyncio.gather(*search_tasks)

        duration = time.perf_counter() - start_time

        logger.info(
            "Executed %s search queries concurrently: %.2f s",
            len(queries),
            duration
        )

        return dict(zip(queries, results))

    @staticmethod
    def _build_sources(search_results: dict[str, list[SearchResult]]) -> list[ResearchSource]:
        """Build sources for each generated search result for each query. (3 queries with 3 sources each => 9 sourced results)"""
        sources = []

        for query, results in search_results.items():
            for result in results:
                source = ResearchSource(
                    source_id=f"S{len(sources) + 1}",
                    search_query=query,
                    result=result
                )

                sources.append(source)

        return sources