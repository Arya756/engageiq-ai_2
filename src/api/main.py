"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.auth import router as auth_router
from src.api.routes.courses import router as courses_router
from src.api.routes.export import router as export_router
from src.api.routes.preferences import router as preferences_router
from src.api.routes.users import router as users_router
from src.api.websocket import router as websocket_router
from src.config.settings import settings
from src.reports.scheduler import shutdown_scheduler, start_scheduler

app = FastAPI(
    title="EngageIQ AI",
    description="Agentic classroom engagement monitoring system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(courses_router)
app.include_router(preferences_router)
app.include_router(export_router)


@app.on_event("startup")
def startup():
    """Start background scheduler."""
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    """Stop background scheduler."""
    shutdown_scheduler()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
