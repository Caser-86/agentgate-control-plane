from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models import utc_now


class Operator(SQLModel, table=True):
    __tablename__ = "operators"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    password_hash: str
    installation_key: str = Field(default="operator", unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class WebSession(SQLModel, table=True):
    __tablename__ = "web_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    operator_id: UUID = Field(foreign_key="operators.id", index=True)
    token_digest: str = Field(unique=True, index=True)
    csrf_digest: str
    expires_at: datetime = Field(index=True)
    revoked_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ClientToken(SQLModel, table=True):
    __tablename__ = "client_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    token_digest: str = Field(unique=True, index=True)
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    expires_at: datetime | None = Field(default=None, index=True)
    revoked_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class BootstrapToken(SQLModel, table=True):
    __tablename__ = "bootstrap_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    issuance_key: str = Field(default="bootstrap", unique=True, index=True)
    token_digest: str = Field(unique=True, index=True)
    expires_at: datetime = Field(index=True)
    consumed_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
