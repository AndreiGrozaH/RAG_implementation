from prometheus_client import Counter

COST_COUNTER = Counter(
    "vendor_cost_usd_total", 
    "Total cost in USD for AI provider"
)

TOKEN_COUNTER = Counter(
    "vendor_tokens_total", 
    "Total tokens used",
    ["direction"] # 'input' sau 'output'
)

EXTERNAL_ERRORS = Counter(
    "vendor_external_api_errors_total",
    "Total errors from external dependencies",
    ["dependency", "error_type"]
)