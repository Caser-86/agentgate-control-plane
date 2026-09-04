from datetime import timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.dependencies import SESSION_COOKIE, require_csrf, require_operator
from app.auth.models import ClientToken, Operator, WebSession
from app.auth.security import (
    bootstrap_file,
    consume_bootstrap_token,
    create_web_session,
    digest_secret,
    hash_password,
    new_secret,
    verify_password,
)
from app.config import get_settings
from app.db import get_session
from app.models import utc_now
from app.schemas import (
    AuthStatusResponse,
    ClientTokenCreatedResponse,
    CreateClientTokenRequest,
    CsrfResponse,
    LoginRequest,
    SetupRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]
CsrfOperatorDep = Annotated[Operator, Depends(require_csrf)]
ALLOWED_CLIENT_SCOPES = frozenset(
    {"propose:events", "propose:checks", "propose:actions", "worker:enroll"}
)


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": "请求被拒绝"},
    )


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=settings.auth_cookie_secure,
        max_age=settings.auth_session_ttl_seconds,
        path="/",
    )


@router.get("/status", response_model=AuthStatusResponse)
def status(request: Request, session: SessionDep) -> AuthStatusResponse:
    if not get_settings().auth_enabled:
        return AuthStatusResponse(authenticated=True, setup_required=False)
    setup_required = session.exec(select(Operator)).first() is None
    try:
        require_operator(request, session)
    except HTTPException:
        return AuthStatusResponse(authenticated=False, setup_required=setup_required)
    return AuthStatusResponse(authenticated=True, setup_required=setup_required)


@router.post("/setup", response_model=AuthStatusResponse, status_code=201)
def setup(request: SetupRequest, response: Response, session: SessionDep) -> AuthStatusResponse:
    if session.exec(select(Operator)).first() is not None:
        raise _error(409, "setup_already_completed")
    consumed = consume_bootstrap_token(session, request.bootstrap_token)
    if consumed is None:
        raise _error(403, "invalid_or_expired_bootstrap_token")
    operator = Operator(password_hash=hash_password(request.password))
    session.add(operator)
    try:
        session.flush()
        session_token, _ = create_web_session(session, operator, get_settings())
        session.commit()
    except IntegrityError:
        session.rollback()
        raise _error(409, "setup_already_completed") from None
    Path(bootstrap_file(get_settings())).unlink(missing_ok=True)
    _set_session_cookie(response, session_token)
    return AuthStatusResponse(authenticated=True, setup_required=False)


@router.post("/login", response_model=AuthStatusResponse)
def login(request: LoginRequest, response: Response, session: SessionDep) -> AuthStatusResponse:
    operator = session.exec(select(Operator)).first()
    if operator is None or not verify_password(operator.password_hash, request.password):
        raise _error(401, "invalid_credentials")
    session_token, _ = create_web_session(session, operator, get_settings())
    session.commit()
    _set_session_cookie(response, session_token)
    return AuthStatusResponse(authenticated=True, setup_required=False)


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, _: CsrfOperatorDep, session: SessionDep
) -> Response:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        web_session = session.exec(
            select(WebSession).where(WebSession.token_digest == digest_secret(raw_token))
        ).first()
        if web_session is not None:
            web_session.revoked_at = utc_now()
            session.add(web_session)
            session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, _: OperatorDep, session: SessionDep) -> CsrfResponse:
    if not get_settings().auth_enabled:
        return CsrfResponse(csrf_token="local-auth-disabled")
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise _error(401, "authentication_required")
    web_session = session.exec(
        select(WebSession).where(WebSession.token_digest == digest_secret(raw_token))
    ).first()
    if web_session is None:
        raise _error(401, "authentication_required")
    csrf_token = new_secret()
    web_session.csrf_digest = digest_secret(csrf_token)
    session.add(web_session)
    session.commit()
    return CsrfResponse(csrf_token=csrf_token)


@router.post("/tokens", response_model=ClientTokenCreatedResponse, status_code=201)
def create_client_token(
    request: CreateClientTokenRequest, _: CsrfOperatorDep, session: SessionDep
) -> ClientTokenCreatedResponse:
    if not request.scopes.issubset(ALLOWED_CLIENT_SCOPES):
        raise _error(403, "invalid_token_scope")
    if request.rotate_token_id is not None:
        replaced = session.get(ClientToken, request.rotate_token_id)
        if replaced is None or replaced.revoked_at is not None:
            raise _error(404, "token_not_found")
        replaced.revoked_at = utc_now()
        session.add(replaced)
    raw_token = new_secret()
    expires_at = (
        utc_now() + timedelta(seconds=request.expires_in_seconds)
        if request.expires_in_seconds is not None
        else None
    )
    created = ClientToken(
        name=request.name,
        token_digest=digest_secret(raw_token),
        scopes=sorted(request.scopes),
        expires_at=expires_at,
    )
    session.add(created)
    session.commit()
    session.refresh(created)
    return ClientTokenCreatedResponse(
        id=created.id,
        name=created.name,
        scopes=created.scopes,
        expires_at=created.expires_at,
        token=raw_token,
    )


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_client_token(token_id: UUID, _: CsrfOperatorDep, session: SessionDep) -> Response:
    client_token = session.get(ClientToken, token_id)
    if client_token is None or client_token.revoked_at is not None:
        raise _error(404, "token_not_found")
    client_token.revoked_at = utc_now()
    session.add(client_token)
    session.commit()
    return Response(status_code=204)
