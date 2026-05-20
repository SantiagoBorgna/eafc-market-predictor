from playwright.sync_api import sync_playwright
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
    Abre una instancia oculta de Chromium, entra a Futwiz,
    y captura silenciosamente el Next-Action ID y el Payload exactos.
    Usa caché para no levantar Playwright en cada llamada.
    """
    global _PAYLOAD_CACHE
    if _PAYLOAD_CACHE:
        return _PAYLOAD_CACHE
        
    resultado = {"action_id": None, "payload": None}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        def handle_request(request):
            if request.url == "https://www.futwiz.com/fc26/players" and request.method == "POST":
                action_id = request.headers.get("next-action")
                if action_id:
                    resultado["action_id"] = action_id
                    resultado["payload"] = request.post_data
                    
        page.on("request", handle_request)
        
        try:
            logger.info("Iniciando Playwright para interceptar la firma de Next.js de Futwiz...")
            page.goto("https://www.futwiz.com/fc26/players", wait_until="domcontentloaded", timeout=15000)
            
            # Esperar a que se dispare la primera request de datos
            time.sleep(3)
        except Exception as e:
            logger.error(f"Error en Playwright interceptor: {e}")
        finally:
            browser.close()
            
    if resultado["action_id"] and resultado["payload"]:
        _PAYLOAD_CACHE = resultado
        
    return resultado

if __name__ == "__main__":
    res = resolver_payload_nextjs()
    print("Action ID:", res["action_id"])
    print("Payload:", res["payload"])
