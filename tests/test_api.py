from fastapi.testclient import TestClient
from app.main import app
import pytest

client = TestClient(app)

def test_health_check():
    """Verifică dacă endpoint-ul de sănătate e online."""
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_query_no_auth():
    """Verifică dacă query-ul e blocat fără token."""
    response = client.post("/v1/query", json={"question": "ce este un aport?"})
    # Acum că avem HTTPBearer, va întoarce 403 dacă lipsește header-ul
    assert response.status_code == 403 

def test_query_wrong_auth():
    """Verifică dacă query-ul e blocat cu token greșit."""
    headers = {"Authorization": "Bearer parola_gresita"}
    response = client.post("/v1/query", json={"question": "test"}, headers=headers)
    assert response.status_code == 401