import sqlite3
import re
import time
import os
import sys

# Agregamos la raíz del proyecto al sys.path para imports si se requieren
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests

def run():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database', 'database.sqlite')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all promo types that are not mapped yet
    cursor.execute("SELECT id FROM tipos_carta WHERE nombre LIKE 'Promo %'")
    promos = cursor.fetchall()
    print(f"Total a procesar: {len(promos)}")
    
    for (tipo_id,) in promos:
        cursor.execute("SELECT futwiz_id, slug, nombre FROM jugadores WHERE version_carta = ? LIMIT 1", (tipo_id,))
        row = cursor.fetchone()
        if not row:
            continue
            
        futwiz_id, slug, player_name = row
        url = f"https://www.futwiz.com/en/fc26/player/{slug}/{futwiz_id}"
        print(f"Fetching {tipo_id} from {url}")
        
        try:
            res = requests.get(url, impersonate="chrome120", timeout=10)
            if res.status_code == 200:
                match = re.search(r'<title>(.*?)</title>', res.text)
                if match:
                    title = match.group(1)
                    promo_match = re.search(r'EA FC26 (.*?)\s+-', title)
                    if promo_match:
                        promo_name = promo_match.group(1).strip()
                        if promo_name:
                            print(f"-> Mapped {tipo_id} to '{promo_name}'")
                            cursor.execute("UPDATE tipos_carta SET nombre = ? WHERE id = ?", (promo_name, tipo_id))
                            conn.commit()
                    else:
                        print(f"-> Could not parse promo from title: {title}")
            time.sleep(0.5)
        except Exception as e:
            print("Error:", e)
            
    conn.close()

if __name__ == '__main__':
    run()
