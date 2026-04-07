import time
import logging
from utils.logger import get_logger
logger = get_logger(__name__)
from curl_cffi import requests

def fetch_with_retry(method, url, max_retries=3, backoff_seconds=5, **kwargs):
    """
    Realiza una petición HTTP con reintentos automáticos si recibe errores 429 o >= 500.
    """
    for attempt in range(max_retries):
        try:
            if method.lower() == 'get':
                res = requests.get(url, **kwargs)
            else:
                res = requests.post(url, **kwargs)

            if res.status_code == 429 or res.status_code >= 500:
                logging.warning(f"Error {res.status_code} al acceder a {url}. Reintentando en {backoff_seconds}s... ({attempt + 1}/{max_retries})")
                time.sleep(backoff_seconds)
                continue
                
            return res
        except requests.RequestsError as e:
            logging.warning(f"Excepción de conexión ({e}) al acceder a {url}. Reintentando en {backoff_seconds}s... ({attempt + 1}/{max_retries})")
            time.sleep(backoff_seconds)
        except Exception as e:
            # Otra excepción general
            logging.error(f"Excepción inesperada en fetch_with_retry: {e}")
            raise
            
    # Si fallan todos los intentos, hacemos uno más para dejar que se dispare o retorne el último response
    if method.lower() == 'get':
        return requests.get(url, **kwargs)
    else:
        return requests.post(url, **kwargs)
