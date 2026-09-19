from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.api.actions import router as actions_router
from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.monitoring import router as monitoring_router
from app.api.platform import router as platform_router
from app.api.policies import router as policies_router
from app.api.runs import router as runs_router
from app.api.v1 import router as v1_router
from app.api.worker import router as worker_router
from app.api.workspaces import router as workspaces_router
from app.auth.security import ensure_bootstrap_token
from app.config import get_settings
from app.db import (
    create_db_and_tables,
    database_schema_is_ready,
    get_engine,
    reset_db_and_tables,
    seed_example_state,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    is_sqlite_test_engine = str(engine.url).startswith("sqlite")
    if settings.database_migration_required and not is_sqlite_test_engine:
        if not database_schema_is_ready(engine):
            raise RuntimeError("database_schema_not_ready: run alembic upgrade head")
    if is_sqlite_test_engine and settings.environment == "test":
        if settings.e2e_reset_database:
            reset_db_and_tables(engine)
            if settings.worker_ready_file:
                from pathlib import Path

                Path(settings.worker_ready_file).unlink(missing_ok=True)
            with Session(engine) as session:
                seed_example_state(session)
        else:
            create_db_and_tables(engine)
    if settings.environment == "development" and settings.seed_example:
        with Session(engine) as session:
            seed_example_state(session)
    if settings.auth_enabled and (not is_sqlite_test_engine or settings.environment == "test"):
        with Session(engine) as session:
            ensure_bootstrap_token(session, settings)
    yield


CORS_ALLOWED_HEADERS = [
    "Accept",
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "X-CSRF-Token",
]

app = FastAPI(
    title="AgentGate API",
    lifespan=lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=CORS_ALLOWED_HEADERS,
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(events_router)
app.include_router(runs_router)
app.include_router(approvals_router)
app.include_router(actions_router)
app.include_router(audit_router)
app.include_router(policies_router)
app.include_router(monitoring_router)
app.include_router(platform_router)
app.include_router(v1_router)
app.include_router(worker_router)
app.include_router(workspaces_router)


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
    code = str(detail.get("code", "http_error"))
    message = str(detail.get("message", "请求失败，请稍后重试。"))
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "请求参数不合法",
            }
        },
    )
