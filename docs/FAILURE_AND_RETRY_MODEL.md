# Failure and Retry Model

## hapi scope
`hapi` does not own workflow retries. It returns explicit state so the caller can retry safely.

## Safe retries
- public app register: safe upsert
- deployment status record: safe replace of latest deployment state
- sync event record: append-only, caller should pass correlation id

## Failure reporting
If `hapi` fails, the caller should capture:
- `run_id`
- `slug`
- `app_id` if known
- failing endpoint
- upstream service involved (`coolify`, `rag-server`, etc.)

## Non-goals
- no internal planner
- no internal agent loops
- no implicit retries hidden from LangGraph
