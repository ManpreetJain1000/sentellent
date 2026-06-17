from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUser, DbSession, SettingsDep
from app.core.rate_limit import enforce_ingest_rate_limit
from app.schemas.api import BackgroundJobResponse, IngestWorkspaceRequest
from app.services.jobs import JobService

router = APIRouter(tags=["workspace"])


@router.post("/workspace/ingest", status_code=status.HTTP_202_ACCEPTED)
def enqueue_workspace_ingest(
    request: Request,
    payload: IngestWorkspaceRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> JSONResponse:
    enforce_ingest_rate_limit(request, settings)
    job_service = JobService(db=db, settings=settings)
    job = job_service.enqueue_email_ingest(user=current_user, max_results=payload.max_results)
    body = BackgroundJobResponse.model_validate(job)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump(mode="json"))


@router.get("/jobs/{job_id}", response_model=BackgroundJobResponse)
def get_job_status(
    job_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> BackgroundJobResponse:
    job_service = JobService(db=db, settings=settings)
    job = job_service.get_job_for_user(job_id=job_id, user=current_user)
    return BackgroundJobResponse.model_validate(job)
