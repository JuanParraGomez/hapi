# hapi

`hapi` is a separate control-plane service for VPS/docker discovery and controlled operations.

## Role in your stack
- `terminal-tools`: local terminal orchestration
- `hapi`: remote/VPS docker inventory and controlled service actions
- existing services (`rag-server`, `CanonDock`, `celery-server`) are untouched

## Architecture
IA -> MCP (`hapi`) -> FastAPI (`hapi`) -> Docker CLI (real backend)

## Key features (V1)
- Docker discovery: containers, networks, volumes, ports, labels
- Exposure classification: `public | internal | unknown`
- Service mutability policy: `manageable | read_only | untouchable`
- Default mutability: `read_only`
- Explicit manageable services: `n8n`, `my-video`
- Short-lived vs long-lived projects with TTL for short-lived

## Mutability policy
File: `app/policies/service_mutability.yaml`

Rules included:
- `n8n` => `manageable`
- `my-video` => `manageable`
- unknown => `read_only`

## API
- `GET /health`
- `GET /policy/mutability`
- `POST /discovery/run`
- `GET /services`
- `GET /services/{service_id}`
- `POST /services/{service_id}/actions` (`start|stop|restart`, only manageable)
- `POST /projects`
- `GET /projects`

## MCP tools
- `hapi_health`
- `hapi_run_discovery`
- `hapi_list_services`
- `hapi_get_service`
- `hapi_service_action`
- `hapi_get_mutability_policy`
- `hapi_create_project`
- `hapi_list_projects`

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
