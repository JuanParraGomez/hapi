from __future__ import annotations

import os

import httpx
from fastmcp import FastMCP

API_BASE = os.getenv("HAPI_API_BASE_URL", "http://127.0.0.1:8095")
TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8096"))

mcp = FastMCP(name="hapi-mcp")


async def _get(path: str):
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{API_BASE}{path}")
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, payload: dict | None = None):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API_BASE}{path}", json=payload or {})
        resp.raise_for_status()
        return resp.json()


@mcp.tool
def hapi_health() -> dict:
    return {"status": "ok", "service": "hapi-mcp", "api_base": API_BASE}


@mcp.tool
async def hapi_run_discovery() -> dict:
    return await _post("/discovery/run")


@mcp.tool
async def hapi_list_services() -> dict:
    data = await _get("/services")
    return {"services": data, "count": len(data)}


@mcp.tool
async def hapi_get_service(service_id: str) -> dict:
    return await _get(f"/services/{service_id}")


@mcp.tool
async def hapi_service_action(service_id: str, action: str) -> dict:
    return await _post(f"/services/{service_id}/actions", {"action": action})


@mcp.tool
async def hapi_get_mutability_policy() -> dict:
    return await _get("/policy/mutability")


@mcp.tool
async def hapi_create_project(name: str, lifetime: str, description: str = "", ttl_hours: int | None = None) -> dict:
    return await _post(
        "/projects",
        {
            "name": name,
            "description": description or None,
            "lifetime": lifetime,
            "ttl_hours": ttl_hours,
        },
    )


@mcp.tool
async def hapi_list_projects() -> dict:
    data = await _get("/projects")
    return {"projects": data, "count": len(data)}


def main() -> None:
    mcp.run(transport=TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
