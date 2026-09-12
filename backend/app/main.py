"""Application factory, error handlers and the single-page UI route."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import router
from .errors import ApiError, error_body
from .store import InMemoryStore

#: backend/app/main.py -> backend/app -> backend -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_INDEX = PROJECT_ROOT / "frontend" / "index.html"

DESCRIPTION = """\
A generic platform driven entirely by configuration: register a schema, ingest
rows against it, register a dashboard configuration, and read back rendered
dashboard data. Adding a new use case -- trade, customer, anything else --
requires no backend changes. All state is held in memory.
"""

_FRAMEWORK_ERROR_CODES = {
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
}


def _register_exception_handlers(app: FastAPI) -> None:
    """Every error path -- ours, pydantic's and starlette's -- answers with the
    same envelope, so a client only ever parses one error shape."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Keeps FastAPI's 422 but replaces its default {"detail": [...]} body.
        details: list[dict[str, Any]] = []
        for error in exc.errors():
            detail: dict[str, Any] = {"issue": error.get("msg", "invalid value")}
            # loc[0] is the source ("body", "query", "path"); drop it and keep
            # the path to the offending value. A body that is not JSON at all
            # has no meaningful location.
            if error.get("type") != "json_invalid":
                location = ".".join(str(part) for part in error.get("loc", ())[1:])
                if location:
                    detail["field"] = location
            details.append(detail)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body(
                "REQUEST_VALIDATION_ERROR",
                "the request body is not in the expected format",
                details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _FRAMEWORK_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )


def create_app() -> FastAPI:
    """Build an app with its own store. Tests use this to get clean state."""
    app = FastAPI(
        title="Schema-Driven Dashboard Platform",
        description=DESCRIPTION,
        version="1.0.0",
    )
    app.state.store = InMemoryStore()
    _register_exception_handlers(app)
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve the single-file UI.

        It is one self-contained HTML file with inline CSS and JS, so a
        FileResponse is enough; no static-asset mount is needed.
        """
        if not FRONTEND_INDEX.is_file():
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                "FRONTEND_NOT_FOUND",
                "the frontend has not been built into this deployment",
            )
        return FileResponse(FRONTEND_INDEX, media_type="text/html")

    return app


app = create_app()
