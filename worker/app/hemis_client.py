from typing import Any

import httpx

from afu_shared.settings import settings

PAGE_LIMIT = 200


class HemisClient:
    def __init__(self) -> None:
        self._headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {settings.api_hemis_token}",
        }
        self._base_url = settings.api_hemis_url.rstrip("/")

    async def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=30.0) as client:
            while True:
                resp = await client.get(path, params={**params, "page": page, "limit": PAGE_LIMIT})
                resp.raise_for_status()
                body = resp.json()
                if not body.get("success"):
                    raise RuntimeError(f"HEMIS API error at {path} page {page}: {body.get('error')}")
                data = body["data"]
                items.extend(data["items"])
                pagination = data.get("pagination")
                if not pagination or page >= pagination.get("pageCount", page):
                    break
                page += 1
        return items

    async def fetch_departments(self) -> list[dict[str, Any]]:
        return await self._paginate("/rest/v1/data/department-list", {})

    async def fetch_employees(self) -> list[dict[str, Any]]:
        return await self._paginate("/rest/v1/data/employee-list", {"type": "all"})
