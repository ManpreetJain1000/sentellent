from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.models.background_job import BackgroundJob
from app.models.user import User


class JobService:
    JOB_EMAIL_INGEST = "email_ingest"

    def __init__(self, *, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def get_job_for_user(self, *, job_id: UUID, user: User) -> BackgroundJob:
        job = self.db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.id == job_id,
                BackgroundJob.organization_id == user.organization_id,
                BackgroundJob.user_id == user.id,
            )
        )
        if job is None:
            raise NotFoundError("Background job not found")
        return job

    def find_active_by_idempotency(self, idempotency_key: str) -> BackgroundJob | None:
        return self.db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.idempotency_key == idempotency_key,
                BackgroundJob.status.in_(("pending", "running")),
            )
        )

    def enqueue_email_ingest(self, *, user: User, max_results: int = 10) -> BackgroundJob:
        idempotency_key = f"email_ingest:{user.id}:{date.today().isoformat()}"
        existing = self.find_active_by_idempotency(idempotency_key)
        if existing is not None:
            return existing

        job = BackgroundJob(
            organization_id=user.organization_id,
            user_id=user.id,
            job_type=self.JOB_EMAIL_INGEST,
            status="pending",
            idempotency_key=idempotency_key,
            payload={"max_results": max_results},
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            # Another request enqueued the same idempotent job concurrently.
            self.db.rollback()
            existing_job = self.db.scalar(
                select(BackgroundJob).where(BackgroundJob.idempotency_key == idempotency_key)
            )
            if existing_job is not None:
                return existing_job
            raise
        self.db.refresh(job)

        from app.workers.tasks.email_ingestion import ingest_user_inbox

        ingest_user_inbox.delay(str(job.id), str(user.id), str(user.organization_id), max_results)
        return job

    def mark_running(self, job: BackgroundJob) -> None:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

    def mark_completed(self, job: BackgroundJob, *, result: dict[str, object]) -> None:
        job.status = "completed"
        job.result = result
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()

    def mark_failed(self, job: BackgroundJob, *, error_message: str) -> None:
        job.status = "failed"
        job.error_message = error_message
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
