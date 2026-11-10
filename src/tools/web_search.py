import httpx

from src.schemas.search import SearchResult


class WebSearchTool:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self.client = client
        self.api_key = api_key

    async def search(self, query: str, max_results: int = 3) -> list[SearchResult]:
        """
        Executes individual search requests.

        :param query:
        :param max_results:
        :return: list[SearchResult]
        """

        if not 1 <= max_results <= 5:
            raise ValueError("max_results must be between 1 and 5")

        response = await self.client.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {self.api_key}"
            },
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False
            }
        )

        response.raise_for_status()

        data = response.json()

        return [
            SearchResult(
                title=item["title"],
                url=item["url"],
                snippet=item["content"]
            )
            for item in data["results"]
        ]