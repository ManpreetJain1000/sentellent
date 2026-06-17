from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.background_job import BackgroundJob
from app.models.user import User
from app.services.google_credentials import GoogleCredentialsService
from app.services.gmail import GmailService
from app.services.jobs import JobService
from app.services.memory import MemoryService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.email_ingestion.ingest_user_inbox")
def ingest_user_inbox(
    job_id: str,
    user_id: str,
    organization_id: str,
    max_results: int = 10,
) -> dict[str, object]:
    settings = get_settings()
    db = get_session_factory()()
    job: BackgroundJob | None = None
    try:
        job = db.get(BackgroundJob, UUID(job_id))
        user = db.get(User, UUID(user_id))
        if job is None or user is None:
            return {"status": "skipped", "reason": "job_or_user_missing"}

        job_service = JobService(db=db, settings=settings)
        job_service.mark_running(job)

        memory_service = MemoryService(db=db, settings=settings)
        credentials = GoogleCredentialsService(settings=settings, db=db)
        gmail = GmailService()

        from app.models.workspace_connection import WorkspaceConnection
        from sqlalchemy import select

        connection = db.scalar(
            select(WorkspaceConnection).where(
                WorkspaceConnection.organization_id == UUID(organization_id),
                WorkspaceConnection.user_id == UUID(user_id),
                WorkspaceConnection.provider == "google",
            )
        )
        if connection is None or not connection.is_connected:
            job_service.mark_failed(job, error_message="Google Workspace is not connected")
            return {"status": "failed", "reason": "not_connected"}

        import asyncio

        async def _run() -> dict[str, object]:
            access_token = await credentials.get_valid_access_token(connection)
            emails = await gmail.list_recent_messages(access_token=access_token, max_results=max_results)
            memories_created = 0
            for email_item in emails:
                extracted = memory_service.extract_memories_from_text(
                    GmailService.memory_source_text(email_item),
                    source_hint="email",
                )
                for memory in extracted:
                    memory_service.create_memory(
                        organization_id=user.organization_id,
                        owner_user_id=user.id,
                        content=memory["content"],
                        memory_type=memory["memory_type"],
                        source_type="email",
                        source_ref=email_item.id,
                    )
                    memories_created += 1
            return {
                "emails_fetched": len(emails),
                "memories_created": memories_created,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        result = asyncio.run(_run())
        job_service.mark_completed(job, result=result)
        return result
    except Exception as exc:
        if job is not None:
            JobService(db=db, settings=settings).mark_failed(job, error_message=str(exc))
        raise
    finally:
        db.close()
