import time
from fastapi import APIRouter, Header, Depends, Request
from app.models.schemas import EvalRequest, EvalResponse, EvalMetrics
from app.models.schemas import QueryRequest, QueryResponse, Citation, Chunk, Usage
from app.services.vertex_service import vertex_service
from app.db.qdrant_client import vector_store
from app.core.security import get_api_key
from app.core.limiter import limiter
from app.core.metrics import COST_COUNTER, TOKEN_COUNTER
from app.core.constants import COMMON_RESPONSES

router = APIRouter()

@router.post("/query", response_model=QueryResponse, responses=COMMON_RESPONSES)
@limiter.limit("50/minute")
def query_documents(
    request: Request, # CRITIC: 'request' trebuie să fie mereu primul pentru limiter!
    query_data: QueryRequest,
    x_request_id: str = Header(..., alias="X-Request-ID"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    api_key: str = Depends(get_api_key)
):
    start_time = time.time()

    # =====================================================================
    # 1. RETRIEVAL (Căutare reală în Qdrant)
    # =====================================================================
    query_vector = vertex_service.get_embeddings(query_data.question)
    
    search_results = vector_store.search_chunks(
        namespace_id=query_data.namespaces[0],
        query_vector=query_vector,
        tenant_id=x_tenant_id,
        top_k=query_data.top_k,
        article_filter=query_data.hint_article_number
    )

    # Dacă baza de date nu a găsit nimic, returnăm contractul "Empty-result"
    if not search_results:
        return QueryResponse(
            request_id=x_request_id,
            answer=None,
            citations=[],
            usage=Usage(input_tokens=0, output_tokens=0, cost_usd=0.0, model_id="gemini-2.5-flash"),
            latency_ms=int((time.time() - start_time) * 1000),
            model_version="gemini-2.5-flash:2026-03",
            retrieval_strategy="hybrid_qdrant_v1",
            confidence=0.0
        )

    # Construim lista de bucăți de text extrase
    retrieved_chunks = []
    context_text = ""
    
    for i, hit in enumerate(search_results):
        payload = hit.payload
        chunk = Chunk(
            chunk_id=payload.get("original_chunk_id", str(hit.id)),
            content=payload.get("content", ""),
            article_number=payload.get("article_number"),
            section_title=payload.get("section_title"),
            source_id=payload.get("source_id", "unknown"),
            namespace_id=query_data.namespaces[0],
            score=hit.score
        )
        retrieved_chunks.append(chunk)
        marker = f"[{i+1}]"
        context_text += f"Sursa {marker} (Articol {chunk.article_number}): {chunk.content}\n\n"

    # Calculăm nivelul de încredere (media scorurilor din DB)
    confidence = sum(c.score for c in retrieved_chunks) / len(retrieved_chunks)

    # =====================================================================
    # 2. CONTRACT OPTIMIZATION: "include_answer = False"
    # =====================================================================
    # Dacă clientul a cerut doar căutare (fără AI), dăm return AICI!
    if not query_data.include_answer:
        return QueryResponse(
            request_id=x_request_id,
            answer=None,
            citations=[Citation(marker=f"[{i+1}]", chunk=c) for i, c in enumerate(retrieved_chunks)],
            usage=Usage(input_tokens=0, output_tokens=0, cost_usd=0.0, model_id="none"),
            latency_ms=int((time.time() - start_time) * 1000),
            model_version="retrieval-only:2026-03",
            retrieval_strategy="hybrid_qdrant_v1",
            confidence=round(confidence, 4)
        )

    # =====================================================================
    # 3. CONSTRUIREA PROMPTULUI ȘI APELUL AI
    # =====================================================================
    history_text = ""
    if query_data.conversation_history:
        for msg in query_data.conversation_history:
            role_name = "Utilizator" if msg.role == "user" else "Asistent"
            history_text += f"{role_name}: {msg.content}\n"

    prompt = f"""Ești un asistent legal pentru platforma Lex-Advisor.
    Răspunde la întrebarea utilizatorului folosind EXCLUSIV informațiile din contextul de mai jos.
    Dacă informația nu se găsește în context, trebuie să răspunzi exact cu cuvântul "NULL".
    IMPORTANT: Răspunsul tău trebuie să fie text simplu (plain text). NU folosi sub nicio formă formatare Markdown (fără steluțe **, fără _, etc).
    Când folosești o informație dintr-o sursă, adaugă marker-ul sursei la sfârșitul propoziției (ex: [1], [2]).

    Istoricul conversației:
    {history_text}
    
    Context:
    {context_text}

    Întrebare: {query_data.question}"""

    llm_result = vertex_service.generate_answer(prompt)
    
    # ==========================================
    # --- AICI ACTUALIZĂM METRICILE PROMETHEUS ---
    # ==========================================
    COST_COUNTER.inc(llm_result["usage"]["cost_usd"])
    TOKEN_COUNTER.labels(direction="input").inc(llm_result["usage"]["input_tokens"])
    TOKEN_COUNTER.labels(direction="output").inc(llm_result["usage"]["output_tokens"])

    # =====================================================================
    # 4. PROCESAREA RĂSPUNSULUI ȘI CITAȚIILOR
    # =====================================================================
    raw_answer = llm_result["text"].strip()
    citations = []
    
    if raw_answer == "NULL":
        final_answer = None
    else:
        final_answer = raw_answer
        
        cite_inline = True
        if query_data.style_hints and query_data.style_hints.cite_inline is False:
            cite_inline = False
            
        if cite_inline:
            for i, chunk in enumerate(retrieved_chunks):
                marker = f"[{i+1}]"
                if marker in final_answer:
                    citations.append(Citation(marker=marker, chunk=chunk))

    # =====================================================================
    # 5. RĂSPUNSUL CĂTRE CLIENT
    # =====================================================================
    return QueryResponse(
        request_id=x_request_id,
        answer=final_answer,
        citations=citations,
        usage=Usage(**llm_result["usage"]),
        latency_ms=int((time.time() - start_time) * 1000),
        model_version=llm_result["usage"]["model_id"] + ":2026-03",
        retrieval_strategy="hybrid_qdrant_v1",
        confidence=round(confidence, 4)
    )

@router.post("/eval", response_model=EvalResponse, responses=COMMON_RESPONSES)
@limiter.limit("50/minute")
def eval_documents(
    request: Request, 
    eval_data: EvalRequest,
    x_request_id: str = Header(..., alias="X-Request-ID"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    api_key: str = Depends(get_api_key)
):
    start_time = time.time()

    # 1. RETRIEVAL 
    query_vector = vertex_service.get_embeddings(eval_data.question)
    search_results = vector_store.search_chunks(
        namespace_id=eval_data.namespaces[0],
        query_vector=query_vector,
        tenant_id=x_tenant_id,
        top_k=eval_data.top_k,
        article_filter=eval_data.hint_article_number
    )

    if not search_results:
        # Dacă nu găsim nimic, precizia și rata de potrivire sunt 0
        return EvalResponse(
            request_id=x_request_id,
            answer=None,
            citations=[],
            usage=Usage(input_tokens=0, output_tokens=0, cost_usd=0.0, model_id="none"),
            latency_ms=int((time.time() - start_time) * 1000),
            model_version="vertex-ai-v1",
            retrieval_strategy="hybrid_qdrant_v1",
            confidence=0.0,
            eval=EvalMetrics(citation_precision_at_k=0.0, keyword_match_rate=0.0)
        )

    retrieved_chunks = []
    context_text = ""
    for i, hit in enumerate(search_results):
        payload = hit.payload
        chunk = Chunk(
            chunk_id=payload.get("original_chunk_id", str(hit.id)),
            content=payload.get("content", ""),
            article_number=payload.get("article_number"),
            source_id=payload.get("source_id", "unknown"),
            namespace_id=eval_data.namespaces[0],
            score=hit.score
        )
        retrieved_chunks.append(chunk)
        context_text += f"Sursa [{i+1}]: {chunk.content}\n\n"
    
    # 2. GENERARE AI
    prompt = f"""Ești un asistent legal pentru platforma Lex-Advisor.
    Răspunde la întrebarea utilizatorului folosind EXCLUSIV informațiile din contextul de mai jos.
    Dacă informația nu se găsește în context, trebuie să răspunzi exact cu cuvântul "NULL".
    IMPORTANT: Răspunsul tău trebuie să fie text simplu (plain text). NU folosi sub nicio formă formatare Markdown.
    Când folosești o informație dintr-o sursă, adaugă marker-ul sursei la sfârșitul propoziției (ex: [1]).

    Context:
    {context_text}

    Întrebare: {eval_data.question}"""
    
    llm_result = vertex_service.generate_answer(prompt)

    # ==========================================
    # --- AICI ACTUALIZĂM METRICILE PROMETHEUS ---
    # ==========================================
    COST_COUNTER.inc(llm_result["usage"]["cost_usd"])
    TOKEN_COUNTER.labels(direction="input").inc(llm_result["usage"]["input_tokens"])
    TOKEN_COUNTER.labels(direction="output").inc(llm_result["usage"]["output_tokens"])

    raw_answer = llm_result["text"].strip()
    
    final_answer = raw_answer if raw_answer != "NULL" else None
    
    # 3. CONSTRUIRE CITAȚII
    citations = []
    if final_answer:
        for i, chunk in enumerate(retrieved_chunks):
            if f"[{i+1}]" in final_answer:
                citations.append(Citation(marker=f"[{i+1}]", chunk=chunk))

    # =====================================================================
    # 4. LOGICA DE EVALUARE (Matematica din spatele /eval)
    # =====================================================================
    
    # Calculăm citation_precision_at_k (Câte din cele așteptate am găsit în Qdrant?)
    returned_chunk_ids = [c.chunk_id for c in retrieved_chunks]
    if eval_data.expected_citations and returned_chunk_ids:        
        matched_citations = set(returned_chunk_ids).intersection(set(eval_data.expected_citations))
        precision = len(matched_citations) / len(returned_chunk_ids)
    else:
        precision = 0.0

    # Calculăm keyword_match_rate (Câte cuvinte cheie a folosit AI-ul în răspuns?)
    if eval_data.expected_answer_keywords and final_answer:
        answer_lower = final_answer.lower()
        matched_keywords = [kw for kw in eval_data.expected_answer_keywords if kw.lower() in answer_lower]
        keyword_rate = len(matched_keywords) / len(eval_data.expected_answer_keywords)
    else:
        keyword_rate = 0.0

    confidence = sum(c.score for c in retrieved_chunks) / len(retrieved_chunks)

    # 5. RĂSPUNSUL FINAL CU EVAL BLOCK
    return EvalResponse(
        request_id=x_request_id,
        answer=final_answer,
        citations=citations,
        usage=Usage(**llm_result["usage"]),
        latency_ms=int((time.time() - start_time) * 1000),
        model_version=llm_result["usage"]["model_id"] + ":2026-03",
        retrieval_strategy="hybrid_qdrant_v1",
        confidence=round(confidence, 4),
        eval=EvalMetrics(
            citation_precision_at_k=round(precision, 2),
            keyword_match_rate=round(keyword_rate, 2)
        )
    )