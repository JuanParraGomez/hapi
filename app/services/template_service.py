from __future__ import annotations

import shutil
from pathlib import Path

from app.models.schemas import TemplateDefinition


class TemplateService:
    def __init__(self, repo_root: Path, templates_root: str):
        self.repo_root = repo_root
        self.templates_root = templates_root

    def template_dir(self, template_slug: str) -> Path:
        return self.repo_root / self.templates_root / template_slug

    def scaffold_dir(self, template_slug: str) -> Path:
        return self.template_dir(template_slug) / "scaffold"

    def exists(self, template_slug: str) -> bool:
        return self.scaffold_dir(template_slug).exists()

    def copy_scaffold(self, template: TemplateDefinition, destination: Path) -> list[str]:
        scaffold = self.scaffold_dir(template.slug)
        copied: list[str] = []
        if not scaffold.exists():
            return copied
        for source in scaffold.rglob("*"):
            relative = source.relative_to(scaffold)
            target = destination / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(relative))
        return copied
