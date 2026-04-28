from fastapi import APIRouter, HTTPException, status, Response
import uuid
from datetime import datetime, timezone

from app.core.constants import COMMON_RESPONSES
# Importăm și inițializăm clientul Qdrant 
from app.db.qdrant_client import VectorStore
vector_store = VectorStore()
JOBS_DB = {} 

router = APIRouter()

# 4.4 Ștergerea unei surse dintr-un namespace
@router.delete("/{namespace_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, responses=COMMON_RESPONSES)
async def delete_single_source(namespace_id: str, source_id: str):
    success = vector_store.delete_source(namespace_id, source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Namespace not found")    
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# 4.5 Ștergerea totală a unui namespace (GDPR)
@router.delete("/{namespace_id}", status_code=status.HTTP_202_ACCEPTED, responses=COMMON_RESPONSES)
async def delete_namespace(namespace_id: str):
    success = vector_store.delete_namespace(namespace_id)
    if not success:
        raise HTTPException(status_code=404, detail="Namespace not found")    
    
    return {
        "job_id": f"del_{uuid.uuid4().hex[:12]}",
        "status": "queued",
        "sla": "24h"
    }

# 4.6 Statistici despre Namespace
@router.get("/{namespace_id}/stats", responses=COMMON_RESPONSES)
async def get_namespace_stats(namespace_id: str):
    stats = vector_store.get_namespace_stats(namespace_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Namespace not found")
        
    return {
        "namespace_id": namespace_id,
        "chunk_count": stats["chunk_count"],
        "source_count": 1, # Un workaround temporar, necesită agregare complexă mai târziu
        "total_tokens_indexed": stats["chunk_count"] * 150, # Estimare (150 tokeni / chunk)
        "last_ingested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "embedding_model": "vertex-text-embedding",
        "embedding_dim": stats["vector_size"]
    }