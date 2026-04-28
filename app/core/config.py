import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Lex-Advisor RAG Service"
    
    # Am șters default-ul! Acum este OBLIGATORIU să fie în fișierul .env
    API_AUTH_KEY: str 
    
    GCP_PROJECT_ID: str = "rag-implementation-494307"
    GCP_LOCATION: str = "europe-west3" 
    
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    
    # Păstrăm default-ul de localhost, dar în Docker îl vom suprascrie din .env
    QDRANT_URL: str = "http://localhost:6333" 
    RAG_API_URL: str = "http://localhost:8080/api"
    WEBHOOK_SECRET: str = "webhook_secret_key"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
    

settings = Settings()

if settings.GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS