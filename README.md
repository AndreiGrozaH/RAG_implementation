# Lex-Advisor RAG API Service

This repository contains the Retrieval-Augmented Generation (RAG) service for the Lex-Advisor platform.

## 1. Prerequisites

To run this service locally or in a staging environment, you need:
* **Docker** installed (v24.0+ recommended)
* **Docker Compose** plugin (v2.20+ recommended)
* Access to a GCP Project with Vertex AI API enabled (for production/staging).

## 2. Running Locally

The service is designed to be run alongside the `lex-advisor` stack. To spin up the RAG API and its isolated Qdrant database locally, run:

```bash
# Ensure the external network exists
docker network create lex-advisor || true

# Start the services in detached mode
docker compose -f docker-compose.service.yml up -d
```
## 3. Environment Variables

The service is strictly configured via environment variables (12-Factor App methodology). No hardcoded credentials exist in the codebase.

| Variable Name | Description | Default / Example | Required |
| :--- | :--- | :--- | :--- |
| `API_AUTH_KEY` | Bearer token for inbound request authentication | `your-secret-key` | **Yes** |
| `QDRANT_URL` | URL to the Qdrant vector database | `http://qdrant:6333` | **Yes** |
| `WEBHOOK_SECRET` | Secret key for HMAC-SHA256 outbound signatures | `your-webhook-secret` | **Yes** |
| `GCP_PROJECT_ID` | Google Cloud Project ID for Vertex AI | `my-gcp-project` | **Yes** |
| `GCP_LOCATION` | Google Cloud compute location | `europe-west3` | No |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP Service Account JSON | `/app/credentials.json` | **Yes** |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry Collector endpoint | `http://otel-collector:4317` | No |
| `OTEL_SERVICE_NAME` | Name of the service for tracing | `lex-advisor-rag` | No |

## 4. Smoke Test Commands

Once the container is running, you can verify its health and observability endpoints using `curl`:

**Check Liveness (Health):**
```bash
curl -f http://localhost:8080/v1/health
curl -s http://localhost:8080/metrics | grep vendor_cost
curl -s http://localhost:8080/v1/openapi.json | grep title
```
---


## 5. Troubleshooting Runbook

If the service is failing, follow these steps to diagnose the issue:

* **Symptom:** `401 Unauthorized` on API calls.
  * **Action:** Verify the `Authorization: Bearer <token>` header matches the `API_AUTH_KEY` injected into the container.

* **Symptom:** `503 Service Unavailable` on `/v1/health`.
  * **Action:** The API cannot reach Qdrant or initialize the Vertex AI client. 
    1. Check if Qdrant is running: `docker ps | grep qdrant`
    2. Check container logs for GCP auth errors: `docker logs <container_id>`

* **Symptom:** Logs are not appearing in the central collector.
  * **Action:** Ensure `OTEL_EXPORTER_OTLP_ENDPOINT` is correctly set and reachable.

* **Symptom:** Ingestion fails with `403 Forbidden` for certain URLs.
  * **Action:** This is a security restriction from the source website (e.g., Wikipedia). 
    1. Verify if the URL is accessible via a standard browser.
    2. For restricted sites, use the **File Upload** method (multipart/form-data) instead of the URL method.