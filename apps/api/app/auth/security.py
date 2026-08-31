import hashlib
import hmac
import os
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.models import BootstrapToken, Operator, WebSession
from app.config import Settings
from app.models import utc_now

password_hasher = PasswordHasher()


def digest_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def bootstrap_file(settings: Settings) -> Path:
    return Path(settings.auth_bootstrap_token_file)


def ensure_bootstrap_token(session: Session, settings: Settings) -> None:
    if session.exec(select(Operator)).first() is not None:
        return
    now = utc_now()
    token = new_secret()
    bootstrap = session.exec(
        select(BootstrapToken)
        .where(BootstrapToken.issuance_key == "bootstrap")
        .with_for_update()
    ).first()
    if bootstrap is not None:
        is_active = (
            bootstrap.consumed_at is None
            and _as_utc(bootstrap.expires_at) > now
        )
        if is_active:
            return
        bootstrap.token_digest = digest_secret(token)
        bootstrap.expires_at = now + timedelta(seconds=settings.auth_bootstrap_ttl_seconds)
        bootstrap.consumed_at = None
        session.add(bootstrap)
        session.commit()
    else:
        session.add(
            BootstrapToken(
                issuance_key="bootstrap",
                token_digest=digest_secret(token),
                expires_at=now + timedelta(seconds=settings.auth_bootstrap_ttl_seconds),
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return
    _publish_bootstrap_token(bootstrap_file(settings), token)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _publish_bootstrap_token(target: Path, token: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".bootstrap-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(token)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def consume_bootstrap_token(session: Session, token: str) -> BootstrapToken | None:
    now = utc_now()
    candidate = session.exec(
        select(BootstrapToken)
        .where(
            cast(Any, BootstrapToken.consumed_at).is_(None),
            cast(Any, BootstrapToken.expires_at) > now,
        )
        .with_for_update()
    ).first()
    if candidate is None or not hmac.compare_digest(candidate.token_digest, digest_secret(token)):
        return None
    candidate.consumed_at = now
    session.add(candidate)
    return candidate


def create_web_session(session: Session, operator: Operator, settings: Settings) -> tuple[str, str]:
    session_token = new_secret()
    csrf_token = new_secret()
    session.add(
        WebSession(
            operator_id=operator.id,
            token_digest=digest_secret(session_token),
            csrf_digest=digest_secret(csrf_token),
            expires_at=utc_now() + timedelta(seconds=settings.auth_session_ttl_seconds),
        )
    )
    return session_token, csrf_token


def session_is_active(web_session: WebSession) -> bool:
    expires_at = web_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return web_session.revoked_at is None and expires_at > utc_now()
