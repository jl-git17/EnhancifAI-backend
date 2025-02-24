from pydantic import BaseSettings, Field
from typing import Optional

class Settings(BaseSettings):
    # Database configuration
    db_host: str = Field(..., env="DB_HOST")
    db_name: str = Field(..., env="DB_NAME")
    db_username: str = Field(..., env="DB_USERNAME")
    db_password: str = Field(..., env="DB_PASSWORD")
    db_schema: str = Field(..., env="DB_SCHEMA")
    
    # Server configuration
    server_host: str = Field("127.0.0.1", env="SERVER_HOST")
    server_port: int = Field(8000, env="SERVER_PORT")
    
    # Stripe configuration
    stripe_plan_id_basic: str = Field(..., env="STRIPE_PLAN_ID_BASIC")
    stripe_plan_id_pro: str = Field(..., env="STRIPE_PLAN_ID_PRO")
    
    # AI and integration settings
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    
    # Admin settings
    admin_user_id: int = Field(..., env="ADMIN_USER_ID")
    
    # Application settings
    app_version: str = Field("1.0.0", env="APP_VERSION")
    
    # Additional configuration
    backend_url: str = Field(..., env="BACKEND_URL")
    api_key: str = Field(..., env="API_KEY")
    sendgrid_api_key: str = Field(..., env="SENDGRID_API_KEY")
    frontend_url: str = Field(..., env="FRONTEND_URL")
    google_ai_studio_api_key: str = Field(..., env="GOOGLE_AI_STUDIO_API_KEY")
    global_max_rows: int = Field(..., env="GLOBAL_MAX_ROWS")
    global_max_prompts: int = Field(..., env="GLOBAL_MAX_PROMPTS")
    admin_username: str = Field(..., env="ADMIN_USERNAME")
    admin_password: str = Field(..., env="ADMIN_PASSWORD")
    google_token_info_auth: str = Field(..., env="GOOGLE_TOKEN_INFO_AUTH")
    google_sheets_redirect_uri: str = Field(..., env="GOOGLE_SHEETS_REDIRECT_URI")
    stripe_secret_key: str = Field(..., env="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(..., env="STRIPE_WEBHOOK_SECRET")
    stripe_subscription_price_id: str = Field(..., env="STRIPE_SUBSCRIPTION_PRICE_ID")
    billing_start: Optional[str] = Field(None, env="BILLING_START")
    
    class Config:
        pass

settings = Settings()
