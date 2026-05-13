import os
import datetime
from curl_cffi import requests
from utils.logger import get_logger

logger = get_logger(__name__)

# Lista básica de equipos que suelen protagonizar Marquesinas de EA FC
EQUIPOS_TOP = [
    "Real Madrid", "FC Barcelona", "Atlético", "Sevilla",
    "Manchester United", "Manchester City", "Liverpool FC", "Arsenal FC", "Chelsea FC", "Tottenham",
    "Bayern Munich", "Dortmund", "Leverkusen", "RB Leipzig",
    "Juventus", "Inter Milan", "AC Milan", "Napoli", "Roma", "Lazio",
    "Paris Saint-Germain", "Marseille", "Lyon",
    "Boca Juniors", "River Plate", "Galatasaray", "Fenerbahce", "Celtic", "Rangers"
]

def obtener_marquesinas_prediccion():
    """
    Busca partidos importantes en los próximos 7 días que podrían ser Marquee Matchups
    usando la API gratuita de football-data.org
    """
    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        logger.warning("FOOTBALL_DATA_API_KEY no configurada. Saltando predicción por API.")
        return []

    headers = {"X-Auth-Token": api_key}
    
    hoy = datetime.date.today()
    # Buscamos desde hoy hasta los próximos 6 días
    fecha_desde = hoy.strftime("%Y-%m-%d")
    fecha_hasta = (hoy + datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={fecha_desde}&dateTo={fecha_hasta}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            
            candidatos = []
            for match in matches:
                home_team = match["homeTeam"]["name"]
                away_team = match["awayTeam"]["name"]
                
                # Verificamos si AMBOS son equipos grandes/clásicos
                is_home_top = any(top in home_team for top in EQUIPOS_TOP)
                is_away_top = any(top in away_team for top in EQUIPOS_TOP)
                
                if is_home_top and is_away_top:
                    candidatos.append({
                        "local": home_team,
                        "visitante": away_team,
                        "competicion": match.get("competition", {}).get("name", "Liga"),
                        "fecha": match["utcDate"][:10]
                    })
            
            # Retornamos máximo 4 que es el formato clásico de EA
            return candidatos[:4]
        else:
            logger.error(f"Error consultando football-data.org: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Excepción al buscar marquesinas por API: {e}")
        
    return []

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    res = obtener_marquesinas_prediccion()
    print("Predicción de Marquesinas:")
    for r in res:
        print(f"{r['local']} vs {r['visitante']} ({r['fecha']})")
