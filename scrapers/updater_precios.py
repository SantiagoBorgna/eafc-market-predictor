import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import sys
import os
import time
import json
import re
from curl_cffi import requests
from utils.http import fetch_with_retry

# Agregar el directorio raíz al path para importar el módulo de base de datos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.crud import obtener_todos_los_jugadores, actualizar_precio_jugador

def extraer_precio_futwiz(slug, futwiz_id):
    """
    Usa la API de Next.js de Futwiz para buscar un jugador y extraer su precio.
    """
    url = "https://www.futwiz.com/fc26/players"
    from utils.http import get_next_action
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': get_next_action(),
    }
    
    # Buscar por slug asegurando límite pequeño
    data = f'[26,{{"mode":"search","filters":{{}},"search":"{slug}","pagination":{{"page":1,"limit":5}},"sorting":{{"field":"rating","direction":"desc"}}}}]'
    
    try:
        res = fetch_with_retry('post', url, headers=headers, data=data, impersonate="chrome120", timeout=15)
        if res.status_code != 200:
            return 0
            
        match = re.search(r'\[\{.*?"builder_name".*?\}\]', res.text)
        if not match:
            return 0
            
        jugadores_batch = json.loads(match.group(0))
        for g in jugadores_batch:
            id_jugador = g.get('line_id') or g.get('pid')
            if str(id_jugador) == str(futwiz_id):
                if g.get('prices') and g['prices'].get('console') and g['prices']['console'].get('bin'):
                    return int(g['prices']['console']['bin'])
    except Exception as e:
        logger.error(f"Excepción obteniendo precio para {slug}: {e}")
        
    return 0

def actualizar_todos_los_precios(paginas=60):
    """
    Obtiene los precios en lotes de a 50 mediante la paginación de Futwiz
    y actualiza la base de datos masivamente sin hacer Requests 1x1.
    """
    logger.info(f"🚀 Iniciando actualizador masivo por lotes (Top {paginas * 50} cartas)...")
    jugadores_bd = obtener_todos_los_jugadores()
    
    if not jugadores_bd:
        logger.warning("⚠️ No hay jugadores en la BD para actualizar.")
        return
        
    # Crear diccionario para búsquedas rápidas en memoria O(1)
    mapa_jugadores = {str(j['futwiz_id']): j for j in jugadores_bd}
    
    url = "https://www.futwiz.com/fc26/players"
    from utils.http import get_next_action
    
    action_id = get_next_action()
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': action_id,
    }
    
    actualizados_count = 0
    errores_count = 0
    fallos_consecutivos = 0
    
    for page in range(1, paginas + 1):
        logger.info(f"📄 Descargando página {page}/{paginas} de Futwiz...")
        data = f'[26,{{"mode":"search","filters":{{}},"search":"$undefined","pagination":{{"page":{page},"limit":50}},"sorting":{{"field":"rating","direction":"desc"}}}}]'
        
        try:
            res = fetch_with_retry('post', url, headers=headers, data=data, impersonate="chrome120", timeout=15)
            if res.status_code != 200:
                logger.warning(f"❌ Error HTTP {res.status_code} al bajar la página {page}. (Posible bloqueo Ddos)")
                fallos_consecutivos += 1
            else:
                match = re.search(r'\[\{.*?"builder_name".*?\}\]', res.text)
                if not match:
                    logger.warning(f"❌ No se encontró el bloque JSON en la página {page}.")
                    fallos_consecutivos += 1
                else:
                    fallos_consecutivos = 0  # Reestablece el bloqueo
                    jugadores_batch = json.loads(match.group(0))
                    
                    for g in jugadores_batch:
                        futwiz_id = str(g.get('line_id') or g.get('pid'))
                        
                        # Si esta carta existe en nuestra base de datos local
                        if futwiz_id in mapa_jugadores:
                            if g.get('prices') and g['prices'].get('console') and g['prices']['console'].get('bin'):
                                nuevo_precio = int(g['prices']['console']['bin'])
                                
                                if nuevo_precio > 0:
                                    jugador = mapa_jugadores[futwiz_id]
                                    db_id = jugador['id']
                                    nombre = jugador['nombre']
                                    
                                    if actualizar_precio_jugador(db_id, nuevo_precio):
                                        actualizados_count += 1
                                        logger.info(f"   ✅ {nombre}: {nuevo_precio} 🪙")
                                        
                                        # Verificar Panic Selling
                                        from bot.motor_reglas import detectar_panic_selling
                                        rating_str = jugador.get('rating', '?')
                                        alerta = detectar_panic_selling(db_id, nuevo_precio, nombre, rating_str)
                                        
                                        if alerta:
                                            logger.warning(f"⚠️ Alerta propagada: {nombre} en Panic Selling!")
                                            try:
                                                token = os.getenv("TELEGRAM_TOKEN")
                                                admin_id = os.getenv("ADMIN_ID")
                                                vip_group_id = os.getenv("VIP_GROUP_ID")
                                                if token:
                                                    msg = f"📉 **¡PANIC SELLING DETECTADO!** 📉\n\nEl precio de **{nombre}** ({rating_str}) bajó de forma repentina a **{nuevo_precio}** 🪙."
                                                    url_tg = f"https://api.telegram.org/bot{token}/sendMessage"
                                                    if admin_id:
                                                        requests.post(url_tg, json={"chat_id": admin_id, "text": msg, "parse_mode": "Markdown"}, impersonate="chrome120")
                                                    if vip_group_id:
                                                        requests.post(url_tg, json={"chat_id": vip_group_id, "text": msg, "parse_mode": "Markdown"}, impersonate="chrome120")
                                            except Exception as e:
                                                logger.error(f"Error enviando Panic Selling a Telegram: {e}")
                                else:
                                    errores_count += 1
                            else:
                                errores_count += 1
                        
        except Exception as e:
            logger.error(f"Excepción en la página {page}: {e}")
            fallos_consecutivos += 1
            
        if fallos_consecutivos >= 3:
            logger.error("🛑 Múltiples fallos de paginación consecutivos (3). Posible bloqueo de Cloudflare o ban de IP. Deteniendo actualización masiva.")
            break
            
        # Throttle vital entre páginas
        time.sleep(2)
        
    logger.info("\n🏁 Actualización de precios masiva finalizada.")
    logger.info(f"✅ Jugadores actualizados con éxito: {actualizados_count}")
    logger.error(f"❌ Errores / Sin precio: {errores_count}")

if __name__ == "__main__":
    actualizar_todos_los_precios(paginas=10) # Test para CLI

