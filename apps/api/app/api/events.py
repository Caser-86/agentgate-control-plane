from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.auth.dependencies import require_operator
from app.auth.models import Operator
from app.db import get_engine
from app.services.outbox import effective_cursor, stream_outbox_events

router = APIRouter(prefix="/api/v1/events", tags=["events"])
OperatorDep = Annotated[Operator, Depends(require_operator)]


def stream_events(*, cursor: int, resource_id: UUID | None) -> AsyncIterator[str]:
    return stream_outbox_events(
        lambda: Session(get_engine()), cursor=cursor, resource_id=resource_id
    )


def sse_response(*, cursor: int, resource_id: UUID | None) -> StreamingResponse:
    return StreamingResponse(
        stream_events(cursor=cursor, resource_id=resource_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
def events(
    _: OperatorDep,
    after: Annotated[str | None, Query()] = None,
    last_event_id: Annotated[str | None, Header()] = None,
    resource_id: UUID | None = None,
) -> StreamingResponse:
    return sse_response(
        cursor=effective_cursor(last_event_id=last_event_id, after=after), resource_id=resource_id
    )
