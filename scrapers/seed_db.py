import sys
import os
import time
import re
from bs4 import BeautifulSoup
from curl_cffi import requests
import random

NAVEGADORES = ["chrome110", "chrome116", "chrome120", "edge99", "edge101", "safari15_5", "safari17_0"]

# Add root folder to sys_path to allow absolute imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import insertar_jugador, obtener_jugador_por_id, obtener_jugador_por_futwiz_id

def parsear_pagina_futwiz(url):
    """
    Toma una URL de un listado de jugadores en Futwiz, extrae una lista de diccionarios
    con los datos básicos: id, slug, nombre, rating, posicion.
    """
    jugadores_extraidos = []
    
    print(f"📡 Scrapeando: {url}")
    try:
        response = requests.get(url, impersonate=random.choice(NAVEGADORES), timeout=15)
        if response.status_code != 200:
            print(f"Error {response.status_code} al acceder a {url}")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cada jugador en la vista de grilla de futwiz (cards o rows)
        cards = soup.select('.player-search-result-row-container')
        
        for card in cards:
            link_elem = card.select_one('a')
            if not link_elem or 'href' not in link_elem.attrs:
                continue
                
            href = link_elem['href']
            partes = href.split('/')
            if len(partes) < 4:
                continue
                
            futwiz_id = int(partes[-1])
            slug = partes[-2]
            
            # Verificar si existe en BD antes de hacer requests individuales (ahorra MUCHISIMO tiempo y evita ban)
            if obtener_jugador_por_futwiz_id(futwiz_id):
                print(f"  ⏭️ Saltando (ya existe en BD): {slug}")
                continue
            
            # Navegar a la página individual para obtener todos los datos
            url_jugador = f"https://www.futwiz.com{href}"
            print(f"  ↳ Obteniendo detalles de: {slug}")
            
            try:
                # Pequeña pausa para no bombardear al servidor con request individuales tan rápido
                time.sleep(1)
                res_indiv = requests.get(url_jugador, impersonate=random.choice(NAVEGADORES), timeout=15)
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
                        # Estructura típica: <div><div class="label">Club</div><div>FC Barcelona</div></div>
                        lines = [text.strip() for text in elem.parent.parent.stripped_strings if text.strip() != label]
                        return lines[0] if lines else ""
                    return ""

                equipo = extract_info('Club')
                liga = extract_info('League')
                nacionalidad = extract_info('Nation')
                
                # Version: Intentamos deducirlo del título de la página o de labels dorados
                version_carta = "Gold" # Default para seed
                
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
                print(f"    Error scrapeando detalles: {e}")
                
    except Exception as e:
        print(f"Excepción en el scraping masivo: {e}")
        
    return jugadores_extraidos

def poblar_base_datos(paginas_a_escanear=5):
    """
    Scrapea el listado de cartas ORO (non-special cards) para poblar la BD inicial.
    Futwiz params: 'rarity=rare,non-rare' y 'quality=gold' filtra a solo oros base.
    """
    # Simplificamos la URL para evitar el Error 500 del servidor
    # 'page' empieza en 0
    url_base = "https://www.futwiz.com/en/fc25/players?page={}&quality=gold&rarity=goldrare,goldnonrare"
    
    total_insertados = 0
    total_procesados = 0

    for i in range(paginas_a_escanear):
        url = url_base.format(i)
        jugadores = parsear_pagina_futwiz(url)
        
        if not jugadores:
            print("⚠️ No se encontraron jugadores o fuimos bloqueados. Deteniendo.")
            break
            
        for g in jugadores:
            total_procesados += 1
            # Para evitar duplicados en pruebas futuras, lo ideal sería chequear si ya existe antes de insertar, 
            # pero por ahora, como el ID nuestro de la BD y el futwiz_id no interactuan conflictivamente salvo 
            # que agreguemos constraint de Unique al futwiz_id, haremos inserción directa.
            
            # En un entorno real se haría: 
            # "SELECT * FROM jugadores where futwiz_id = ?" si no existe, insert. (Lo agregaremos luego).
            
            # Inserción asumiendo que está semi-vacia:
            # Ponemos "Gold" como versión por defecto ya que usamos URLs filtradas.
            id_db = insertar_jugador(
                futwiz_id=g['futwiz_id'],
                slug=g['slug'],
                nombre=g['nombre'],
                rating=g['rating'],
                version_carta=g.get('version_carta', 'Gold'),
                liga=g.get('liga', ''),
                equipo=g.get('equipo', ''),
                nacionalidad=g.get('nacionalidad', ''),
                posicion=g['posicion']
            )
            if id_db:
                total_insertados += 1
                
        # Anti-ban sleep (Fundamental!)
        print(f"✅ Pagina {i} escaneada. Durmiendo 3 segundos anti-ban...")
        time.sleep(3)
        
    print(f"🎉 Población finalizada. {total_procesados} procesados. {total_insertados} insertados en BD.")

if __name__ == "__main__":
    print("Iniciando SEED masivo. Limitado a 1 página para test inicial rápido.")
    poblar_base_datos(paginas_a_escanear=1)
