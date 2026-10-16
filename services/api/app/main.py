import hmac
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.anthropic_llm import AnthropicLLMProvider
from app.ai.registry import register as register_llm
from app.ai.registry import unregister as unregister_llm
from app.ai.sarvam import SarvamLLMProvider
from app.core.config import Settings, get_settings
from app.core.crypto import FieldCrypto
from app.core.db import create_db_engine, create_sessionmaker
from app.core.errors import install_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.observability import (
    HardeningMiddleware,
    Metrics,
    MetricsMiddleware,
    migration_state,
    refresh_job_gauges,
    render,
)
from app.modules.ai.router import router as ai_router
from app.modules.audit.router import router as audit_router
from app.modules.clinical.router import router as clinical_router
from app.modules.consent.router import router as consent_router
from app.modules.cover.router import router as cover_router
from app.modules.identity.router import auth_router, users_router
from app.modules.interactions.gateway import router as gateway_router
from app.modules.interactions.router import router as interactions_router
from app.modules.interop.router import router as fhir_router
from app.modules.languages.router import router as languages_router
from app.modules.patients.router import router as patients_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.summaries.router import router as summaries_router
from app.modules.templates.router import router as templates_router
from app.modules.tenancy.router import router as tenancy_router
from app.speech.audio_store import LocalEncryptedAudioStore
from app.speech.registry import register, unregister
from app.speech.sarvam import SarvamSpeechProvider

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
    llm_key = settings.anthropic_api_key.get_secret_value()
    if llm_key:
        register_llm(
            "anthropic",
            lambda: AnthropicLLMProvider(
                llm_key,
                model=settings.anthropic_model,
                timeout_seconds=settings.llm_timeout_seconds,
            ),
        )
    else:
        unregister_llm("anthropic")
    sarvam_key = settings.sarvam_api_key.get_secret_value()
    if sarvam_key:
        register_llm(
            "sarvam",
            lambda: SarvamLLMProvider(
                sarvam_key,
                model=settings.sarvam_llm_model,
                base_url=settings.sarvam_rest_url,
                timeout=settings.llm_timeout_seconds,
            ),
        )
    else:
        unregister_llm("sarvam")
    key = settings.sarvam_api_key.get_secret_value()
    if key:
        register(
            "sarvam",
            lambda: SarvamSpeechProvider(
                key,
                model=settings.sarvam_model,
                mode=settings.sarvam_mode,
                url=settings.sarvam_url,
                use_language_hint=settings.sarvam_use_language_hint,
            ),
        )
    else:
        unregister("sarvam")
    app.state.engine = engine
    app.state.crypto = FieldCrypto(settings.field_encryption_key)
    app.state.audio_store = LocalEncryptedAudioStore(settings.audio_store_path, app.state.crypto)
    app.state.sessionmaker = create_sessionmaker(engine)

    app.state.metrics = Metrics()
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(MetricsMiddleware, metrics=app.state.metrics)
    app.add_middleware(
        HardeningMiddleware,
        max_bytes=settings.max_request_bytes,
        hsts=settings.environment == "production",
    )
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
        consent_router,
        languages_router,
        interactions_router,
        gateway_router,
        ai_router,
        summaries_router,
        templates_router,
        cover_router,
        fhir_router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    def ready() -> JSONResponse:
        """Ready only if the database answers and its schema matches this code."""
        try:
            state = migration_state(engine, Path(__file__).resolve().parent.parent)
        except Exception:  # noqa: BLE001  (never leak driver detail to an unauthenticated probe)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        if state == "behind":
            return JSONResponse({"status": "migrations_pending"}, status_code=503)
        return JSONResponse({"status": "ready", "migrations": state})

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics(request: Request) -> Response:
        token = settings.metrics_token
        if not token and settings.environment == "production":
            return Response(status_code=404)  # disabled until a token is configured
        if token and not hmac.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {token}"
        ):
            return Response(status_code=401)
        refresh_job_gauges(app.state.metrics, engine)
        body, content_type = render(app.state.metrics)
        return Response(body, media_type=content_type)

    return app
