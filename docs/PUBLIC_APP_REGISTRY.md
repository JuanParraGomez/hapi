# Public App Registry

`hapi` stores public app inventory in SQLite.

## Tables
- `public_apps`
- `public_deployments`
- `sync_events`

## public_apps fields
- `app_id`
- `slug`
- `name`
- `app_type`
- `framework`
- `repo_url`
- `branch`
- `commit_sha`
- `public_url`
- `domain`
- `deployment_provider`
- `data_strategy_json`
- `project_slug`
- `status`
- `tags_json`
- `metadata_json`
- `created_at`
- `updated_at`

## Purpose
This registry is the public-plane source of truth used by `langgraph-agent-server` to avoid collisions, detect existing public apps, and store deployment visibility after publishing.
