from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.policies import router as policies_router
from app.api.runs import router as runs_router
from app.api.v1 import router as v1_router
from app.api.worker import router as worker_router
from app.auth.security import ensure_bootstrap_token
from app.config import get_settings
from app.db import database_schema_is_ready, get_engine, seed_demo_state

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    is_sqlite_test_engine = str(engine.url).startswith("sqlite")
    if settings.database_migration_required and not is_sqlite_test_engine:
        if not database_schema_is_ready(engine):
            raise RuntimeError("database_schema_not_ready: run alembic upgrade head")
    if settings.environment == "development" and settings.seed_demo:
        with Session(engine) as session:
            seed_demo_state(session)
    if not is_sqlite_test_engine:
        with Session(engine) as session:
            ensure_bootstrap_token(session, settings)
    yield


app = FastAPI(title="AgentGate API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(runs_router)
app.include_router(approvals_router)
app.include_router(audit_router)
app.include_router(policies_router)
app.include_router(v1_router)
app.include_router(worker_router)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
    code = str(detail.get("code", "http_error"))
    message = str(detail.get("message", "Request failed"))
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
                "message": "Request validation failed",
            }
        },
    )
