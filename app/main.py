from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.container import build_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    container = build_container(settings)
    app.state.container = container
    if settings.auto_refresh_inventory_on_startup:
        payload = container.discovery_service.run()
        container.inventory_service.store_run(payload)
    yield


app = FastAPI(title="hapi", version="0.1.0", lifespan=lifespan)
app.include_router(router)
