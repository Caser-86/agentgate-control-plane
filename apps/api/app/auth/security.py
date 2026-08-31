import hashlib
import hmac
import secrets
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
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
    active = session.exec(
        select(BootstrapToken).where(
            cast(Any, BootstrapToken.consumed_at).is_(None), BootstrapToken.expires_at > now
        )
    ).first()
    if active is not None:
        return
    token = new_secret()
    session.add(
        BootstrapToken(
            token_digest=digest_secret(token),
            expires_at=now + timedelta(seconds=settings.auth_bootstrap_ttl_seconds),
        )
    )
    session.commit()
    target = bootstrap_file(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(token, encoding="utf-8")


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
