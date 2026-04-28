from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- Modele pentru componentele de bază ---

class Chunk(BaseModel):
    chunk_id: str
    content: str
    article_number: Optional[str] = None
    section_title: Optional[str] = None
    point_number: Optional[str] = None
    page_number: Optional[int] = None
    source_id: str
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    namespace_id: str
    score: float
    metadata: Optional[Dict[str, Any]] = None

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_id: str

class Citation(BaseModel):
    marker: str
    chunk: Chunk

# --- Modele pentru Request (Ce primim de la client) ---

class Message(BaseModel):
    role: str
    content: str

class StyleHints(BaseModel):
    answer_max_chars: int = 2000
    cite_inline: bool = True
    tone: str = "formal"

class ChatMessage(BaseModel):
    role: str      # Poate fi "user" sau "assistant"
    content: str

class QueryRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    language: str = "ro"
    namespaces: List[str] = Field(..., min_length=1, max_length=10)
    top_k: int = Field(10, le=50)
    hint_article_number: Optional[str] = None
    conversation_history: Optional[List[ChatMessage]] = Field(default=[], max_length=15)
    rerank: bool = True
    include_answer: bool = True    
    style_hints: Optional[StyleHints] = None

# --- Modele pentru Response (Ce trimitem înapoi clientului) ---

class QueryResponse(BaseModel):
    request_id: str
    answer: Optional[str]
    citations: List[Citation]
    usage: Usage
    latency_ms: int
    model_version: str
    retrieval_strategy: Optional[str] = "hybrid_qdrant_v1"
    confidence: float

class EvalRequest(QueryRequest):
    # Moștenește tot din QueryRequest și adaugă:
    expected_citations: List[str] = []
    expected_answer_keywords: List[str] = []

class EvalMetrics(BaseModel):
    citation_precision_at_k: float
    keyword_match_rate: float

class EvalResponse(QueryResponse):
    # Moștenește tot din QueryResponse și adaugă:
    eval: EvalMetrics