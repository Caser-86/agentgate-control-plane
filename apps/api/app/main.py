from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.health import router as health_router
from app.api.policies import router as policies_router
from app.api.runs import router as runs_router
from app.config import get_settings
from app.db import create_db_and_tables, get_engine, seed_demo_state

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    create_db_and_tables(engine)
    with Session(engine) as session:
        seed_demo_state(session)
    yield


app = FastAPI(title="AgentGate API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(runs_router)
app.include_router(approvals_router)
app.include_router(audit_router)
app.include_router(policies_router)


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
