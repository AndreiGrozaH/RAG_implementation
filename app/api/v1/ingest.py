import httpx
import tempfile
import os
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any
from langchain_core.documents import Document
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Request, Header, Depends
from pydantic import BaseModel
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.vertex_service import vertex_service
from app.db.qdrant_client import vector_store
from app.core.limiter import limiter  
from app.core.security import get_api_key
from .namespaces import JOBS_DB
from app.core.metrics import COST_COUNTER, TOKEN_COUNTER
from app.core.constants import COMMON_RESPONSES
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/ingest", tags=["Ingest"])

# --- 1. BAZA DE DATE PENTRU JOB-URI ---
JOBS_DB: Dict[str, dict] = {}

# --- 2. SCHEME PYDANTIC ---
class IngestRequest(BaseModel):
    namespace_id: str
    source_id: str
    source_type: str = "url" # "url" sau "file"
    url: Optional[str] = None
    callback_url: Optional[str] = None
    mime_type_hint: str = "application/pdf"
    metadata: Optional[Dict[str, Any]] = {}
    
class JobResponse(BaseModel):
    job_id: str
    status: str
    submitted_at: str
    estimated_completion_at: Optional[str] = None

# --- FUNCȚII UTILITARE ---
async def send_webhook_notification(callback_url: Optional[str], payload: dict):
    if not callback_url:
        return
    body_str = json.dumps(payload)
    signature = hmac.new(key=settings.WEBHOOK_SECRET.encode(), msg=body_str.encode(), digestmod=hashlib.sha256).hexdigest()
    async with httpx.AsyncClient() as client:
        try:
            headers = {"X-Vendor-Signature": f"sha256={signature}", "Content-Type": "application/json"}
            await client.post(callback_url, data=body_str, headers=headers, timeout=10.0)
        except Exception as e:
            logger.error(f"Eroare la trimiterea webhook-ului: {e}")

