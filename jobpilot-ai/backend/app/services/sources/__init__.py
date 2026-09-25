"""Importing this package registers every adapter in REGISTRY."""
from . import api_sources, web_sources  # noqa: F401
from .base import REGISTRY, PoliteClient, SearchQuery, SourceAdapter, SourceError, register  # noqa: F401
