from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from enhancifai_backend.database.handlers.users import UsersDbCore
import jwt
from typing import Optional
from fastapi import HTTPException, Header, status

SECRET_KEY = os.getenv("API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 2  # in days

# Using os.path.join for consistency and cross-platform compatibility
STATIC_FILES_DIRECTORY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "files")
STATIC_PAGES_DIRECTORY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pages")


VALID_ENGINES = ["gpt-4-turbo", "gpt-3.5-turbo", "gemini", "gpt-4o", "gpt-4o-mini"]

class AdminSettings:
    settings = {
        'ai_api_key': os.getenv('OPENAI_API_KEY'),
        'ai_engine': 'gpt-4o-mini'
    }

    @classmethod
    def set_ai_settings(cls, engine, api_key):
        if engine == 'gemini':
            cls.settings['ai_engine'] = engine
            cls.settings['ai_api_key'] = os.getenv('OPENAI_API_KEY')
        else:
            cls.settings['ai_engine'] = engine
            cls.settings['ai_api_key'] = api_key

    @classmethod
    def get_ai_engine(cls):
        #print(f"AI Engine: {cls.settings['ai_engine']}")
        return cls.settings['ai_engine']
    
    @classmethod
    def get_ai_api_key(cls):
        return cls.settings['ai_api_key']


def verify_secret_key(x_api_key: str = Header(None, alias="x-api-key")):
    if x_api_key != SECRET_KEY:
        print(f"Wrong API key: {x_api_key}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return x_api_key

def create_jwt_token(data: dict, days=JWT_EXPIRATION):
    expiration = datetime.now(timezone.utc) + timedelta(days=days)
    token = jwt.encode({"exp": expiration, **data}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expiration.strftime('%Y-%m-%d %H:%M:%S') + 'Z'

def decode_jwt(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your session has expired. Please login again.")

def get_current_user_id(token: str = Header(None, alias="token")) -> Optional[int]:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    
    jwt_data = decode_jwt(token)
    user_email = jwt_data.get("email", None)
    
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    
    user_details = UsersDbCore.get_user_by_email(user_email)
    return user_details.get("user_id", None)

def get_current_user_id_unverified(token: str = Header(None, alias="token")) -> Optional[int]:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    
    jwt_data = decode_jwt(token)
    user_email = jwt_data.get("email", None)
    
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please login again.")
    
    user_details = UsersDbCore.get_user_by_email_unverified(user_email)
    return user_details.get("user_id", None)

def clean_user_data(data):
    if data['password_hash'] is None or data['password_hash'] == '':
        data['has_password'] = False
    else:
        data['has_password'] = True
    for key in ['user_id', 'google_oauth_token', 'password_hash']:
        del data[key]
    return data

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_unique_token():
    return secrets.token_hex(32)
