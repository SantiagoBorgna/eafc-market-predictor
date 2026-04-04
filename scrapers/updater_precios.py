import sys
import os
import time
import json
import re
from curl_cffi import requests

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
        res = requests.post(url, headers=headers, data=data, impersonate="chrome120", timeout=15)
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
        print(f"Excepción obteniendo precio para {slug}: {e}")
        
    return 0

def actualizar_todos_los_precios():
    """
    Obtiene todos los jugadores de la base de datos, extrae sus precios
    actualizados mediante la API de Futwiz y los guarda en la BD.
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
        
        print(f"🔍 Buscando API FC26 para {nombre}...")
        
        nuevo_precio = extraer_precio_futwiz(slug, futwiz_id)
        
        if nuevo_precio > 0:
            if actualizar_precio_jugador(jugador_id, nuevo_precio):
                actualizados_count += 1
                print(f"   ✅ Precio actualizado: {nuevo_precio}")
            else:
                pass
        else:
            print(f"   ❌ No se pudo extraer el precio API de {nombre}.")
            errores_count += 1
            
        time.sleep(1)
        
    print("\n🏁 Actualización de precios finalizada.")
    print(f"✅ Jugadores actualizados con éxito: {actualizados_count}")
    print(f"❌ Errores o precios sin cambios: {errores_count}")

if __name__ == "__main__":
    actualizar_todos_los_precios()

