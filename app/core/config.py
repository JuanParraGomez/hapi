from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "hapi"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8095

    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8096

    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/hapi.db")

    service_mutability_policy_path: Path = Path("./app/policies/service_mutability.yaml")
    project_layout_policy_path: Path = Path("./app/policies/project_layout_policy.yaml")
    template_policy_path: Path = Path("./app/policies/template_policy.yaml")
    registry_policy_path: Path = Path("./app/policies/registry_policy.yaml")
    rag_sync_policy_path: Path = Path("./app/policies/rag_sync_policy.yaml")
    coolify_policy_path: Path = Path("./app/policies/coolify_policy.yaml")

    discovery_timeout_seconds: int = 15
    short_lived_default_ttl_hours: int = 24

    auto_refresh_inventory_on_startup: bool = True

    coolify_server_repo_root: Path = Path("/home/juan/Documents/coolify-server")
    default_long_lived_root: str = "apps"
    default_short_lived_root: str = "sandboxes"

    coolify_enabled: bool = False
    coolify_base_url: str = "http://127.0.0.1:18000"
    coolify_api_token: str | None = None

    rag_sync_enabled: bool = True
    rag_api_base_url: str = "http://127.0.0.1:8000"

    @property
    def inventory_path(self) -> Path:
        return self.data_dir / "inventory.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.inventory_path.parent.mkdir(parents=True, exist_ok=True)
    settings.coolify_server_repo_root.mkdir(parents=True, exist_ok=True)
    return settings
