from pathlib import Path

from app.models.schemas import (
    DeploymentStatus,
    ProjectCreateRequest,
    ProjectDeployRequest,
    ProjectLifetime,
    ProjectPromoteRequest,
    PublicAppDeploymentRequest,
    PublicAppRegisterRequest,
    PublicAppSyncRequest,
)
from app.services.public_app_service import PublicAppService


def test_short_lived_project_created_in_sandboxes(project_service):
    result = project_service.create(ProjectCreateRequest(name="Landing Lab", lifetime=ProjectLifetime.short_lived))

    assert result.project.project_root == "sandboxes/landing-lab"
    assert result.project.ttl_hours == 24
    assert result.project.expires_at is not None
    assert (project_service.repo_root / "sandboxes" / "landing-lab" / "README.md").exists()


def test_long_lived_project_created_in_apps(project_service):
    result = project_service.create(
        ProjectCreateRequest(name="CRM Portal", lifetime=ProjectLifetime.long_lived, template="nextjs-starter")
    )

    assert result.project.project_root == "apps/crm-portal"
    assert result.project.expires_at is None
    assert result.project.deployment_provider.value == "coolify"
    assert (project_service.repo_root / "apps" / "crm-portal" / "app.meta.yaml").exists()


def test_duplicate_slug_validation(project_service):
    project_service.create(ProjectCreateRequest(name="CRM Portal", lifetime=ProjectLifetime.long_lived))
    validation = project_service.validate_slug("crm-portal")

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
    project_service.create(ProjectCreateRequest(name="CRM Portal", lifetime=ProjectLifetime.long_lived))
    context = project_service.render_context("crm-portal")

    assert context.slug == "crm-portal"
    assert context.project_root == "apps/crm-portal"
    assert "edit README" in " ".join(context.notes_for_agent)


def test_promote_sandbox_to_app(project_service):
    project_service.create(ProjectCreateRequest(name="Idea Lab", lifetime=ProjectLifetime.short_lived))
    promoted = project_service.promote("idea-lab", ProjectPromoteRequest(target_slug="idea-crm"))

    assert promoted.project.project_root == "apps/idea-crm"
    assert promoted.project.promoted_from == "sandboxes/idea-lab"
    assert (project_service.repo_root / "apps" / "idea-crm").exists()
    assert not (project_service.repo_root / "sandboxes" / "idea-lab").exists()


def test_rag_sync_and_change_detection(project_service):
    project_service.create(ProjectCreateRequest(name="CRM Portal", lifetime=ProjectLifetime.long_lived))
    sync = project_service.sync_rag("crm-portal", force=True)
    status = project_service.rag_status("crm-portal")
    change = project_service.check_conceptual_change("crm-portal")

    assert sync.synced is True
    assert status.document_id == "doc-crm-portal"
    assert change.reason == "test-check"
    assert sync.details["metadata"]["tenant_id"] == "ui-projects"


def test_deploy_calls_coolify_adapter(project_service):
    project_service.create(ProjectCreateRequest(name="CRM Portal", lifetime=ProjectLifetime.long_lived))
    deploy = project_service.deploy("crm-portal", ProjectDeployRequest())
    project = project_service.get("crm-portal")

    assert deploy.status == "deploying"
    assert deploy.provider.value == "coolify"
    assert project.coolify_application == "coolify-crm-portal"


def test_public_app_registry_flow(project_service):
    service = PublicAppService(db=project_service.db, coolify_service=project_service.coolify_service)
    app = service.register(
        PublicAppRegisterRequest(
            slug="crm-ui",
            name="CRM UI",
            app_type="nextjs",
            project_slug="crm",
            repo_url="git@github.com:JuanParraGomez/coolify-server.git",
            branch="main",
            commit_sha="abc123",
            domain="crm-ui.apps.uniflexa.cloud",
        )
    )
    deployment = service.record_deployment(
        app.app_id,
        PublicAppDeploymentRequest(
            deployment_status=DeploymentStatus.ready_for_coolify,
            domain="crm-ui.apps.uniflexa.cloud",
            details={"base_directory": "/apps/crm-ui"},
        ),
    )
    sync = service.record_sync(app.app_id, PublicAppSyncRequest(target="rag", details={"document_id": "doc-1"}))
    summary = service.public_summary()

    assert service.get_by_slug("crm-ui").app_id == app.app_id
    assert deployment.deployment_status.value == "ready_for_coolify"
    assert sync.target == "rag"
    assert summary.total_apps == 1
    assert summary.coolify["reachable"] is True


def test_delete_long_lived_project_uses_soft_rag_note(project_service):
    project_service.create(ProjectCreateRequest(name="CRM Platform", lifetime=ProjectLifetime.long_lived))
    deleted = project_service.delete("crm-platform", purge_coolify=False, purge_public_registry=False)

    assert deleted.deleted is True
    assert deleted.rag_action == "soft_note"
    assert deleted.rag_deleted is False
    assert deleted.rag_note_document_id == "doc-delete-crm-platform"
    assert "apps/crm-platform" in deleted.removed_paths
    assert "rag/manifests/crm-platform.yaml" in deleted.removed_paths


def test_delete_short_lived_project_uses_hard_rag_delete(project_service):
    project_service.create(ProjectCreateRequest(name="Idea Lab", lifetime=ProjectLifetime.short_lived))
    deleted = project_service.delete("idea-lab", purge_coolify=False, purge_public_registry=False)

    assert deleted.deleted is True
    assert deleted.rag_action == "hard_delete"
    assert deleted.rag_deleted is True
    assert deleted.rag_note_document_id == "doc-delete-idea-lab"
    assert "sandboxes/idea-lab" in deleted.removed_paths
