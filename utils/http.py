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
        
import re
_NEXT_ACTION_CACHE = None

def get_next_action():
    """
    Extrae dinámicamente el ID next-action del sitio web de Futwiz para prevenir caídas
    cuando Futwiz hace deploys y cambia sus hashes de Next.js.
    """
    global _NEXT_ACTION_CACHE
    if _NEXT_ACTION_CACHE:
        return _NEXT_ACTION_CACHE
        
    try:
        res = fetch_with_retry('get', "https://www.futwiz.com/fc26/players", impersonate="chrome120")
        if res.status_code == 200:
            # Buscamos un hash hexadecimal de 40 caracteres, típicamente el action ID de next.js.
            matches = re.findall(r'[a-f0-9]{40}', res.text)
            if matches:
                # El action id actual de Futwiz siempre está expuesto en su DOM.
                _NEXT_ACTION_CACHE = matches[0]
                return _NEXT_ACTION_CACHE
    except Exception as e:
        logger.error(f"Error extrayendo next-action dinámico: {e}")
        
    # Fallback seguro (último conocido histórico)
    return "7f14f6fdfcf68078a40fee222c3416dc2d522611c3"

