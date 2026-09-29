from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from app.database import engine, Base
from app.models.resume_model import *

from app.routers.auth_router import router as auth_router
from app.routers.resume_router import router as resume_router
from app.routers.health_router import router as health_router
from app.routers.metrics_router import router as metrics_router

from app.core.logger import setup_logger
from app.middleware.logging_middleware import log_requests
from app.core.exceptions import register_exception_handlers

setup_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully")
    yield
    logger.info("Application shutting down...")

app = FastAPI(
    title="Asynchronous Resume Scoring API",
    version="1.0",
    lifespan=lifespan
)

register_exception_handlers(app)

app.middleware("http")(log_requests)

app.include_router(auth_router)
app.include_router(resume_router)
app.include_router(health_router)
app.include_router(metrics_router)

@app.get("/", tags=["Root"])
def root():
    return {
        "name": "Asynchronous Resume Scoring API",
        "version": "1.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }