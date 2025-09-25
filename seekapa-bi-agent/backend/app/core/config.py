from pydantic_settings import BaseSettings
import os
from typing import Optional

class Settings(BaseSettings):
    # Azure AI
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_ai_services_endpoint: str = os.getenv("AZURE_AI_SERVICES_ENDPOINT", "")
    azure_openai_api_version: str = "2025-01-01-preview"
    
    # Model Deployments
    gpt5_deployment: str = os.getenv("GPT5_DEPLOYMENT", "gpt-5")
    gpt5_mini_deployment: str = os.getenv("GPT5_MINI_DEPLOYMENT", "gpt-5-mini")
    
    # Power BI
    powerbi_tenant_id: str = os.getenv("POWERBI_TENANT_ID", "")
    powerbi_client_id: str = os.getenv("POWERBI_CLIENT_ID", "")
    powerbi_client_secret: str = os.getenv("POWERBI_CLIENT_SECRET", "")
    powerbi_workspace_id: str = os.getenv("POWERBI_WORKSPACE_ID", "")
    powerbi_dataset_id: str = os.getenv("POWERBI_DATASET_ID", "")
    powerbi_api_url: str = os.getenv("POWERBI_API_URL", "https://api.powerbi.com/v1.0/myorg")
    powerbi_scope: str = os.getenv("POWERBI_SCOPE", "https://analysis.windows.net/powerbi/api/.default")

    # PubNub Configuration for Real-time Messaging
    pubnub_publish_key: str = os.getenv("PUBNUB_PUBLISH_KEY", "")
    pubnub_subscribe_key: str = os.getenv("PUBNUB_SUBSCRIBE_KEY", "")
    pubnub_secret_key: str = os.getenv("PUBNUB_SECRET_KEY", "")
    pubnub_enabled: bool = os.getenv("PUBNUB_ENABLED", "false").lower() == "true"
    
    # Application
    app_name: str = "Seekapa BI Agent"
    app_port: int = 8000
    
    class Config:
        env_file = "../.env"
        case_sensitive = False
        extra = "ignore"  # This allows extra fields without errors

settings = Settings()
