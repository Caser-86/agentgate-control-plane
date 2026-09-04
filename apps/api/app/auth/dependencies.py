from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.auth.models import ClientToken, Operator, WebSession
from app.auth.security import digest_secret, session_is_active
from app.config import get_settings
from app.control.enums import WorkerStatus
from app.control.models import WorkerRegistration
from app.db import get_session
from app.models import utc_now

SESSION_COOKIE = "agentgate_session"
LOCAL_OPERATOR_ID = UUID("00000000-0000-0000-0000-000000000001")

SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True)
class ClientIdentity:
    token_id: str
    scopes: frozenset[str]

    @property
    def actor(self) -> str:
        return f"client:{self.token_id}"


@dataclass(frozen=True)
class WorkerIdentity:
    worker_id: str
    protocol_version: str
    capabilities: frozenset[str]

    @property
    def actor(self) -> str:
        return f"worker:{self.worker_id}"


def _auth_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": "访问被拒绝"})


def _local_operator() -> Operator:
    return Operator(
        id=LOCAL_OPERATOR_ID,
        password_hash="local-auth-disabled",
        installation_key="local-auth-disabled",
    )


def require_operator(request: Request, session: SessionDep) -> Operator:
    if not get_settings().auth_enabled:
        return _local_operator()
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        if request.headers.get("Authorization"):
            raise _auth_error(403, "operator_required")
        raise _auth_error(401, "authentication_required")
    web_session = session.exec(
        select(WebSession).where(WebSession.token_digest == digest_secret(raw_token))
    ).first()
    if web_session is None or not session_is_active(web_session):
        raise _auth_error(401, "authentication_required")
    operator = session.get(Operator, web_session.operator_id)
    if operator is None:
        raise _auth_error(401, "authentication_required")
    return operator


def require_csrf(request: Request, session: SessionDep) -> Operator:
    if not get_settings().auth_enabled:
        return _local_operator()
    operator = require_operator(request, session)
    raw_session_token = request.cookies.get(SESSION_COOKIE)
    csrf_token = request.headers.get("X-CSRF-Token")
    valid_origin = request.headers.get("Origin") in get_settings().web_origins
    if not valid_origin or not raw_session_token or not csrf_token:
        raise _auth_error(403, "csrf_validation_failed")
    web_session = session.exec(
        select(WebSession).where(WebSession.token_digest == digest_secret(raw_session_token))
    ).first()
    if web_session is None or web_session.csrf_digest != digest_secret(csrf_token):
        raise _auth_error(403, "csrf_validation_failed")
    return operator


def require_client_scope(scope: str) -> Callable[[Request, SessionDep], ClientIdentity]:
    def dependency(request: Request, session: SessionDep) -> ClientIdentity:
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token:
            raise _auth_error(401, "authentication_required")
        client_token = session.exec(
            select(ClientToken).where(ClientToken.token_digest == digest_secret(token))
        ).first()
        if client_token is None or client_token.revoked_at is not None:
            raise _auth_error(401, "authentication_required")
        expires_at = client_token.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at is not None and expires_at <= utc_now():
            raise _auth_error(401, "authentication_required")
        scopes = frozenset(client_token.scopes)
        if scope not in scopes:
            raise _auth_error(403, "insufficient_scope")
        return ClientIdentity(token_id=str(client_token.id), scopes=scopes)

    return dependency


def require_worker(request: Request, session: SessionDep) -> WorkerIdentity:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise _auth_error(401, "authentication_required")
    worker = session.exec(
        select(WorkerRegistration).where(WorkerRegistration.token_digest == digest_secret(token))
    ).first()
    if worker is None or worker.status != WorkerStatus.ACTIVE:
        raise _auth_error(401, "authentication_required")
    return WorkerIdentity(
        worker_id=str(worker.id),
        protocol_version=worker.protocol_version,
        capabilities=frozenset(worker.capabilities),
    )
