from __future__ import annotations

from pathlib import Path

import yaml

from app.models.schemas import CoolifyPolicy, ProjectLayoutPolicy, RagSyncPolicy, RegistryPolicy, TemplateDefinition


class ProjectPolicyService:
    def __init__(
        self,
        project_layout_path: Path,
        template_policy_path: Path,
        registry_policy_path: Path,
        rag_sync_policy_path: Path,
        coolify_policy_path: Path,
    ):
        self.project_layout = ProjectLayoutPolicy.model_validate(self._load_yaml(project_layout_path))
        raw_templates = self._load_yaml(template_policy_path)
        self.templates = [TemplateDefinition.model_validate(item) for item in raw_templates.get("templates", [])]
        self.registry = RegistryPolicy.model_validate(self._load_yaml(registry_policy_path))
        self.rag_sync = RagSyncPolicy.model_validate(self._load_yaml(rag_sync_policy_path))
        self.coolify = CoolifyPolicy.model_validate(self._load_yaml(coolify_policy_path))

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"policy_file_invalid:{path}")
        return data

    def template_by_slug(self, slug: str) -> TemplateDefinition:
        for template in self.templates:
            if template.slug == slug:
                return template
        raise KeyError(f"template_not_found:{slug}")

    def template_slugs(self) -> list[str]:
        return [template.slug for template in self.templates]
