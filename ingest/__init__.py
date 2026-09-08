"""Ingestion framework: fetch -> validate -> stage (pending) -> commit (approved)."""
from . import pipeline
from . import sources

__all__ = ["pipeline", "sources"]