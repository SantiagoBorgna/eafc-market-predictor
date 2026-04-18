import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import sys
import os
import time
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import insertar_jugador, _get_connection, obtener_jugador_por_futwiz_id
from functools import lru_cache
from curl_cffi import requests

@lru_cache(maxsize=200)
def jugador_ya_existe_en_bd(futwiz_id):
    """Verifica en SQLite si la carta existe y guarda el resultado en caché."""
    return obtener_jugador_por_futwiz_id(futwiz_id) is not None

def parsear_novedades_futwiz():
    """
    Busca los top 150 jugadores más recientes/altos usando la API de Next.js.
    Dado que las nuevas cartas promo suelen entrar en el top rating, esto es altamente eficiente.
    """
    from utils.http import fetch_with_retry, get_next_action
    
    url = "https://www.futwiz.com/fc26/players"
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': get_next_action(),
    }
    
    jugadores_extraidos = []
    
    try:
        # Explorar 3 páginas (150 cartas)
        for page in range(1, 4):
            data = f'[26,{{"mode":"search","filters":{{}},"search":"$undefined","pagination":{{"page":{page},"limit":50}},"sorting":{{"field":"rating","direction":"desc"}}}}]'
            
            res = requests.post(url, headers=headers, data=data, impersonate="chrome120", timeout=15)
            if res.status_code != 200:
                continue
                
            match = re.search(r'\[\{.*?"builder_name".*?\}\]', res.text)
            if not match:
                continue
                
            jugadores_batch = json.loads(match.group(0))
            for g in jugadores_batch:
                id_jugador = g.get('line_id') or g.get('pid')
                if not id_jugador: continue
                
                # Check mem caché
                if jugador_ya_existe_en_bd(id_jugador):
                    continue
                    
                nombre = g.get('common_name') or g.get('builder_name') or "Desconocido"
                builder = str(g.get('builder_name', '')).lower()
                slug = builder.replace(' ', '-') if builder else 'player'
                rating = g.get('rating', 0)
                posicion = str(g.get('position', ''))
                
                equipo_id = str(g.get('club', ''))
                liga_id = str(g.get('league', ''))
                nacion_id = str(g.get('nation', ''))
                
                version_carta = "Promo/Special"
                
                jugadores_extraidos.append({
                    'futwiz_id': id_jugador,
                    'slug': slug,
                    'nombre': nombre,
                    'rating': rating,
                    'posicion': posicion,
                    'equipo': equipo_id,
                    'liga': liga_id,
                    'nacionalidad': nacion_id,
                    'version_carta': version_carta
                })
            
            time.sleep(1) # antiban
    except Exception as e:
        logger.error(f"Error extrayendo novedades API: {e}")
        
    return jugadores_extraidos

def chequear_cartas_nuevas():
    """
    Revisa la API de FC26 y agrega a la BD los jugadores que aún no existen.
    Devuelve un reporte (string) con las novedades encontradas.
    """
    logger.info("🔍 Revisando API masiva en busca de cartas sin registrar...")
    
    jugadores_recientes = parsear_novedades_futwiz()
    
    if not jugadores_recientes:
        return None
        
    conn = _get_connection()
    cursor = conn.cursor()
    
    nuevos_agregados = []
    
    for j in jugadores_recientes:
        futwiz_id = j['futwiz_id']
        try:
            id_insertado = insertar_jugador(
                futwiz_id=j['futwiz_id'],
                slug=j['slug'],
                nombre=j['nombre'],
                rating=j['rating'],
                version_carta=j.get('version_carta', 'Special'),
                liga=j.get('liga', ''),
                equipo=j.get('equipo', ''),
                nacionalidad=j.get('nacionalidad', ''),
                posicion=j['posicion']
            )
            
            if id_insertado:
                nuevos_agregados.append(j['nombre'])
                logger.info(f"✨ ¡NUEVA CARTA REGISTRADA! {j['nombre']} ({j['rating']})")
        except Exception as e:
            logger.error(f"Error procesando id {futwiz_id}: {e}")
            
    conn.close()
    
    if nuevos_agregados:
        nombres_juntos = ", ".join(nuevos_agregados[:10])
        if len(nuevos_agregados) > 10:
            nombres_juntos += f" y {len(nuevos_agregados)-10} más..."
            
        logger.info(f"📦 Se agregaron {len(nuevos_agregados)} nuevas cartas: {nombres_juntos}")
        
    return None

if __name__ == '__main__':
    logger.info(chequear_cartas_nuevas())
