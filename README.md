# hapi

`hapi` is a separate control-plane service for VPS/docker discovery and controlled operations.

## Role in your stack
- `terminal-tools`: local terminal orchestration
- `hapi`: remote/VPS docker inventory plus UI-project orchestration over `coolify-server`
- `coolify-server`: central monorepo for long-lived apps, sandboxes, templates, registry and RAG manifests
- existing services (`rag-server`, `CanonDock`, `celery-server`) remain untouched

## Architecture
IA -> MCP (`hapi`) -> FastAPI (`hapi`) -> discovery / project orchestration / adapters (`Coolify`, `rag-server`)

## Phase 1 kept intact
- Docker discovery: containers, networks, volumes, ports, labels
- Exposure classification: `public | internal | unknown`
- Service mutability policy: `manageable | read_only | untouchable`
- Default mutability: `read_only`
- Explicit manageable services: `n8n`, `my-video`

## Phase 2 added
`hapi` now understands `coolify-server` as the central root for UI projects.

Central layout:
- `apps/`: long-lived apps
- `sandboxes/`: short-lived experiments
- `templates/`: reusable starters
- `registry/projects/`: source of truth manifests
- `rag/manifests/`: sync manifests for documentation indexed into `rag-server`
- `docs/`: higher-level operating docs

## Core rules
- no new repos by default for UI projects
- no orphan folders outside approved roots
- every project gets:
  - `README.md`
  - `app.meta.yaml`
  - `deploy.meta.yaml`
- every project is registered in `registry/projects/<slug>.yaml`
- long-lived UI projects prefer `Coolify`
- short-lived experiments prefer `sandboxes/` and can later be promoted
- RAG sync indexes documentation and metadata, not all source code by default

## Project model
Project creation produces:
- folder under `apps/<slug>` or `sandboxes/<slug>`
- scaffold copied from a known template
- mandatory README and metadata
- registry manifest
- optional deploy preparation
- optional RAG sync

Important metadata fields include:
- `slug`
- `project_type`
- `status`
- `template`
- `project_root`
- `deployment_provider`
- `coolify_project`
- `coolify_application`
- `domain`
- `rag_sync_enabled`

## Long-lived vs short-lived
### Long-lived
- created in `apps/<slug>`
- persistent
- prefer `Coolify`
- prepared for domain + deploy workflow
- suitable for real products and maintained UI projects

### Short-lived
- created in `sandboxes/<slug>`
- TTL supported
- aimed at prototypes, labs and experiments
- can be promoted later to `apps/<slug>`

## Promotion
`hapi` supports sandbox promotion:
- move `sandboxes/<slug>` -> `apps/<slug>`
- update metadata
- update registry
- rewrite README
- refresh RAG sync state
- optionally prepare deploy through `Coolify`

## RAG sync
Primary indexed files:
- `README.md`
- `app.meta.yaml`
- `deploy.meta.yaml`

Optional if present:
- `ARCHITECTURE.md`
- `DECISIONS.md`

The sync is conceptual, not full-code indexing by default.

Refresh heuristic:
- refresh when README/metadata signatures change
- intended for conceptual changes: purpose, architecture, domain, deployment, stack, usage, integrations
- not intended for trivial style-only changes

## Context rendering for agents
`hapi` can render compact project context so agents do not work blind.

Returned context includes:
- project identity
- project type
- current status
- root path
- template
- deployment provider
- domain
- README summary
- RAG sync status
- operational notes for the agent

## Coolify integration
`Coolify` is the preferred backend for long-lived UI projects.

Current integration covers:
- listing projects
- ensuring a Coolify project exists
- preparing deployment metadata for monorepo subdirectories
- deployment handoff using `base_directory=/apps/<slug>` or `/sandboxes/<slug>`

If `Coolify` is not configured:
- `hapi` degrades with explicit errors
- local project creation and registry still work

## Policies
Files:
- `app/policies/service_mutability.yaml`
- `app/policies/project_layout_policy.yaml`
- `app/policies/template_policy.yaml`
- `app/policies/registry_policy.yaml`
- `app/policies/rag_sync_policy.yaml`
- `app/policies/coolify_policy.yaml`

## API
Phase 1 endpoints:
- `GET /health`
- `GET /policy/mutability`
- `POST /discovery/run`
- `GET /services`
- `GET /services/{service_id}`
- `POST /services/{service_id}/actions`

Phase 2 endpoints:
- `POST /projects`
- `POST /projects/create`
- `GET /projects`
- `GET /projects/{slug}`
- `GET /projects/{slug}/validate`
- `POST /projects/{slug}/edit-context`
- `PATCH /projects/{slug}`
- `POST /projects/{slug}/promote`
- `POST /projects/{slug}/deploy`
- `POST /projects/{slug}/sync-rag`
- `GET /projects/{slug}/rag-status`
- `GET /registry`
- `GET /registry/{slug}`
- `POST /registry/refresh`
- `GET /coolify/projects`

## MCP tools
- `hapi_health`
- `hapi_run_discovery`
- `hapi_list_services`
- `hapi_get_service`
- `hapi_service_action`
- `hapi_get_mutability_policy`
- `hapi_create_project`
- `hapi_list_projects`
- `hapi_get_project`
- `hapi_render_project_context`
- `hapi_deploy_project`
- `hapi_promote_project`
- `hapi_sync_project_rag`
- `hapi_get_project_rag_status`
- `hapi_list_registry`
- `hapi_refresh_registry`
- `hapi_update_project`

## Environment
Important variables:
- `COOLIFY_SERVER_REPO_ROOT`
- `COOLIFY_ENABLED`
- `COOLIFY_BASE_URL`
- `COOLIFY_API_TOKEN`
- `DEFAULT_LONG_LIVED_ROOT`
- `DEFAULT_SHORT_LIVED_ROOT`
- `RAG_SYNC_ENABLED`
- `RAG_API_BASE_URL`

See `.env.example`.

## Local run
```bash
cd /home/juan/Documents/hapi
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
cp -n .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095
```

## MCP run
```bash
cd /home/juan/Documents/hapi
. .venv/bin/activate
export HAPI_API_BASE_URL=http://127.0.0.1:8095
python -m app.mcp_server.server
```

## Docker run
```bash
cd /home/juan/Documents/hapi
cp -n .env.example .env
docker compose up --build -d
docker compose ps
```

## Tests
```bash
cd /home/juan/Documents/hapi
. .venv/bin/activate
pytest -q
```
