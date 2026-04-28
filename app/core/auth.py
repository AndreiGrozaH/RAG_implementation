from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# HTTPBearer este mecanismul standard din FastAPI pentru tokeni (Bearer)
security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifică dacă token-ul primit în header este identic 
    cu cel din variabila de mediu API_AUTH_KEY.
    """
    if credentials.credentials != settings.API_AUTH_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials