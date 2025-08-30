import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Header, status
import jwt

from enhancifai_backend.config import settings

SECRET_KEY = settings.api_key
JWT_SECRET = settings.jwt_secret_key
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 2  # in days

# Using os.path.join for consistency and cross-platform compatibility
STATIC_FILES_DIRECTORY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "files")
STATIC_PAGES_DIRECTORY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pages")

VALID_ENGINES = ["gpt-4-turbo", "gpt-3.5-turbo", "gemini", "gpt-4o", "gpt-4o-mini", "gpt-4.1-nano"]

FILE_AGE_LIMIT = 86400  # seconds (1 day)


class AdminSettings:
    """Class to manage AI settings for the application."""
    settings = {
        'ai_api_key': settings.openai_api_key,
        'ai_engine': 'gpt-4.1-nano',
        'ai_engine_performance_optimization': 'gpt-4.1-mini',
    }

    @classmethod
    def set_ai_settings(cls, engine: str, api_key: str) -> None:
        """
        Set AI settings for the application.

        Args:
            engine (str): The AI engine to use.
            api_key (str): The API key for the AI engine.
        """
        if engine == 'gemini':
            cls.settings['ai_engine'] = engine
            cls.settings['ai_api_key'] = settings.google_ai_studio_api_key
        else:
            cls.settings['ai_engine'] = engine
            cls.settings['ai_api_key'] = api_key

    @classmethod
    def get_ai_engine(cls) -> str:
        """
        Get the current AI engine.

        Returns:
            str: The current AI engine.
        """
        return cls.settings['ai_engine']

    @classmethod
    def get_ai_engine_performance_optimization(cls) -> str:
        """
        Get the current AI engine performance optimization.

        Returns:
            str: The current AI engine performance optimization.
        """
        return cls.settings['ai_engine_performance_optimization']

    @classmethod
    def get_ai_api_key(cls) -> str:
        """
        Get the current AI API key.

        Returns:
            str: The current AI API key.
        """
        return cls.settings['ai_api_key']


def verify_secret_key(x_api_key: str = Header(None, alias="x-api-key")) -> str:
    """
    Verify the provided API key.

    Args:
        x_api_key (str): The API key to verify.

    Raises:
        HTTPException: If the API key is invalid.

    Returns:
        str: The verified API key.
    """
    if x_api_key != SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return x_api_key


def create_jwt_token(data: dict, days: int = JWT_EXPIRATION) -> tuple[str, str]:
    """
    Create a JWT token.

    Args:
        data (dict): The data to include in the token.
        days (int): The number of days the token is valid for.

    Returns:
        tuple[str, str]: The token and its expiration date.
    """
    expiration = datetime.now(timezone.utc) + timedelta(days=days)
    token = jwt.encode({"exp": expiration, **data}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expiration.strftime('%Y-%m-%d %H:%M:%S') + 'Z'


def decode_jwt(token: str) -> dict:
    """
    Decode a JWT token.

    Args:
        token (str): The token to decode.

    Raises:
        HTTPException: If the token is expired or invalid.

    Returns:
        dict: The decoded token data.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your session has expired. Please login again.")

def get_microsite_session_id(token: str = Header(None, alias="x-microsite-session-id")) -> Optional[str]:
    """
    Get the microsite session ID from the request headers.

    Args:
        token (str): The token to extract the microsite session ID from.

    Returns:
        Optional[str]: The microsite session ID.
    """
    if not token:
        return None
    return token

def clean_user_data(data: dict) -> dict:
    """
    Clean user data by removing sensitive information.

    Args:
        data (dict): The user data to clean.

    Returns:
        dict: The cleaned user data.
    """
    data['has_password'] = bool(data['password_hash'])
    for key in ['user_id', 'google_oauth_token', 'password_hash']:
        data.pop(key, None)
    return data


def hash_password(password: str) -> str:
    """
    Hash a password using SHA-256.

    Args:
        password (str): The password to hash.

    Returns:
        str: The hashed password.
    """
    return hashlib.sha256(password.encode()).hexdigest()


def generate_unique_token() -> str:
    """
    Generate a unique token.

    Returns:
        str: The generated token.
    """
    return secrets.token_hex(32)
