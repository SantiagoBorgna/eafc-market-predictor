import sys
import os
import time
import re
from bs4 import BeautifulSoup
from curl_cffi import requests
import random

NAVEGADORES = ["chrome110", "chrome116", "chrome120", "edge99", "edge101", "safari15_5", "safari17_0"]

# Agregar el directorio raíz al path para importar el módulo de base de datos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.crud import obtener_todos_los_jugadores, actualizar_precio_jugador

def extraer_precio_futwiz(url):
    """
    Visita la página de un jugador en futwiz y extrae su precio actual.
    Retorna el precio como entero o 0 si hubo un error.
    """
    try:
        response = requests.get(url, impersonate=random.choice(NAVEGADORES), timeout=15)
        if response.status_code != 200:
            print(f"Error {response.status_code} al acceder a {url}")
            return 0
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Búsqueda del contenedor de precios
        price_container = soup.select_one('.price-num') or soup.select_one('.player-prices')
        
        if not price_container:
            return 0
            
        text_content = price_container.text.strip()
        # Buscar el primer número formateado (ej. 14,000 o 450)
        match = re.search(r'(?:^|\s|£|€|\$)?([\d,]+|\d+)', text_content)
        
        if match:
            precio_str = match.group(1).replace(',', '')
            return int(precio_str)
            
    except Exception as e:
        print(f"Excepción obteniendo precio en {url}: {e}")
        
    return 0

def actualizar_todos_los_precios():
    """
    Obtiene todos los jugadores de la base de datos, extrae sus precios
    actualizados desde Futwiz y los guarda en la BD.
    """
    print("🚀 Iniciando actualizador de precios masivo...")
    jugadores = obtener_todos_los_jugadores()
    
    if not jugadores:
        print("⚠️ No hay jugadores en la base de datos para actualizar.")
        return
        
    print(f"📊 Se encontraron {len(jugadores)} jugadores para actualizar. Esto tomará un tiempo.")
    
    actualizados_count = 0
    errores_count = 0
    
    for jugador in jugadores:
        jugador_id = jugador['id']
        futwiz_id = jugador['futwiz_id']
        slug = jugador['slug']
        nombre = jugador['nombre']
        
        url_jugador = f"https://www.futwiz.com/en/fc25/player/{slug}/{futwiz_id}"
        print(f"🔍 Actualizando {nombre}...")
        
        nuevo_precio = extraer_precio_futwiz(url_jugador)
        
        if nuevo_precio > 0:
            if actualizar_precio_jugador(jugador_id, nuevo_precio):
                actualizados_count += 1
                print(f"   ✅ Precio actualizado: {nuevo_precio}")
            else:
                # Si actualizar_precio_jugador retorna False (ej. el precio no cambió o no rompió el mínimo), solo lo indicamos
                # Dependiendo de tu lógica en crud.py, actualizar_precio_jugador SIEMPRE actualiza el precio actual, 
                # y si hay un nuevo mínimo tb lo actualiza. False puede ocurrir si hubo error SQL o si pasamos precio=0.
                pass
        else:
            print(f"   ❌ No se pudo extraer el precio de {nombre}.")
            errores_count += 1
            
        # IMPORTANT: Pausa para no saturar al servidor (anti-ban)
        time.sleep(1)
        
    print("\n🏁 Actualización de precios finalizada.")
    print(f"✅ Jugadores actualizados con éxito (nuevo historial o precio exacto): {actualizados_count}")
    print(f"❌ Errores extrayendo precio: {errores_count}")

if __name__ == "__main__":
    actualizar_todos_los_precios()