def load_and_extract_text(file_path: str, mime_type: str) -> list[Document]:
    """Funcție universală care citește PDF, HTML, TXT și Markdown cu fallback inteligent."""
    
    # Citim primele câteva caractere pentru a detecta manual tipul dacă hint-ul e greșit
    with open(file_path, "rb") as f:
        header = f.read(500).decode('utf-8', errors='ignore').strip()
    
    # FORȚĂM HTML dacă vedem tag-uri, chiar dacă hint-ul zice PDF
    is_actually_html = "<!DOC" in header.upper() or "<HTML" in header.upper()
    
    if mime_type == "application/pdf" and not is_actually_html:
        try:
            loader = PyPDFLoader(file_path)
            return loader.load()
        except Exception as e:
            logger.error(f"Eroare PyPDFLoader: {e}. Încercăm fallback la text.")
            is_actually_html = True # Dacă moare PDF loader-ul, încercăm să-l citim ca text/html
        
    if mime_type == "text/html" or is_actually_html:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
        text = soup.get_text(separator="\n", strip=True)
        return [Document(page_content=text, metadata={"page": 1})]
        
    elif mime_type in ["text/plain", "text/markdown"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return [Document(page_content=text, metadata={"page": 1})]
        
    else:
        # Ultimul efort: îl citim ca text chior dacă nu știm ce e
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return [Document(page_content=text, metadata={"page": 1})]

# --- 3. MUNCITORUL DIN FUNDAL ---
async def process_document_worker(job_id: str, payload: IngestRequest, tenant_id: str, file_bytes: bytes = None):
    tmp_path = None
    try:
        JOBS_DB[job_id]["status"] = "fetching"
        JOBS_DB[job_id]["progress"] = {"stage": "fetching", "percent": 10}
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name
            if payload.source_type == "file" and file_bytes:
                tmp_file.write(file_bytes)
            elif payload.source_type == "url" and payload.url:
                headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.google.com/"
                }
                async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
                    response = await client.get(payload.url, headers=headers, timeout=20.0)
                    response.raise_for_status()
                    tmp_file.write(response.content)
            else:
                raise ValueError("Sursa invalidă.")

        JOBS_DB[job_id]["status"] = "extracting"
        JOBS_DB[job_id]["progress"] = {"stage": "extracting", "percent": 30}
        
        # Aici apelăm funcția noastră nouă cu verificare de tip
        documents = load_and_extract_text(tmp_path, payload.mime_type_hint)
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\nArticolul", "\nArt.", "\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_documents(documents)

        JOBS_DB[job_id]["status"] = "embedding"
        JOBS_DB[job_id]["progress"] = {"stage": "embedding", "percent": 50}
        
        qdrant_chunks = []
        total_chunks = len(chunks)
        
        if total_chunks == 0:
            raise ValueError("Documentul nu conține text.")
        
        for i, chunk in enumerate(chunks):
            content = chunk.page_content
            vector = vertex_service.get_embeddings(content)

            estimated_tokens = len(content) // 4
            COST_COUNTER.inc((estimated_tokens / 1000) * 0.00002)
            TOKEN_COUNTER.labels(direction="input").inc(estimated_tokens)
            
            qdrant_chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "vector": vector,
                "payload": {
                    "content": content,
                    "tenant_id": tenant_id,
                    "source_id": payload.source_id,
                    "page_number": chunk.metadata.get("page", 0),
                    "original_chunk_id": f"{payload.source_id}_chunk_{i}"
                }
            })
            
            if i % 5 == 0: 
                JOBS_DB[job_id]["progress"]["percent"] = 50 + int((i / total_chunks) * 45)

        vector_store.insert_chunks(payload.namespace_id, qdrant_chunks)      
        
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        JOBS_DB[job_id].update({
            "status": "done",
            "progress": {"stage": "done", "percent": 100, "chunks_created": total_chunks},
            "completed_at": now_str
        })

        await send_webhook_notification(payload.callback_url, {"event": "ingest.completed", "job_id": job_id, "status": "done", "chunks_created": total_chunks})

    except Exception as e:
        logger.error(f"Eroare procesare job {job_id}: {str(e)}")
        JOBS_DB[job_id].update({"status": "failed", "error": {"code": "processing_error", "message": str(e)}})
        await send_webhook_notification(payload.callback_url, {"event": "ingest.failed", "job_id": job_id, "status": "failed"})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- 4. RUTA POST /v1/ingest ---
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse, responses=COMMON_RESPONSES)
@limiter.limit("50/minute")
async def ingest_document(
    request: Request,
    background_tasks: BackgroundTasks,
    x_request_id: str = Header(..., alias="X-Request-ID"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    api_key: str = Depends(get_api_key)
):
    content_type = request.headers.get("content-type", "")
    file_bytes = None

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            payload_str = form.get("payload")
            file_upload = form.get("file")
            if not payload_str or not file_upload:
                raise HTTPException(status_code=400, detail="Missing payload or file")
            payload_dict = json.loads(payload_str)
            payload = IngestRequest(**payload_dict)
            file_bytes = await file_upload.read()
        elif "application/json" in content_type:
            payload_dict = await request.json()
            payload = IngestRequest(**payload_dict)
        else:
            raise HTTPException(status_code=415, detail="Unsupported Media Type")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = f"j_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    JOBS_DB[job_id] = {
        "job_id": job_id, "tenant_id": x_tenant_id, "namespace_id": payload.namespace_id,
        "source_id": payload.source_id, "status": "queued",
        "progress": {"stage": "queued", "percent": 0}, "submitted_at": now, "completed_at": None, "error": None
    }
    background_tasks.add_task(process_document_worker, job_id, payload, x_tenant_id, file_bytes)
    return JobResponse(job_id=job_id, status="queued", submitted_at=now)

@router.get("/{job_id}", responses=COMMON_RESPONSES)
@limiter.limit("50/minute")
async def get_job_status(request: Request, job_id: str):
    job = JOBS_DB.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return job