"""Ingestion framework: fetch -> validate -> stage (pending) -> commit (approved)."""

from . import pipeline, sources

__all__ = ["pipeline", "sources"]
