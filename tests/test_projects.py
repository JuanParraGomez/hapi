from pathlib import Path

from app.models.schemas import ProjectCreateRequest, ProjectDeployRequest, ProjectLifetime, ProjectPromoteRequest


def test_short_lived_project_created_in_sandboxes(project_service):
    result = project_service.create(ProjectCreateRequest(name="Landing Lab", lifetime=ProjectLifetime.short_lived))

    assert result.project.project_root == "sandboxes/landing-lab"
    assert result.project.ttl_hours == 24
    assert result.project.expires_at is not None
    assert (project_service.repo_root / "sandboxes" / "landing-lab" / "README.md").exists()


def test_long_lived_project_created_in_apps(project_service):
    result = project_service.create(ProjectCreateRequest(name="CRM", lifetime=ProjectLifetime.long_lived, template="nextjs-starter"))

    assert result.project.project_root == "apps/crm"
    assert result.project.expires_at is None
    assert result.project.deployment_provider.value == "coolify"
    assert (project_service.repo_root / "apps" / "crm" / "app.meta.yaml").exists()


def test_duplicate_slug_validation(project_service):
    project_service.create(ProjectCreateRequest(name="CRM", lifetime=ProjectLifetime.long_lived))
    validation = project_service.validate_slug("crm")

    assert validation.available is False
    assert validation.reason == "slug_already_exists"


def test_generation_of_readme_metadata_and_registry(project_service):
    result = project_service.create(ProjectCreateRequest(name="Ops Portal", lifetime=ProjectLifetime.long_lived, template="react-starter"))

    root = project_service.repo_root / "apps" / "ops-portal"
    assert (root / "README.md").read_text(encoding="utf-8").startswith("# Ops Portal")
    assert (root / "app.meta.yaml").exists()
    assert (root / "deploy.meta.yaml").exists()
    assert (project_service.repo_root / result.project.registry_path).exists()


def test_render_project_context(project_service):
    project_service.create(ProjectCreateRequest(name="CRM", lifetime=ProjectLifetime.long_lived))
    context = project_service.render_context("crm")

    assert context.slug == "crm"
    assert context.project_root == "apps/crm"
    assert "edit README" in " ".join(context.notes_for_agent)


def test_promote_sandbox_to_app(project_service):
    project_service.create(ProjectCreateRequest(name="Idea Lab", lifetime=ProjectLifetime.short_lived))
    promoted = project_service.promote("idea-lab", ProjectPromoteRequest(target_slug="idea-crm"))

    assert promoted.project.project_root == "apps/idea-crm"
    assert promoted.project.promoted_from == "sandboxes/idea-lab"
    assert (project_service.repo_root / "apps" / "idea-crm").exists()
    assert not (project_service.repo_root / "sandboxes" / "idea-lab").exists()


def test_rag_sync_and_change_detection(project_service):
    project_service.create(ProjectCreateRequest(name="CRM", lifetime=ProjectLifetime.long_lived))
    sync = project_service.sync_rag("crm", force=True)
    status = project_service.rag_status("crm")
    change = project_service.check_conceptual_change("crm")

    assert sync.synced is True
    assert status.document_id == "doc-crm"
    assert change.reason == "test-check"


def test_deploy_calls_coolify_adapter(project_service):
    project_service.create(ProjectCreateRequest(name="CRM", lifetime=ProjectLifetime.long_lived))
    deploy = project_service.deploy("crm", ProjectDeployRequest())

    assert deploy.status == "ready_for_coolify"
    assert deploy.provider.value == "coolify"
