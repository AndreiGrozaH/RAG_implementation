# ==========================================
# STAGE 1: Builder (Instalăm dependențele)
# ==========================================
# Folosim o imagine de bază Python 3.12 fixată prin SHA-256 

FROM python:3.12.3-slim@sha256:7c91350a4d5386050b1e19d71c48011c7fae1208a0d783aa8d73b06cc131d923 AS builder
#FROM python:3.12.3-slim AS builder

# Setăm variabile de mediu pentru a nu genera fișiere .pyc și a nu bloca stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Creăm un mediu virtual pentru a izola instalarea (best practice)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiem doar requirements.txt prima dată pentru a profita de cache-ul Docker
COPY requirements.txt .

# Instalăm dependențele
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# STAGE 2: Runtime (Imaginea finală sub 500MB)
# ==========================================

FROM python:3.12.3-slim@sha256:7c91350a4d5386050b1e19d71c48011c7fae1208a0d783aa8d73b06cc131d923
#FROM python:3.12.3-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Instalăm curl pentru HEALTHCHECK și curățăm cache-ul APT pentru a ține imaginea mică
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Cerință: Creăm un user non-root cu UID 1000 numit 'appuser'
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copiem mediul virtual din Stage 1
COPY --from=builder /opt/venv /opt/venv

# Copiem codul sursă al aplicației noastre
COPY app/ ./app/

# Schimbăm permisiunile pe fișiere către noul utilizator
RUN chown -R appuser:appuser /app

# Trecem pe user-ul non-root
USER appuser

# Cerință: Serviciul ascultă pe portul 8080
EXPOSE 8080

# Cerință: HEALTHCHECK pe GET /v1/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/v1/health || exit 1

# Pornim aplicația cu Uvicorn (gestionează SIGTERM graceful din oficiu)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]