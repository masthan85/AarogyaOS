from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.crypto import FieldCrypto
from app.core.db import create_db_engine, create_sessionmaker
from app.core.errors import install_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.modules.audit.router import router as audit_router
from app.modules.clinical.router import router as clinical_router
from app.modules.identity.router import auth_router, users_router
from app.modules.patients.router import router as patients_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.tenancy.router import router as tenancy_router

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)

    app = FastAPI(
        title="AarogyaOS API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.crypto = FieldCrypto(settings.field_encryption_key)
    app.state.sessionmaker = create_sessionmaker(engine)

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    install_error_handlers(app)

    for router in (
        auth_router,
        users_router,
        tenancy_router,
        audit_router,
        patients_router,
        scheduling_router,
        clinical_router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    def ready() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return {"status": "ready"}

    return app
