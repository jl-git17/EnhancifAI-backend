from pydantic import BaseModel, validator
from enum import Enum
from datetime import datetime, timedelta, timezone
import pytz


class Engine(str, Enum):
    GPT4_O = "gpt-4o"
    GPT4_TURBO_PREVIEW = "gpt-4-turbo-preview"
    GPT3_5_TURBO = "gpt-3.5-turbo"
    GEMINI = "gemini"

class AdminAISettings(BaseModel):
    ai_engine: Engine
    api_key: str
    
class RunLogsRequest(BaseModel):

    start_date: datetime = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end_date: datetime = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)