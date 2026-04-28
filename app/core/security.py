from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# Această clasă "HTTPBearer" comunică perfect cu lăcătușul din Swagger
security_scheme = HTTPBearer()

async def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security_scheme)):
    """
    HTTPBearer extrage automat token-ul și se asigură că formatul este corect.
    """
    token = credentials.credentials # Aici se extrage direct cheia, fără cuvântul Bearer
    
    if token != settings.API_AUTH_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autentificare incorect",
        )
    
    return token