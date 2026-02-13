"""
Job Manager for async IFC export tasks.

Provides an in-memory job queue for handling long-running IFC
conversion requests. Jobs are tracked with status, progress, and results.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    """Job model for tracking async tasks."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str = Field(..., description="Job type (e.g., 'ifc-convert', 'ifc-convert-dsl')")
    status: JobStatus = Field(default=JobStatus.PENDING)
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    message: str = Field(default="Job created", description="Status message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Job metadata")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Job result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


class JobManager:
    """
    In-memory job manager for async IFC export tasks.

    For production clusters, consider Redis or a database for persistence.
    """

    def __init__(self, max_jobs: int = 1000, job_ttl_hours: int = 24):
        self._jobs: Dict[str, Job] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._max_jobs = max_jobs
        self._job_ttl_hours = job_ttl_hours
        logger.info(f"JobManager initialized (max_jobs={max_jobs}, ttl={job_ttl_hours}h)")

    def create_job(self, job_type: str, metadata: Optional[Dict[str, Any]] = None) -> Job:
        job = Job(type=job_type, status=JobStatus.PENDING, metadata=metadata)
        self._jobs[job.id] = job
        self._cleanup_old_jobs()
        logger.info(f"Created job {job.id} of type '{job_type}'")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found for update")
            return None

        if status is not None:
            job.status = status
            if status == JobStatus.RUNNING and job.started_at is None:
                job.started_at = datetime.utcnow()
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.completed_at = datetime.utcnow()

        if progress is not None:
            job.progress = max(0, min(100, progress))
        if message is not None:
            job.message = message
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error

        logger.debug(f"Updated job {job_id}: status={job.status}, progress={job.progress}")
        return job

    async def run_job(
        self,
        job_id: str,
        task_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        try:
            self.update_job(
                job_id,
                status=JobStatus.RUNNING,
                message="Processing IFC export request",
            )

            logger.info(f"Starting job {job_id} execution")
            result = await task_func(*args, **kwargs)

            self.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                message="IFC export completed successfully",
                result=result,
            )
            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
            self.update_job(
                job_id,
                status=JobStatus.FAILED,
                message="IFC export failed",
                error=error_msg,
            )

        finally:
            if job_id in self._tasks:
                del self._tasks[job_id]

    def start_background_job(
        self,
        job_id: str,
        task_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        task = asyncio.create_task(self.run_job(job_id, task_func, *args, **kwargs))
        self._tasks[job_id] = task
        logger.debug(f"Started background task for job {job_id}")

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status != JobStatus.RUNNING:
            logger.warning(f"Job {job_id} is not running (status={job.status})")
            return False

        task = self._tasks.get(job_id)
        if task:
            task.cancel()
            del self._tasks[job_id]

        self.update_job(
            job_id,
            status=JobStatus.FAILED,
            message="Job cancelled by user",
            error="Job was cancelled",
        )
        logger.info(f"Cancelled job {job_id}")
        return True

    def list_jobs(
        self,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Job]:
        jobs = list(self._jobs.values())

        if job_type:
            jobs = [j for j in jobs if j.type == job_type]

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def _cleanup_old_jobs(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return

        cutoff_time = datetime.utcnow() - timedelta(hours=self._job_ttl_hours)
        old_jobs = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
            and job.completed_at
            and job.completed_at < cutoff_time
        ]

        for job_id in old_jobs:
            del self._jobs[job_id]
            if job_id in self._tasks:
                del self._tasks[job_id]

        if old_jobs:
            logger.debug(f"Cleaned up {len(old_jobs)} old jobs")


# Singleton instance
_job_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
