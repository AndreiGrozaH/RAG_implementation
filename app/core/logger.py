import logging
import sys
from pythonjsonlogger import jsonlogger
from opentelemetry import trace

def get_logger(name: str):
    logger = logging.getLogger(name)
    
    # Dacă are deja handlere, nu le duplicăm
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Creăm un handler care scrie în consolă (stdout)
    log_handler = logging.StreamHandler(sys.stdout)

    # Definim formatul cerut: timestamp, nivel, mesaj, și cel mai important: ID-urile!
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    
    # Adăugăm un filtru care injectează Trace ID și Span ID în fiecare log
    class OpenTelemetryFilter(logging.Filter):
        def filter(self, record):
            span = trace.get_current_span()
            span_context = span.get_span_context()
            
            if span_context.is_valid:
                record.trace_id = format(span_context.trace_id, "032x")
                record.span_id = format(span_context.span_id, "016x")
            else:
                record.trace_id = None
                record.span_id = None
                
            # Pentru X-Request-ID vom folosi o variabilă de context (o vom seta în middleware)
            record.request_id = getattr(record, 'request_id', 'unknown')
            return True

    logger.addFilter(OpenTelemetryFilter())
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    
    # Nu propagăm logurile mai sus pentru a evita dublarea lor în consolă
    logger.propagate = False
    return logger