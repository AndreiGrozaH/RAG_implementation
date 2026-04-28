from slowapi import Limiter
from slowapi.util import get_remote_address

# Inițializăm limiter-ul aici, separat de restul aplicației
limiter = Limiter(key_func=get_remote_address)