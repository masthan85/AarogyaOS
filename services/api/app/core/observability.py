"""Metrics, request hardening and readiness.

Metrics carry route *templates* (`/patients/{patient_id}`), never raw paths, ids, query strings or
bodies, so nothing identifying can reach a monitoring system. Counters are per process: when more
than one worker runs, the scraper must sum across them (standard Prometheus practice).
"""

from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "aarogya_http_requests_total",
            "HTTP requests",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "aarogya_http_request_duration_seconds",
            "HTTP request duration",
            ["method", "route"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.job_success = Gauge(
            "aarogya_job_last_success_timestamp_seconds",
            "Unix time of the last successful scheduled job run",
            ["job"],
            registry=self.registry,
        )


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app, self.metrics = app, metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import time

        start = time.perf_counter()
        status = {"code": 500}

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            if template not in ("/metrics",):
                method = scope["method"]
                self.metrics.requests.labels(method, template, str(status["code"])).inc()
                self.metrics.latency.labels(method, template).observe(time.perf_counter() - start)


class HardeningMiddleware:
    """Security headers on every response and a cap on request size."""

    def __init__(self, app: ASGIApp, *, max_bytes: int, hsts: bool) -> None:
        self.app, self.max_bytes, self.hsts = app, max_bytes, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send, path)
            return

        seen = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:  # chunked upload that lied or omitted its length
                    raise _TooLarge
            return message

        async def with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                out = [(k, v) for k, v in message["headers"]]
                names = {k.lower() for k, _ in out}
                for k, v in self._headers(path):
                    if k not in names:
                        out.append((k, v))
                message = {**message, "headers": out}
            await send(message)

        try:
            await self.app(scope, counted_receive, with_headers)
        except _TooLarge:
            if not started:
                await self._reject(send, path)

    def _headers(self, path: str) -> list[tuple[bytes, bytes]]:
        h = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
        ]
        if path.startswith("/api/"):
            # Clinical responses must not be stored by browsers or intermediaries.
            h += [
                (b"cache-control", b"no-store"),
                (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
            ]
        if self.hsts:
            h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        return h

    async def _reject(self, send: Send, path: str) -> None:
        body = b'{"title":"payload_too_large","status":413,"detail":"Request body is too large"}'
        headers = [(b"content-type", b"application/problem+json"), *self._headers(path)]
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


def migration_state(engine: Engine, project_root: Path) -> str:
    """'ok' when the database is at the code's head revision, 'behind' if not, 'unknown' if we
    cannot tell (for instance the migration scripts are not shipped)."""
    ini = project_root / "alembic.ini"
    if not ini.exists():
        return "unknown"
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    heads = set(ScriptDirectory.from_config(cfg).get_heads())
    with engine.connect() as conn:
        current = {r[0] for r in conn.execute(text("select version_num from alembic_version"))}
    return "ok" if current == heads else "behind"


def refresh_job_gauges(metrics: Metrics, engine: Engine) -> None:
    from sqlalchemy.orm import Session

    from app.core.db import set_tenant
    from app.jobs import last_success

    try:
        with Session(engine) as s:
            set_tenant(s, None, bypass=True)
            for name, at in last_success(s).items():
                metrics.job_success.labels(name).set(at.timestamp())
    except Exception:  # noqa: BLE001  (a scrape must never fail because the ledger is unreadable)
        return


def render(metrics: Metrics) -> tuple[bytes, str]:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return generate_latest(metrics.registry), CONTENT_TYPE_LATEST


__all__ = ["HardeningMiddleware", "Metrics", "MetricsMiddleware", "migration_state", "render"]
