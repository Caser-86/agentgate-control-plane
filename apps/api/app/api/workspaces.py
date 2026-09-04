from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth.dependencies import require_csrf, require_operator
from app.auth.models import Operator
from app.db import get_session
from app.schemas_workspaces import QuarantineEntryListResponse, WorkspaceCreate, WorkspaceResponse
from app.schemas_workspaces import WorkspacePatch as WorkspacePatchRequest
from app.services.workspaces import WorkspaceError, WorkspacePatch, WorkspaceService

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]
CsrfOperatorDep = Annotated[Operator, Depends(require_csrf)]


def _raise_workspace_error(error: WorkspaceError) -> NoReturn:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


@router.post("", response_model=WorkspaceResponse, status_code=201)
def create_workspace(
    request: WorkspaceCreate, _: CsrfOperatorDep, session: SessionDep
) -> WorkspaceResponse:
    try:
        workspace = WorkspaceService(session).create(
            request.name, request.root_path, request.protected_patterns
        )
        return WorkspaceResponse.model_validate(workspace)
    except WorkspaceError as error:
        _raise_workspace_error(error)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(_: OperatorDep, session: SessionDep) -> list[WorkspaceResponse]:
    return [
        WorkspaceResponse.model_validate(item) for item in WorkspaceService(session).list_all()
    ]


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: UUID,
    request: WorkspacePatchRequest,
    _: CsrfOperatorDep,
    session: SessionDep,
) -> WorkspaceResponse:
    try:
        workspace = WorkspaceService(session).update(
            workspace_id,
            WorkspacePatch(
                name=request.name,
                root_path=request.root_path,
                protected_patterns=request.protected_patterns,
                enabled=request.enabled,
            ),
        )
        return WorkspaceResponse.model_validate(workspace)
    except WorkspaceError as error:
        _raise_workspace_error(error)


@router.get("/{workspace_id}/quarantine", response_model=QuarantineEntryListResponse)
def list_quarantine_entries(
    workspace_id: UUID,
    _: OperatorDep,
    session: SessionDep,
    status: str | None = Query(default=None, max_length=16),
) -> QuarantineEntryListResponse:
    try:
        entries = WorkspaceService(session).list_quarantine_entries(workspace_id, status)
    except WorkspaceError as error:
        _raise_workspace_error(error)
    return QuarantineEntryListResponse(items=entries)
