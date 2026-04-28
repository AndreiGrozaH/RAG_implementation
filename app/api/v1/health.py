import time
from fastapi import APIRouter, Response
from typing import Dict, Any

# Importăm serviciile noastre reale
from app.db.qdrant_client import vector_store
from app.services.vertex_service import vertex_service

router = APIRouter()

START_TIME = time.time()

@router.get("/health", summary="Liveness Health Check")
def health_check(response: Response) -> Dict[str, Any]:
    uptime = int(time.time() - START_TIME)
    
    # 1. Ping Qdrant (Acceptabil pentru că e o conexiune internă în rețeaua Docker)
    try:
        # Verificăm dacă clientul e viu apelând colecțiile
        vector_store.client.get_collections()
        vector_store_status = "ok"
    except Exception:
        vector_store_status = "down"

    # 2. Status Vertex AI (FĂRĂ APEL DE REȚEA)
    try:
        # Verificăm doar dacă serviciul a fost inițializat corect în memorie.
        # Nu trimitem text la Google ca să nu generăm costuri și rate-limits la fiecare 30 secunde.
        if vertex_service is not None:
            llm_status = "ok"
        else:
            llm_status = "down"
    except Exception:
        llm_status = "down"

    # 3. Object Store (Momentan folosim tempfile local)
    object_store_status = "ok"
    
    # Determinăm statusul global
    overall_status = "ok"
    if vector_store_status == "down" or llm_status == "down":
        overall_status = "down"
        # Returnăm 503 ca Docker să știe că aplicația e stricată și trebuie restartată
        response.status_code = 503 
    elif vector_store_status == "degraded" or llm_status == "degraded":
        overall_status = "degraded"
        
    return {
        "status": overall_status,
        "version": "1.0.0",
        "uptime_seconds": uptime,
        "dependencies": {
            "vector_store": vector_store_status,
            "llm": llm_status,
            "object_store": object_store_status
        }
    }