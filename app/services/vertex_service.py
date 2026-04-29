import vertexai
from vertexai.language_models import TextEmbeddingModel
from vertexai.generative_models import GenerativeModel
from app.core.config import settings

# Inițializăm Vertex AI o singură dată, folosind variabilele din config.py (care respectă europe-west3)
vertexai.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_LOCATION)

class VertexService:
    def __init__(self):        
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
        self.generation_model = GenerativeModel("gemini-2.5-flash")

    def get_embeddings(self, text: str) -> list[float]:
        """Generează vectori pentru text (folosit la ingestie și la căutare)."""
        embeddings = self.embedding_model.get_embeddings([text])
        return embeddings[0].values

    def generate_answer(self, prompt: str) -> dict:
        """Trimite promptul către LLM și extrage răspunsul alături de metadatele de cost."""
        response = self.generation_model.generate_content(prompt)
        
        # Tratăm diferențele dintre versiunile SDK-ului Vertex AI
        if hasattr(response, "usage_metadata"):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
        else:
            # Pentru versiunea stabilă 1.44.0
            input_tokens = response._raw_response.usage_metadata.prompt_token_count
            output_tokens = response._raw_response.usage_metadata.candidates_token_count
        
        # Prețuri reale Gemini 2.5 Flash (cost per 1 milion de tokeni)
        INPUT_COST_PER_M = 0.075
        OUTPUT_COST_PER_M = 0.30
        
        cost_usd = (input_tokens * INPUT_COST_PER_M / 1_000_000) + (output_tokens * OUTPUT_COST_PER_M / 1_000_000)
        
        return {
            "text": response.text,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
                "model_id": "gemini-2.5-flash"
            }
        }

# Creăm o instanță unică (singleton) pe care o vom importa în rutele noastre
vertex_service = VertexService()