"""
FastAPI application entry point for ACL Patient Assistant.

This is the main application file that sets up:
- FastAPI app instance
- Middleware (CORS, logging, exception handling)
- Route registration
- Startup/shutdown events
- APScheduler for automated jobs
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routes import router
from db.database import engine, Base
from scheduler import start_scheduler, stop_scheduler


# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    
    # Ensure database tables exist
    # (In production, use Alembic migrations instead)
    Base.metadata.create_all(bind=engine)
    logger.info("database_initialized")
    
    # Start APScheduler
    start_scheduler()
    logger.info("scheduler_initialized")
    
    yield
    
    # Shutdown
    stop_scheduler()
    logger.info("scheduler_stopped")
    logger.info("application_shutdown")


# Create FastAPI application instance
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered SMS assistant for ACL surgery patients",
    lifespan=lifespan,
)


# Add CORS middleware (allow all origins for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unhandled errors.
    Logs the error and returns a 500 response.
    """
    logger.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
        }
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all incoming requests and their responses.
    """
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else None,
    )
    
    response = await call_next(request)
    
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    
    return response


# Register routes
app.include_router(router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
