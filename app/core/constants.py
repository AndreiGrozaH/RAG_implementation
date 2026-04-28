COMMON_RESPONSES = {
    400: {"description": "Bad Request - Format invalid"},
    401: {"description": "Unauthorized - Invalid API Key"},
    403: {"description": "Forbidden - Acces interzis"},
    404: {"description": "Not Found - Resursa nu a fost găsită"},
    409: {"description": "Duplicate Job - Conflict de Idempotency-Key"},
    429: {"description": "Rate Limit Exceeded - Prea multe cereri"},
    500: {"description": "Internal Server Error"},
    503: {"description": "Service Unavailable - Dependențe indisponibile"}
}