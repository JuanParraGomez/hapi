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


async def _patch(path: str, payload: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(f"{API_BASE}{path}", json=payload)
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
async def hapi_create_project(
    name: str,
    lifetime: str,
    description: str = "",
    slug: str | None = None,
    template: str | None = None,
    ttl_hours: int | None = None,
    deploy_now: bool = False,
) -> dict:
    return await _post(
        "/projects/create",
        {
            "name": name,
            "description": description or None,
            "slug": slug,
            "template": template,
            "lifetime": lifetime,
            "ttl_hours": ttl_hours,
            "deploy_now": deploy_now,
        },
    )


@mcp.tool
async def hapi_list_projects() -> dict:
    data = await _get("/projects")
    return {"projects": data, "count": len(data)}


@mcp.tool
async def hapi_get_project(slug: str) -> dict:
    return await _get(f"/projects/{slug}")


@mcp.tool
async def hapi_render_project_context(slug: str) -> dict:
    return await _post(f"/projects/{slug}/edit-context", {"include_readme": True})


@mcp.tool
async def hapi_deploy_project(slug: str, domain: str | None = None, environment_profile: str = "production") -> dict:
    return await _post(
        f"/projects/{slug}/deploy",
        {"domain": domain, "environment_profile": environment_profile},
    )


@mcp.tool
async def hapi_promote_project(slug: str, target_slug: str | None = None, domain: str | None = None, deploy_now: bool = False) -> dict:
    return await _post(
        f"/projects/{slug}/promote",
        {"target_slug": target_slug, "domain": domain, "deploy_now": deploy_now},
    )


@mcp.tool
async def hapi_sync_project_rag(slug: str, force: bool = False, note: str | None = None) -> dict:
    return await _post(f"/projects/{slug}/sync-rag", {"force": force, "note": note})


@mcp.tool
async def hapi_get_project_rag_status(slug: str) -> dict:
    return await _get(f"/projects/{slug}/rag-status")


@mcp.tool
async def hapi_list_registry() -> dict:
    return await _get("/registry")


@mcp.tool
async def hapi_refresh_registry() -> dict:
    return await _post("/registry/refresh")


@mcp.tool
async def hapi_update_project(slug: str, description: str | None = None, notes: str | None = None, domain: str | None = None, status: str | None = None) -> dict:
    payload = {"description": description, "notes": notes, "domain": domain, "status": status}
    return await _patch(f"/projects/{slug}", payload)


@mcp.tool
async def hapi_list_public_apps() -> dict:
    return await _get("/public/apps")


@mcp.tool
async def hapi_get_public_app(app_id: str) -> dict:
    return await _get(f"/public/apps/{app_id}")


@mcp.tool
async def hapi_get_public_app_by_slug(slug: str) -> dict:
    return await _get(f"/public/apps/by-slug/{slug}")


@mcp.tool
async def hapi_register_public_app(
    slug: str,
    name: str,
    app_type: str = "generic",
    framework: str | None = None,
    repo_url: str | None = None,
    branch: str | None = None,
    commit_sha: str | None = None,
    public_url: str | None = None,
    domain: str | None = None,
    project_slug: str | None = None,
    status: str = "draft",
) -> dict:
    return await _post(
        "/public/apps/register",
        {
            "slug": slug,
            "name": name,
            "app_type": app_type,
            "framework": framework,
            "repo_url": repo_url,
            "branch": branch,
            "commit_sha": commit_sha,
            "public_url": public_url,
            "domain": domain,
            "project_slug": project_slug,
            "status": status,
        },
    )


@mcp.tool
async def hapi_record_public_deployment(
    app_id: str,
    deployment_status: str,
    provider: str = "coolify",
    public_url: str | None = None,
    domain: str | None = None,
    commit_sha: str | None = None,
) -> dict:
    return await _post(
        f"/public/apps/{app_id}/deployment",
        {
            "deployment_status": deployment_status,
            "provider": provider,
            "public_url": public_url,
            "domain": domain,
            "commit_sha": commit_sha,
        },
    )


@mcp.tool
async def hapi_public_summary() -> dict:
    return await _get("/infra/public-summary")


@mcp.tool
async def hapi_coolify_health() -> dict:
    return await _get("/infra/coolify/health")


def main() -> None:
    mcp.run(transport=TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
