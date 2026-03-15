# UI Factory Architecture

## Role of hapi
`hapi` is the public-plane and VPS-facing service for the UI factory flow.

It does not plan or orchestrate the workflow. It provides:
- public app inventory
- public deployment registry
- Coolify health/resources lookup
- project bootstrap and metadata under `coolify-server`
- project context rendering
- documentation sync requests to `rag-server`

## Role of langgraph-agent-server
`langgraph-agent-server` is the single orchestrator for complex UI creation/update/publish flows.

It calls:
- `terminal-tools` for execution and file/build/git work
- `hapi` for public-plane and project bootstrap/registration
- `rag-server` for discovery and final memory

## System flow
1. External IA calls `langgraph-agent-server`
2. `discover_existing_ui` checks `rag-server` and `hapi`
3. `plan_ui_solution` decides template/framework/slug
4. `build_or_update_ui` bootstraps project through `hapi` and edits/builds via `terminal-tools`
5. `publish_to_git` uses `terminal-tools`
6. `deploy_via_coolify` goes through `hapi`
7. `register_public_result_in_hapi` stores public state in `hapi`
8. `ingest_ui_memory_to_rag` stores final operational memory in `rag-server`

## Source of truth boundaries
- workflow state: `langgraph-agent-server`
- public app inventory and deployment visibility: `hapi`
- project filesystem layout: `coolify-server`
- execution: `terminal-tools`
- memory/discovery: `rag-server`
