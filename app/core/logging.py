"""
Logging configuration for the service.

Provides get_logger() so every module gets a consistently-named
child logger under the service namespace.
"""

import logging
from typing import Optional

SERVICE_NAME = "ifc-export-service"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance under the service namespace.

    Args:
        name: Optional sub-logger name (e.g. "ifc_builder").
              If not provided, returns the namespace root logger.
    """
    if name:
        return logging.getLogger(f"{SERVICE_NAME}.{name}")
    return logging.getLogger(SERVICE_NAME)
