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

    discovery_timeout_seconds: int = 15
    short_lived_default_ttl_hours: int = 24

    auto_refresh_inventory_on_startup: bool = True

    @property
    def inventory_path(self) -> Path:
        return self.data_dir / "inventory.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.inventory_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
