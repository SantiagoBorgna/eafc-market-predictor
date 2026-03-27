import os
import sqlite3
from curl_cffi import requests
from database.crud import es_post_nuevo, registrar_post

def chequear_filtraciones_reddit():
    """
    Se conecta al feed JSON de múltiples subreddits buscando posts
    recientes sobre Leaks o Filtraciones.
    Devuelve un diccionario con la nueva filtración o None si no hay nada nuevo.
    """
    fuentes_reddit = [
        # El oficial buscando por la etiqueta formal 'Leak'
        "https://www.reddit.com/r/EASportsFC/search.json?q=flair%3ALeak&restrict_sr=on&sort=new",
        # El foro alternativo masivo de Ultimate Team
        "https://www.reddit.com/r/fut/search.json?q=leak&restrict_sr=on&sort=new",
        # El clásico foro de comunidades más veteranas
        "https://www.reddit.com/r/FIFA/search.json?q=leak&restrict_sr=on&sort=new"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 EA_FC_Tracker_Bot/1.0"
    }

    for url in fuentes_reddit:
        try:
            # Usamos curl_cffi para bypassear posibles bloqueos de Reddit a bots ordinarios
            response = requests.get(url, headers=headers, impersonate="chrome110", timeout=15)
            
            if response.status_code == 200:
                datos = response.json()
                posts = datos.get('data', {}).get('children', [])
                
                for p in posts:
                    post_data = p['data']
                    post_id = post_data['id']
                    titulo = post_data['title']
                    permalink = post_data['permalink']
                    
                    # Filtramos basuras: si alguien pregunta "Is this a leak?" no es un leak
                    if "?" in titulo and "leak" in titulo.lower():
                        continue
                    
                    # Si el post no está en nuestra BD, significa que es una filtración genuinamente nueva
                    if es_post_nuevo(post_id):
                        # Lo registramos para no volver a analizar el mismo id de Reddit
                        registrar_post(post_id, titulo)
                        
                        url_completa = f"https://www.reddit.com{permalink}"
                        return { # Al encontrar 1 leak, retornamos y detenemos el bucle hasta los próximos 5 mins
                            'titulo': titulo,
                            'url': url_completa
                        }
                        
            # Reddit podría bloquearnos si no esperamos un poco o por HTTP 429
            elif response.status_code == 429:
                print("⚠️ Reddit nos limitó (HTTP 429). Esperamos hasta el próximo ciclo.")
                break # Frenamos de pegarle a los que faltan y retornamos
                
        except Exception as e:
            print(f"❌ Error escaneando un foro de Reddit: {e}")
        
    return None

if __name__ == '__main__':
    # Prueba manual aisalda
    filtracion = chequear_filtraciones_reddit()
    if filtracion:
        print("Nueva filtración Encontrada:")
        print(filtracion['titulo'])
        print(filtracion['url'])
    else:
        print("Ninguna filtración nueva.")
