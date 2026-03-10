"""
Canonical in-memory job manager for async processing of long-running tasks.

This module provides a simple job queue system using Python's asyncio
for background task execution. Jobs are stored in memory and will be
lost on server restart.

This is the shared canonical implementation used across all V-CAD services.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    """Represents an async job."""
    id: str = Field(..., description="Unique job identifier")
    type: str = Field(..., description="Type of job")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current job status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage (0-100)")
    message: Optional[str] = Field(default=None, description="Status message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary job metadata")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Job result when completed")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    error_code: Optional[int] = Field(default=None, description="HTTP status code for the error")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    model_config = {"protected_namespaces": ()}


class JobManager:
    """
    Manages async jobs with in-memory storage.

    This is a singleton class that maintains a dictionary of jobs
    and handles their lifecycle.
    """

    _instance: Optional["JobManager"] = None
    _jobs: Dict[str, Job] = {}
    _tasks: Dict[str, asyncio.Task] = {}
    _max_jobs: int = 1000
    _job_ttl_hours: int = 24

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs = {}
            cls._instance._tasks = {}
        return cls._instance

    def create_job(self, job_type: str, metadata: Optional[Dict[str, Any]] = None) -> Job:
        """Create a new job and return it."""
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.PENDING,
            message="Job created, waiting to start...",
            metadata=metadata,
        )
        self._jobs[job_id] = job
        self._cleanup_old_jobs()
        logger.info(f"Created job {job_id} of type {job_type}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_code: Optional[int] = None,
    ) -> Optional[Job]:
        """Update a job's status and fields."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
            if status == JobStatus.RUNNING and job.started_at is None:
                job.started_at = datetime.now(timezone.utc)
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.completed_at = datetime.now(timezone.utc)

        if progress is not None:
            job.progress = min(100, max(0, progress))
        if message is not None:
            job.message = message
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        if error_code is not None:
            job.error_code = error_code

        self._jobs[job_id] = job
        return job

    async def run_job(
        self,
        job_id: str,
        task_func: Callable[..., Awaitable[Dict[str, Any]]],
        *args,
        **kwargs,
    ) -> None:
        """Run a job in the background."""
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        try:
            self.update_job(job_id, status=JobStatus.RUNNING, message="Processing...")
            logger.info(f"Starting job {job_id}")
            result = await task_func(*args, **kwargs)
            self.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                message="Completed successfully",
                result=result,
            )
            logger.info(f"Job {job_id} completed successfully")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            error_code = getattr(e, "status_code", None)
            self.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=str(e),
                error_code=error_code,
                message=f"Failed: {str(e)}",
            )

    def start_background_job(
        self,
        job_id: str,
        task_func: Callable[..., Awaitable[Dict[str, Any]]],
        *args,
        **kwargs,
    ) -> None:
        """Start a job as a background task. Returns immediately."""
        task = asyncio.create_task(self.run_job(job_id, task_func, *args, **kwargs))
        self._tasks[job_id] = task

        def cleanup(t):
            self._tasks.pop(job_id, None)

        task.add_done_callback(cleanup)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            self.update_job(
                job_id,
                status=JobStatus.FAILED,
                error="Job cancelled by user",
                message="Cancelled",
            )
            return True
        return False

    def _cleanup_old_jobs(self) -> None:
        """Remove old completed jobs to prevent memory growth."""
        if len(self._jobs) <= self._max_jobs:
            return

        now = datetime.now(timezone.utc)
        jobs_to_remove = []
        for job_id, job in self._jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                if job.completed_at:
                    age_hours = (now - job.completed_at).total_seconds() / 3600
                    if age_hours > self._job_ttl_hours:
                        jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            del self._jobs[job_id]
            logger.debug(f"Cleaned up old job {job_id}")

    def list_jobs(self, job_type: Optional[str] = None, limit: int = 100) -> list[Job]:
        """List jobs, optionally filtered by type."""
        jobs = list(self._jobs.values())
        if job_type:
            jobs = [j for j in jobs if j.type == job_type]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]


# Module-level singleton access
_job_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """Get the global job manager instance."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
