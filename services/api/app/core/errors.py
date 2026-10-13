from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self, detail: str, *, code: str | None = None, extra: dict[str, object] | None = None
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        self.extra = extra or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


def _body(
    request: Request, status: int, code: str, detail: object, extra: dict[str, object] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            **(extra or {}),
            "type": f"https://aarogyaos.example/errors/{code}",
            "title": code,
            "status": status,
            "detail": detail,
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _body(request, exc.status_code, exc.code, exc.detail, exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _body(request, exc.status_code, "http_error", exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Strip submitted values: they may contain passwords or PHI.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _body(request, 422, "validation_error", errors)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("aarogya").exception("unhandled error")
        return _body(request, 500, "internal_error", "Internal server error")
