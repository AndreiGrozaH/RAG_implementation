from fastapi import APIRouter, HTTPException, status, Response
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import settings
from qdrant_client.models import Filter, FieldCondition, MatchValue



class VectorStore:
    def __init__(self):
        # Ne conectăm la instanța Qdrant (care va rula din Docker sau local)
        self.client = QdrantClient(url=settings.QDRANT_URL)
        # Dimensiunea vectorilor generați de "text-multilingual-embedding-002" este 768
        self.vector_size = 768

    def _ensure_collection_exists(self, collection_name: str):
        """Verifică dacă un namespace (colecție) există, și îl creează dacă nu."""
        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size, 
                    distance=models.Distance.COSINE
                ),
            )

    def insert_chunks(self, namespace_id: str, chunks: list[dict]):
        """Inserează documente vectorizate în Qdrant (folosit la Ingestie)."""
        self._ensure_collection_exists(namespace_id)
        
        points = []
        for chunk in chunks:
            points.append(
                models.PointStruct(
                    id=chunk["chunk_id"],
                    vector=chunk["vector"], # Aici vor fi cele 768 de numere
                    payload=chunk["payload"] # Aici stocăm textul și metadatele (titlu, articol, etc.)
                )
            )
            
        self.client.upsert(
            collection_name=namespace_id,
            points=points
        )

    def search_chunks(self, namespace_id: str, query_vector: list[float], tenant_id: str, top_k: int = 10, article_filter: str = None) -> list:
        """Caută cele mai relevante paragrafe (folosit la Query)."""
        # Dacă colecția nu există, returnăm listă goală
        if not self.client.collection_exists(namespace_id):
            return []

        # 1. Construim filtrul SAU (should): documentul îmi aparține MIE sau e PUBLIC
        tenant_filter = models.Filter(
            should=[
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=tenant_id)
                ),
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value="public")
                )
            ]
        )

        # 2. Punem filtrul de securitate pe lista de condiții OBLIGATORII (must)
        must_conditions = [tenant_filter]

        # 3. Dacă utilizatorul a dat și un "hint_article_number", îl adăugăm tot ca obligatoriu
        if article_filter:
            must_conditions.append(
                models.FieldCondition(
                    key="article_number",
                    match=models.MatchValue(value=article_filter)
                )
            )

        # 4. Asamblăm filtrul final
        final_query_filter = models.Filter(must=must_conditions)

        # 5. Executăm căutarea reală
        results = self.client.search(
            collection_name=namespace_id,
            query_vector=query_vector,
            query_filter=final_query_filter,
            limit=top_k,
            with_payload=True
        )
        
        return results

    def delete_namespace(self, namespace_id: str) -> bool:
        """Șterge complet o colecție (tot namespace-ul). GDPR Compliance."""
        if self.client.collection_exists(namespace_id):
            self.client.delete_collection(collection_name=namespace_id)
            return True
        return False

    def delete_source(self, namespace_id: str, source_id: str) -> bool:
        """Șterge doar paragrafele care provin dintr-un anumit document (source_id)."""
        if not self.client.collection_exists(namespace_id):
            return False
            
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        self.client.delete(
            collection_name=namespace_id,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_id",
                        match=MatchValue(value=source_id)
                    )
                ]
            )
        )
        return True

    def get_namespace_stats(self, namespace_id: str) -> dict:
        """Returnează statistici despre o colecție."""
        if not self.client.collection_exists(namespace_id):
            return None
            
        collection_info = self.client.get_collection(collection_name=namespace_id)
        
        return {
            "chunk_count": collection_info.points_count,
            "vector_size": collection_info.config.params.vectors.size
        }

# Creăm instanța singleton
vector_store = VectorStore()