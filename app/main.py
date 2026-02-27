import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.health import router as health_router
from app.api.v1.router import router as v1_router
from app.api.jobs_router import router as jobs_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure ASGI logging middleware (avoids BaseHTTPMiddleware CORS issues)
# ---------------------------------------------------------------------------

class LoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.time()
        method = scope.get("method", "")
        path = scope.get("path", "")
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.time() - start) * 1000
        if path not in ("/health", "/"):
            logger.info("%s %s %s %.0fms", method, path, status_code, duration_ms)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "%s v%s starting on port %s",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.PORT,
    )
    yield
    logger.info("%s shutting down", settings.APP_NAME)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health & root endpoints
app.include_router(health_router)

# Sync v1 endpoints (direct conversion)
app.include_router(v1_router, prefix="/api/v1")

# Async job-based endpoints
app.include_router(jobs_router)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Wrap with logging middleware (outermost layer)
app = LoggingMiddleware(app)
