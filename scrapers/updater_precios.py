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
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': '7f14f6fdfcf68078a40fee222c3416dc2d522611c3',
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

def actualizar_todos_los_precios():
    """
    Obtiene todos los jugadores de la base de datos, extrae sus precios
    actualizados mediante la API de Futwiz y los guarda en la BD.
    """
    logger.info("🚀 Iniciando actualizador de precios masivo...")
    jugadores = obtener_todos_los_jugadores()
    
    if not jugadores:
        logger.warning("⚠️ No hay jugadores en la base de datos para actualizar.")
        return
        
    logger.info(f"📊 Se encontraron {len(jugadores)} jugadores para actualizar. Esto tomará un tiempo.")
    
    actualizados_count = 0
    errores_count = 0
    
    for jugador in jugadores:
        jugador_id = jugador['id']
        futwiz_id = jugador['futwiz_id']
        slug = jugador['slug']
        nombre = jugador['nombre']
        
        logger.info(f"🔍 Buscando API FC26 para {nombre}...")
        
        nuevo_precio = extraer_precio_futwiz(slug, futwiz_id)
        
        if nuevo_precio > 0:
            if actualizar_precio_jugador(jugador_id, nuevo_precio):
                actualizados_count += 1
                logger.info(f"   ✅ Precio actualizado: {nuevo_precio}")
                
                # Regla inversa: Chequear si originó Panic Selling
                from bot.motor_reglas import detectar_panic_selling
                rating_str = jugador.get('rating', '?')
                alerta = detectar_panic_selling(jugador_id, nuevo_precio, nombre, rating_str)
                if alerta:
                    logger.warning(f"⚠️ Alerta propagada: {nombre} en Panic Selling!")
                    # TODO: Transmitir esta alerta vía Telegram si el bot está corriendo
            else:
                pass
        else:
            logger.info(f"   ❌ No se pudo extraer el precio API de {nombre}.")
            errores_count += 1
            
        time.sleep(1)
        
    logger.info("\n🏁 Actualización de precios finalizada.")
    logger.info(f"✅ Jugadores actualizados con éxito: {actualizados_count}")
    logger.error(f"❌ Errores o precios sin cambios: {errores_count}")

if __name__ == "__main__":
    actualizar_todos_los_precios()

