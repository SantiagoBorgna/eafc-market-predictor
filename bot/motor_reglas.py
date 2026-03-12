import re
import sys
import os

# Agregamos la raíz del proyecto al sys.path para poder importar modules desde otras carpetas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import buscar_jugador_por_requisito

# Diccionarios de palabras clave simples para el parser
NACIONALIDADES_CLAVE = ["Argentina", "Brazil", "France", "Spain", "Germany", "England", "Portugal", "Netherlands"]
LIGAS_CLAVE = ["Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1", "MLS"]

def extraer_requisitos(texto):
    """
    Toma un texto en inglés y extrae posibles requisitos de SBC usando Regex y palabras clave.
    Retorna un diccionario con los criterios encontrados.
    """
    criterios = {}
    texto_upper = texto.upper()
    texto_original = texto
    
    # 1. Buscar Rating (ej: "84 Rated", "84 Rating", "Min 84 OVR")
    match_rating = re.search(r'(\d{2})\s*(?:RATED|RATING|OVR|OVR\.)', texto_upper)
    if match_rating:
        criterios['rating'] = int(match_rating.group(1))
        
    # 2. Buscar Nacionalidad
    for nacion in NACIONALIDADES_CLAVE:
        if nacion.upper() in texto_upper:
            criterios['nacionalidad'] = nacion
            break # Asumimos un solo país por ahora para simplificar
            
    # 3. Buscar Liga
    for liga in LIGAS_CLAVE:
        # Quitamos espacios para buscar ej: PremierLeague o Premier League
        if liga.upper().replace(" ", "") in texto_upper.replace(" ", ""):
            criterios['liga'] = liga
            break
            
    return criterios

def analizar_filtracion_y_recomendar(texto_filtracion):
    """
    Analiza una filtración, busca jugadores que cumplan el requisito y 
    arma un reporte de mercado (Alertas de Inversión) con precaución.
    """
    requisitos = extraer_requisitos(texto_filtracion)
    
    if not requisitos:
        return None # No se encontraron requisitos útiles en el leak
        
    # Buscamos en la BD todos los jugadores que cumplen (ojo, puede ser una lista grande si la BD está llena)
    jugadores_candidatos = buscar_jugador_por_requisito(requisitos)
    
    if not jugadores_candidatos:
        return f"🔍 **Análisis de Leak:** Se requiere {requisitos}. No tenemos jugadores en la BD que cumplan esto aún."
        
    # Filtramos las "oportunidades": jugadores que están a menos de un 15% de su precio mínimo histórico, o cuyo precio sea > 0
    oportunidades = []
    for j in jugadores_candidatos:
        precio_actual = j['precio_actual']
        precio_min = j['precio_historico_minimo']
        
        # Ignoramos si no tenemos precios de esa carta aún
        if precio_actual == 0 or precio_min == 0:
            continue
            
        # Si el precio actual está muy cerca (o es igual) al mínimo histórico (ej: máximo un 15% más caro que el piso)
        if precio_actual <= (precio_min * 1.15):
            oportunidades.append(j)
            
    # Armamos el mensaje
    requisitos_texto = ", ".join([f"{k}: {v}" for k, v in requisitos.items()])
    mensaje = f"🚨 **ANÁLISIS DE MERCADO / SBC LEAK**\n"
    mensaje += f"Requisitos detectados: *{requisitos_texto}*\n\n"
    
    if oportunidades:
        mensaje += "📈 **POSIBLES INVERSIONES:**\n"
        for op in oportunidades[:5]: # Mostramos máximo 5 para no saturar el chat
            mensaje += f"• {op['nombre']} ({op['rating']}) - Precio Actual: {op['precio_actual']} 🪙 (Piso Histórico: {op['precio_historico_minimo']})\n"
            
        mensaje += "\n⚠️ *ATENCIÓN: Estas cartas PUEDEN llegar a aumentar de valor si el SBC dispara su demanda. Esto es solo una predicción basada en datos estadísticos, no una certeza absoluta. Invertí con precaución.*"
    else:
        mensaje += "No se detectaron oportunidades claras de inversión (los jugadores actuales que cumplen estos requisitos ya tienen precios inflados o no los tenemos registrados)."
        
    return mensaje

# --- Bloque de Prueba ---
if __name__ == '__main__':
    print("--- 🧪 Test de Motor de Reglas y Predicción ---")
    
    # Simulamos un texto de una filtración real que podría llegar por RSS o Twitter
    texto_ejemplo_1 = "🚨 LEAK: The upcoming Player of the Month SBC will require an 90 Rated squad including at least 1 player from Argentina."
    texto_ejemplo_2 = "SBC leaked! Requires an 84 rated squad from LaLiga."
    
    print("\n[TEST 1]")
    print(f"Texto: {texto_ejemplo_1}")
    analisis_1 = analizar_filtracion_y_recomendar(texto_ejemplo_1)
    print("Resultado:")
    print(analisis_1)
    
    print("\n[TEST 2]")
    print(f"Texto: {texto_ejemplo_2}")
    analisis_2 = analizar_filtracion_y_recomendar(texto_ejemplo_2)
    print("Resultado:")
    print(analisis_2)
