"""Backward-compatibility shim — canonical implementation is in app.core.job_manager."""

from app.core.job_manager import Job, JobManager, JobStatus, get_job_manager

__all__ = ["Job", "JobManager", "JobStatus", "get_job_manager"]
