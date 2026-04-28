# Open Questions Responses (Section 10) - Lex-Advisor RAG Service

This document clarifies the architectural and technical decisions for the implementation of the RAG microservice, according to the v1.0 specification.

### 1. Embedding Model
**Question:** Which embedding model will you use, and is it swappable per tenant?
**Answer:** We will use the **`text-multilingual-embedding-002`** model provided via Google Vertex AI. This model is optimized for multiple languages, including Romanian, and will be hosted exclusively in the `europe-west3` (Frankfurt) region to ensure data residency and GDPR compliance. The system is designed to support per-tenant model swapping via database-level configurations, although we recommend maintaining a standard model to avoid re-embedding costs.

### 2. Answer Generation (LLM)
**Question:** Which LLM(s) will you use, do you support per-tenant selection, and can they be pinned to a specific version?
**Answer:** Text generation will be powered by **Gemini 2.5 Flash** via Google Vertex AI. We support per-tenant model selection and implement version pinning (e.g., `gemini-2.5-flash:2026-03`) to ensure 100% stability for the client's regression testing.

### 3. Cost Accuracy
**Question:** How accurate is `usage.cost_usd`, and how is reconciliation handled?
**Answer:** The accuracy will be **100%**. The cost is calculated completely deterministically at the request level, multiplying the exact number of tokens (`input_tokens` and `output_tokens` returned by the Vertex AI API) by the selected model's official list price. 

### 4. Optional Endpoints
**Question:** Will you implement the optional `POST /v1/eval` endpoint and webhooks?
**Answer:** **Yes.** We will implement webhook support (asynchronous `POST` with HMAC-SHA256 signature) to optimize the ingestion flow and eliminate the need for costly polling. Additionally, `POST /v1/eval` will be fully implemented to facilitate seamless A/B testing within the Lex-Advisor environment.

### 5. Namespace Deletion (GDPR)
**Question:** Do you support soft-delete with a grace window or only hard-delete for namespaces?
**Answer:** We implement a **soft-delete immediately followed by an asynchronous hard-delete** procedure. Upon calling the `DELETE /v1/namespaces/{id}` endpoint, the namespace instantly becomes inaccessible (logical isolation). An internal background worker will then execute the irreversible physical purging of vectors and metadata within a maximum of 24 hours, strictly adhering to the GDPR SLA.

### 6. Tech Stack
**Question:** What framework/stack and vector store are utilized?
**Answer:** * **Language & Framework:** Python 3.12 with **FastAPI** (ensuring strict type validation and automatic OpenAPI contract generation).
* **Vector Store:** **Qdrant**, running containerized within the internal network. It offers excellent performance for metadata filtering (essential for multi-tenant isolation).
* **RAG Logic:** A *bespoke* architectural implementation (without heavy frameworks like LangChain/LlamaIndex) to maintain minimal latency and absolute control over instructions (e.g., preventing Markdown formatting generation).

### 7. Pricing Model
**Question:** What is the proposed pricing model?
**Answer:** We propose a transparent, hybrid model:
1.  **Platform Fee (Fixed):** A monthly cost covering the core infrastructure (FastAPI compute + Qdrant storage).
2.  **Pass-through Fee (Variable):** Costs associated with LLM inference and embedding generation are billed exactly at the provider's (Google Cloud) list price, mapped 1:1 with the metadata emitted in the `cost_usd` parameter.

### 8. Timeline Commitment
**Question:** What timeline applies for reaching the SLOs and Romanian language quality gates?
**Answer:** We commit to a **3-week** timeline until the cutover phase:
* *Week 1:* Docker infrastructure setup, CI/CD, core routing, and Qdrant integration.
* *Week 2:* Hybrid search implementation to resolve `hint_article_number` parameters, Vertex AI integration, and Romanian-specific Prompt Engineering.
* *Week 3:* Optimizing p95 latency (≤ 4000 ms), running Schemathesis contract testing suites, and validating the 4 quality gates (e.g., ≥ 85% correctness).