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

# Add root folder to sys_path to allow absolute imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import insertar_jugador, obtener_jugador_por_futwiz_id, registrar_metadato

def poblar_base_datos(paginas_a_escanear=400, limit_por_pagina=50):
    """
    Scrapea el listado completo usando la API de Next.js de FC26.
    """
    url = "https://www.futwiz.com/fc26/players"
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': '7f14f6fdfcf68078a40fee222c3416dc2d522611c3',
    }
    
    total_insertados = 0
    total_procesados = 0

    for i in range(1, paginas_a_escanear + 1):
        # Escaneamos sin filtros extraños para sacar todos
        data = f'[26,{{"mode":"search","filters":{{}},"search":"$undefined","pagination":{{"page":{i},"limit":{limit_por_pagina}}},"sorting":{{"field":"rating","direction":"desc"}}}}]'
        
        logger.info(f"📡 API FC26 -> Escaneando página {i} ({limit_por_pagina} por pág)")
        try:
            res = fetch_with_retry('post', url, headers=headers, data=data, impersonate="chrome120", timeout=20)
            if res.status_code != 200:
                logger.error(f"Error {res.status_code} al acceder a la API de FC26. Saltando página...")
                continue
                
            match = re.search(r'\[\{.*?"builder_name".*?\}\]', res.text)
            if not match:
                logger.warning("⚠️ No se encontró la lista de jugadores. Puede que hayamos llegado al final.")
                break
                
            jugadores_batch = json.loads(match.group(0))
            if not jugadores_batch:
                logger.warning("⚠️ Lista JSON vacía. Fin de base de datos.")
                break
                
            for g in jugadores_batch:
                total_procesados += 1
                futwiz_id = g.get('line_id') or g.get('pid')
                if not futwiz_id:
                    continue
                    
                nombre = g.get('common_name') or g.get('builder_name') or "Desconocido"
                
                builder = str(g.get('builder_name', '')).lower()
                slug = builder.replace(' ', '-') if builder else 'player'
                rating = g.get('rating', 0)
                
                # Posiciones
                posicion = str(g.get('position', ''))
                alt_pos = [g.get('position2'), g.get('position3'), g.get('position4')]
                alt_pos = [p for p in alt_pos if p and str(p).strip() != '']
                posiciones_alternativas = ", ".join(alt_pos)
                
                equipo_id = str(g.get('club', ''))
                liga_id = str(g.get('league', ''))
                nacion_id = str(g.get('nation', ''))
                
                # Tipo de Carta
                # Futwiz suele tener rare y card_id
                card_num = g.get('card_id')
                rare_num = g.get('rare')
                if card_num:
                    tipo_id = f"c_{card_num}"
                    version_carta = f"Promo {card_num}"
                else:
                    tipo_id = f"r_{rare_num}"
                    version_carta = "Gold Rare" if rare_num == 5 else ("Gold NR" if rare_num == 1 else f"Rare {rare_num}")
                
                # Registramos meta relacional
                registrar_metadato('clubes', equipo_id, "Club Desconocido")
                registrar_metadato('ligas', liga_id, "Liga Desconocida")
                registrar_metadato('nacionalidades', nacion_id, "Nación Desconocida")
                registrar_metadato('tipos_carta', tipo_id, version_carta)
                
                precio_bin = 0
                if g.get('prices') and g['prices'].get('console') and g['prices']['console'].get('bin'):
                    precio_bin = g['prices']['console']['bin']

                if obtener_jugador_por_futwiz_id(futwiz_id):
                    continue
                    
                id_db = insertar_jugador(
                    futwiz_id=futwiz_id,
                    slug=slug,
                    nombre=nombre,
                    rating=rating,
                    version_carta=tipo_id, # Guardamos el ID del tipo de carta
                    liga=liga_id,
                    equipo=equipo_id,
                    nacionalidad=nacion_id,
                    posicion=posicion,
                    posiciones_alternativas=posiciones_alternativas,
                    precio_actual=precio_bin
                )
                if id_db:
                    total_insertados += 1
                    
            logger.info(f"✅ Pagina {i} procesada. Insertados hasta ahora: {total_insertados}")
            time.sleep(1.5) # Respetando límite para 400 páginas
            
        except Exception as e:
            logger.error(f"Excepción fatal en el scrapping: {e}")
            break
            
    logger.info(f"🎉 Población MASIVA finalizada. {total_procesados} leídos. {total_insertados} insertados en BD.")

if __name__ == "__main__":
    logger.info("Iniciando SEED MASIVO para FC26 (100% de la BD).")
    # En producción lo pondremos a 400, si detecta final se corta solo
    poblar_base_datos(paginas_a_escanear=400, limit_por_pagina=50)
