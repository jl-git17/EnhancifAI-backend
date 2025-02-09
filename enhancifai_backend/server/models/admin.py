"""Module defining models for admin settings."""

# Standard library imports
from datetime import datetime, timedelta, timezone
from enum import Enum

# Third-party imports
from pydantic import BaseModel, Field


class Engine(str, Enum):
    """Enumeration of available AI engines."""
    GPT4_O = "gpt-4o"
    GPT4_O_MINI = "gpt-4o-mini"
    GPT3_5_TURBO = "gpt-3.5-turbo"
    GEMINI = "gemini"


class AdminAISettings(BaseModel):
    """Model for admin AI settings."""
    ai_engine: Engine
    api_key: str


class RunLogsRequest(BaseModel):
    """Request model for run logs with default datetime range."""
    start_date: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    )
    end_date: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
