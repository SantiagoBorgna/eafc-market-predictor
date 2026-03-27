import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import insertar_jugador, _get_connection, obtener_jugador_por_futwiz_id
from scrapers.seed_db import parsear_pagina_futwiz
from functools import lru_cache

@lru_cache(maxsize=50)
def jugador_ya_existe_en_bd(futwiz_id):
    """Verifica en SQLite si la carta existe y guarda el resultado en caché."""
    return obtener_jugador_por_futwiz_id(futwiz_id) is not None

def parsear_novedades_futwiz(url):
    """
    Parseador especial para la página 'latest' ya que tiene una estructura CSS distinta 
    a la página de búsqueda general.
    """
    jugadores_extraidos = []
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup
        import re
        
        response = requests.get(url, impersonate="chrome110", timeout=15)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=re.compile(r'^/fc25/player/'))
        
        # Usar un set para evitar duplicados en la misma página (Futwiz pone la carta 2 veces a veces)
        procesados = set()
        
        for a in links:
            href = a.get('href')
            if href in procesados: continue
            procesados.add(href)
            
            partes = href.split('/')
            if len(partes) < 4: continue
                
            futwiz_id = int(partes[-1])
            slug = partes[-2]
            
            # Verificar si existe en BD preguntando a la caché en memoria 
            if jugador_ya_existe_en_bd(futwiz_id):
                print(f"  ⏭️ Saltando novedad (ya existe en BD): {slug}")
                continue
            
            # Navegar a la página individual para obtener todos los datos
            url_jugador = f"https://www.futwiz.com{href}"
            print(f"  ↳ Novedad, obteniendo detalles de: {slug}")
            
            try:
                time.sleep(1) # pausa anti-ban
                res_indiv = requests.get(url_jugador, impersonate="chrome110", timeout=15)
                soup_indiv = BeautifulSoup(res_indiv.text, 'html.parser')
                
                # Nombre
                nombre_elem = soup_indiv.select_one('.player-profile-name')
                nombre = nombre_elem.text.strip() if nombre_elem else slug.replace('-', ' ').title()
                
                # Rating
                rating_elem = soup_indiv.select_one('.player-profile-stats-rating')
                rating = int(rating_elem.text.strip()) if rating_elem and rating_elem.text.strip().isdigit() else 0
                
                # Posicion
                pos_elem = soup_indiv.select_one('.player-profile-stats-pos')
                posicion = pos_elem.text.strip() if pos_elem else ""

                def extract_info(label):
                    elem = soup_indiv.find(string=re.compile(label))
                    if elem and elem.parent and elem.parent.parent:
                        lines = [text.strip() for text in elem.parent.parent.stripped_strings if text.strip() != label]
                        return lines[0] if lines else ""
                    return ""

                equipo = extract_info('Club')
                liga = extract_info('League')
                nacionalidad = extract_info('Nation')
                
                # Intentamos deducir la version_carta
                version_elem = soup_indiv.find(string=re.compile('Skill Moves'))
                version_carta = "Special" # Default si no encontramos el label
                # Un truco sucio: A veces la version esta cerca del nombre o como background
                
                jugadores_extraidos.append({
                    'futwiz_id': futwiz_id,
                    'slug': slug,
                    'nombre': nombre,
                    'rating': rating,
                    'posicion': posicion,
                    'equipo': equipo,
                    'liga': liga,
                    'nacionalidad': nacionalidad,
                    'version_carta': version_carta
                })
            except Exception as e:
                print(f"    Error scrapeando detalles de la novedad: {e}")
                
    except Exception as e:
        print(f"Error parseando novedades: {e}")
        
    return jugadores_extraidos

def chequear_cartas_nuevas():
    """
    Revisa la sección 'Latest' de Futwiz y agrega a la BD los jugadores que aún no existen.
    Devuelve un reporte (string) con las novedades encontradas, listo para enviarse por Telegram.
    """
    url_novedades = "https://www.futwiz.com/en/fc25/players/latest"
    print("🔍 Revisando la sección de cartas más recientes de EA Sports...")
    
    jugadores_recientes = parsear_novedades_futwiz(url_novedades)
    
    conn = _get_connection()
    cursor = conn.cursor()
    
    nuevos_agregados = []
    
    for j in jugadores_recientes:
        futwiz_id = j['futwiz_id']
        
        try:
            # Los jugadores_recientes ya vienen filtrados (no existen en BD) gracias al check en parsear_novedades_futwiz
            id_insertado = insertar_jugador(
                futwiz_id=j['futwiz_id'],
                slug=j['slug'],
                nombre=j['nombre'],
                rating=j['rating'],
                version_carta=j.get('version_carta', 'Scraped/Unknown'),
                liga=j.get('liga', ''),
                equipo=j.get('equipo', ''),
                nacionalidad=j.get('nacionalidad', ''),
                posicion=j['posicion']
            )
            
            if id_insertado:
                nuevos_agregados.append(j['nombre'])
                print(f"✨ ¡NUEVA CARTA REGISTRADA! {j['nombre']} ({j['rating']})")
        except Exception as e:
            print(f"Error procesando id {futwiz_id}: {e}")
            
    conn.close()
    
    if nuevos_agregados:
        nombres_juntos = ", ".join(nuevos_agregados[:10]) # Limite para no ser spam
        if len(nuevos_agregados) > 10:
            nombres_juntos += f" y {len(nuevos_agregados)-10} más..."
            
        print(f"📦 [Silent DB Update] Se agregaron {len(nuevos_agregados)} nuevas cartas: {nombres_juntos}")
        
    return None # Volvemos el bot 100% silencioso para no enviar alertas falsas de cartas ya lanzadas

if __name__ == '__main__':
    print(chequear_cartas_nuevas())
