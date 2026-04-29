import os
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from app.api.v1 import health, query, ingest, namespaces
from app.core.config import settings
from app.core.limiter import limiter
from app.core.auth import verify_api_key
import time
import uuid
import yaml
from pathlib import Path
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=None,
    docs_url="/docs"
)

@app.get("/v1/openapi.json", include_in_schema=False)
async def serve_openapi_json():
    # Calea către fișierul openapi.yaml din rădăcina proiectului
    yaml_path = Path("openapi.yaml")
    
    # Dacă fișierul nu există, returnăm eroare clară
    if not yaml_path.exists():
        return JSONResponse(
            status_code=404, 
            content={"error": "Fisierul openapi.yaml lipseste din radacina proiectului!"}
        )
    
    # Citim fișierul YAML și FastAPI îl va returna automat ca JSON
    with open(yaml_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
        
    return schema

otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
service_name = os.getenv("OTEL_SERVICE_NAME", settings.PROJECT_NAME)

resource = Resource.create({"service.name": service_name})
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Dacă primim o adresă pentru serverul de loguri, trimitem datele.
if otlp_endpoint:
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)


FastAPIInstrumentor.instrument_app(app)

# Configurăm Prometheus
instrumentator = Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=[".*admin.*", "/metrics", "/v1/health"],
)

# Adăugăm metricile standard (latenta, nr cereri)
instrumentator.instrument(app).expose(app, endpoint="/metrics")

app.state.limiter = limiter

@app.middleware("http")
async def add_observability_headers(request: Request, call_next):
    # 1. Pornim cronometrul
    start_time = time.time()
    
    # 2. Preluăm X-Request-ID-ul primit de la client. 
    # (Dacă dintr-un motiv anume lipsește, generăm noi unul temporar)
    request_id = request.headers.get("X-Request-ID", f"req-{uuid.uuid4()}")
    
    # 3. Generăm Trace-ID-ul nostru (X-Vendor-Trace-ID)    
    trace_id = f"trace-{uuid.uuid4().hex[:16]}"
    
    # ==========================================================
    # Executăm ruta cerută 
    response = await call_next(request)
    # ==========================================================
    
    # 4. Calculăm timpul total scurs în milisecunde
    process_time_ms = int((time.time() - start_time) * 1000)
    
    # 5. Lipim Headerele obligatorii pe "plicul" de răspuns
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Vendor-Trace-ID"] = trace_id
    response.headers["X-Vendor-Retrieval-Strategy"] = "hybrid_qdrant_v1"
    
    # Server-Timing este un format standard W3C.
    response.headers["Server-Timing"] = f"total_app;dur={process_time_ms}"
    
    return response

# --- 1. HANDLER PENTRU ERORI HTTP GENERALE ---
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    request_id = request.headers.get("X-Request-ID", "unknown")    
    
    code_map = {
        400: "invalid_request", 401: "unauthorized", 403: "forbidden",
        404: "not_found", 409: "duplicate_job", 413: "payload_too_large",
        415: "unsupported_media_type", 422: "validation_error",
        429: "rate_limited", 500: "internal_error", 502: "upstream_error",
        503: "service_unavailable", 504: "timeout"
    }
    
    error_code = code_map.get(exc.status_code, "unknown_error")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc.detail),
                "request_id": request_id,
                "details": {}
            }
        }
    )

# --- 2. HANDLER PENTRU DATE INVALIDE (Erori Pydantic 422) ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = request.headers.get("X-Request-ID", "unknown")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Datele trimise nu respectă formatul cerut.",
                "request_id": request_id,
                "details": {"errors": exc.errors()}
            }
        }
    )

# --- 3. HANDLER PENTRU RATE LIMITING (429) ---
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    request_id = request.headers.get("X-Request-ID", "unknown")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Ai depășit limita de cereri.",
                "request_id": request_id,
                "details": {}
            }
        }
    )

# Înregistrăm rutele
# 1. Ruta de Health rămâne FĂRĂ parolă (la liber pentru monitorizare/Docker)
app.include_router(health.router, prefix="/v1", tags=["Health"])

# 2. Rutele de business primesc "Paznicul"
app.include_router(
    query.router, 
    prefix="/v1", 
    tags=["Query"], 
    dependencies=[Depends(verify_api_key)]
)

app.include_router(
    ingest.router, 
    prefix="/v1", 
    tags=["Ingest"], 
    dependencies=[Depends(verify_api_key)]
)

app.include_router(
    namespaces.router, 
    prefix="/v1/namespaces", 
    tags=["Namespaces"], 
    dependencies=[Depends(verify_api_key)]
)
