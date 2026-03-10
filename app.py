# print("Hola mundo")

from curl_cffi import requests
from bs4 import BeautifulSoup

# --- ESTA ES LA FUNCIÓN QUE PIDE LA KAN-8 (Limpieza de datos) ---
def limpiar_precio(precio_texto):
    """
    Escribir una lógica en Python que convierta "15.5K" al número entero 15500.
    """
    if not precio_texto or "No listado" in precio_texto or "Error" in precio_texto:
        return 0
    
    # Quitamos comas y pasamos a mayúsculas para detectar la 'K'
    p = precio_texto.strip().upper().replace(',', '')
    
    try:
        if 'K' in p:
            # Si detecta 'K', quita la letra, convierte a decimal y multiplica por 1000
            numero = float(p.replace('K', ''))
            return int(numero * 1000)
        else:
            # Si no hay 'K', simplemente lo convierte a número entero
            return int(p)
    except Exception:
        return 0

# --- ESTA ES LA FUNCIÓN QUE HICISTE CON SANTIAGO (Sin cambios) ---
def get_player_price_futwiz(player_id, player_slug, fc_version=25):
    """
    Obtiene el precio de un jugador desde Futwiz para una versión específica de EA FC.
    fc_version: El año del juego (ej: 25 para FC25, 26 para FC26, 27 para FC27)
    """
    # La URL en futwiz sigue este formato general
    url = f"https://www.futwiz.com/en/fc{fc_version}/player/{player_slug}/{player_id}"
    
    print(f"Buscando el precio en: {url}")
    
    try:
        # Usamos curl_cffi para evadir protecciones (Cloudflare) simulando Chrome
        response = requests.get(url, impersonate="chrome110", timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscamos la clase específica que contiene el precio en Futwiz (.price-num)
            precio_element = soup.select_one('.price-num')
            
            if precio_element:
                precio = precio_element.text.strip()
                return precio
            else:
                return "No listado / Extinto"
        elif response.status_code == 404:
            return "El jugador no existe en esta versión o la URL es incorrecta."
        else:
            return f"Error HTTP {response.status_code}"
            
    except Exception as e:
        return f"Error de conexión: {e}"

if __name__ == "__main__":
    # URL de un jugador de prueba en Futwiz (Messi)
    player_slug_messi = "lionel-messi"
    player_id_messi = "45" # ID en FC25
    
    # Probando para FC 25 (el juego actual)
    print("--- Probando FC 25 ---")
    precio_25_texto = get_player_price_futwiz(player_id_messi, player_slug_messi, fc_version=25)
    
    # APLICANDO LIMPIEZA DE DATOS (KAN-8)
    precio_limpio = limpiar_precio(precio_25_texto)
    
    print(f"El precio original es: {precio_25_texto}")
    print(f"El precio LIMPIO (Entero) es: {precio_limpio}") # Aquí verás el número entero
    
    # Preparado para FC 27
    print("\n--- Probando FC 27 (Aún no existe) ---")
    precio_27 = get_player_price_futwiz(player_id_messi, player_slug_messi, fc_version=27)
    print(f"El resultado es: {precio_27}")