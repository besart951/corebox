"""FastAPI CLI entry point. Configure .env before importing this module."""

from .main import create_app

app = create_app()
