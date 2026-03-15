# LangGraph <-> hapi Contract

## Principles
- `langgraph-agent-server` owns planning, retries, sequencing and workflow state.
- `hapi` owns public visibility metadata and VPS/public-plane state.
- Requests are HTTP/JSON.
- `run_id` is passed as `correlation_id` when meaningful.

## Public-plane endpoints
- `GET /public/apps`
- `GET /public/apps/{app_id}`
- `GET /public/apps/by-slug/{slug}`
- `GET /public/apps/by-domain/{domain}`
- `POST /public/apps/register`
- `POST /public/apps/{app_id}/deployment`
- `POST /public/apps/{app_id}/sync`
- `GET /public/deployments/{app_id}/status`
- `GET /infra/coolify/health`
- `GET /infra/coolify/resources`
- `GET /infra/public-summary`

## Idempotency rules
- `POST /public/apps/register` upserts by `app_id`, then `slug`, then `domain`.
- `POST /public/apps/{app_id}/deployment` replaces the latest deployment status for that app.
- `POST /public/apps/{app_id}/sync` appends a sync event.

## Error model
- `404 public_app_not_found` when lookup misses
- `4xx` for invalid payloads
- `5xx` for infrastructure/service failures

## Retry semantics expected from LangGraph
- retry on timeout/transport error
- retry on `5xx`
- do not blindly retry on `4xx`
