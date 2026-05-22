import re
from curl_cffi import requests
from bs4 import BeautifulSoup
import time
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from utils.logger import get_logger
logger = get_logger(__name__)

_PAYLOAD_CACHE = None

def resolver_payload_nextjs():
    """
    Resuelve el Next-Action ID de forma nativa sin Playwright.
    Busca todos los hashes en los chunks JS y los prueba hasta
    encontrar el que devuelve datos válidos.
    """
    global _PAYLOAD_CACHE
    if _PAYLOAD_CACHE:
        return _PAYLOAD_CACHE
        
    resultado = {"action_id": None, "payload": None}
    
    try:
        logger.info("Iniciando resolución nativa de firma Next.js (Sin Playwright)...")
        url = 'https://www.futwiz.com/fc26/players'
        res = requests.get(url, impersonate='chrome120', timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Extraer los scripts JS compilados de Next.js
        scripts = soup.find_all('script', src=True)
        chunks = [s['src'] for s in scripts if '_next/static/chunks' in s['src']]
        
        action_ids = set()
        for chunk in chunks:
            chunk_url = f"https://www.futwiz.com{chunk}" if chunk.startswith('/') else chunk
            try:
                js_res = requests.get(chunk_url, impersonate='chrome120', timeout=5)
                # Next.js Server Actions IDs suelen tener 40 o más caracteres hexadecimales
                matches = re.findall(r'([a-f0-9]{40,})', js_res.text)
                action_ids.update(matches)
            except:
                continue
                
        # Payload estructurado de búsqueda de FC26
        data_str = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":40},"sorting":{"field":"rating","direction":"desc"}}]'
        
        h_base = {
            'accept': 'text/x-component',
            'content-type': 'text/plain;charset=UTF-8'
        }
        
        logger.info(f"Probando {len(action_ids)} Action IDs candidatos...")
        for aid in action_ids:
            h = h_base.copy()
            h['next-action'] = aid
            try:
                res_post = requests.post(url, headers=h, data=data_str, impersonate='chrome120', timeout=5)
                if res_post.status_code == 200 and 'builder_name' in res_post.text:
                    logger.info(f"✅ Action ID validado: {aid}")
                    resultado["action_id"] = aid
                    resultado["payload"] = data_str
                    _PAYLOAD_CACHE = resultado
                    return resultado
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error resolviendo firma nativa: {e}")
        
    logger.error("🛑 No se encontró ningún Action ID válido.")
    return resultado

if __name__ == "__main__":
    res = resolver_payload_nextjs()
    print("Action ID:", res["action_id"])
    print("Payload:", res["payload"])
