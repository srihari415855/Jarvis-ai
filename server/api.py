"""Minimal FastAPI backend providing health status endpoint for JARVIS Day 1.
"""

from fastapi import FastAPI
from config.settings import settings

app = FastAPI(
    title=settings.JARVIS_NAME,
    version=settings.JARVIS_VERSION,
    description="Local-first Personal AI Assistant API",
)


@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "jarvis",
    }
