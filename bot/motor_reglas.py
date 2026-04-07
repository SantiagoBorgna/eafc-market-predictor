import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import re
import sys
import os
import json

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("config.json no encontrado, cargando opciones por defecto.")
        return {
            "motor_reglas": {
                "max_sobreprecio_inversion": 1.15,
                "max_recomendaciones_mostrar": 5
            }
        }

CONFIG = load_config()

# Agregamos la raíz del proyecto al sys.path para poder importar modules desde otras carpetas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.crud import buscar_jugador_por_requisito, obtener_precio_hace_n_horas

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
        return None, {} # No se encontraron requisitos útiles en el leak
        
    # Buscamos en la BD todos los jugadores que cumplen (ojo, puede ser una lista grande si la BD está llena)
    jugadores_candidatos = buscar_jugador_por_requisito(requisitos)
    
    if not jugadores_candidatos:
        return f"🔍 **Análisis de Leak:** Se requiere {requisitos}. No tenemos jugadores en la BD que cumplan esto aún.", requisitos
        
    # Filtramos las "oportunidades": jugadores que están a menos de un 15% de su precio mínimo histórico, o cuyo precio sea > 0
    oportunidades = []
    for j in jugadores_candidatos:
        precio_actual = j['precio_actual']
        precio_min = j['precio_historico_minimo']
        
        # Ignoramos si no tenemos precios de esa carta aún
        if precio_actual == 0 or precio_min == 0:
            continue
            
        umbral_sobreprecio = CONFIG.get("motor_reglas", {}).get("max_sobreprecio_inversion", 1.15)
        # Si el precio actual está muy cerca (o es igual) al mínimo histórico
        if precio_actual <= (precio_min * umbral_sobreprecio):
            oportunidades.append(j)
        else:
            logger.info(f"Jugador {j['nombre']} ignorado, precio muy inflado (Actual: {precio_actual}, Mínimo: {precio_min})")
            
    # Armamos el mensaje
    requisitos_texto = ", ".join([f"{k}: {v}" for k, v in requisitos.items()])
    mensaje = f"🚨 **ANÁLISIS DE MERCADO / SBC LEAK**\n"
    mensaje += f"Requisitos detectados: *{requisitos_texto}*\n\n"
    
    if oportunidades:
        mensaje += "📈 **POSIBLES INVERSIONES:**\n"
        max_items = CONFIG.get("motor_reglas", {}).get("max_recomendaciones_mostrar", 5)
        for op in oportunidades[:max_items]: # Mostramos hasta el máximo configurado
            mensaje += f"• {op['nombre']} ({op['rating']}) - Precio Actual: {op['precio_actual']} 🪙 (Piso Histórico: {op['precio_historico_minimo']})\n"
            
        mensaje += "\n⚠️ *ATENCIÓN: Estas cartas PUEDEN llegar a aumentar de valor si el SBC dispara su demanda. Esto es solo una predicción basada en datos estadísticos, no una certeza absoluta. Invertí con precaución.*"
    else:
        mensaje += "No se detectaron oportunidades claras de inversión (los jugadores actuales que cumplen estos requisitos ya tienen precios inflados o no los tenemos registrados)."
        
    return mensaje, requisitos

def detectar_panic_selling(jugador_id, precio_actual, nombre_jugador, rating, tiempo_horas=1):
    """
    Regla Inversa: Analiza si el jugador sufrió una caída violenta en su precio en la última hora.
    Si cae por encima del porcentaje configurado, podría ser Panic Selling.
    """
    umbral_caida = CONFIG.get("motor_reglas", {}).get("umbral_panic_selling_caida", 0.15)
    
    precio_pasado = obtener_precio_hace_n_horas(jugador_id, horas=tiempo_horas)
    if precio_pasado == 0 or precio_actual == 0:
        return None
        
    caida = (precio_pasado - precio_actual) / precio_pasado
    
    if caida >= umbral_caida:
        mensaje = f"📉 **PANIC SELLING DETECTADO**\n\n"
        mensaje += f"Jugador: *{nombre_jugador}* ({rating})\n"
        mensaje += f"Precio Máx ({tiempo_horas}h atrás): {precio_pasado} 🪙\n"
        mensaje += f"Precio Actual: {precio_actual} 🪙\n"
        mensaje += f"Caída abrupta del: *{caida*100:.1f}%*\n\n"
        mensaje += "💸 _Posible oportunidad de compra si esperás un rebote inmediato del mercado._"
        
        logger.info(f"Oportunidad Panic Selling: {nombre_jugador} (Cayó {caida*100:.1f}%)")
        return mensaje
        
    return None

# --- Bloque de Prueba ---
if __name__ == '__main__':
    logger.info("--- 🧪 Test de Motor de Reglas y Predicción ---")
    
    # Simulamos un texto de una filtración real que podría llegar por RSS o Twitter
    texto_ejemplo_1 = "🚨 LEAK: The upcoming Player of the Month SBC will require an 90 Rated squad including at least 1 player from Argentina."
    texto_ejemplo_2 = "SBC leaked! Requires an 84 rated squad from LaLiga."
    
    logger.info("\n[TEST 1]")
    logger.info(f"Texto: {texto_ejemplo_1}")
    analisis_1, req_1 = analizar_filtracion_y_recomendar(texto_ejemplo_1)
    logger.info("Resultado:")
    logger.info(analisis_1)
    logger.info(f"Requisitos extraídos: {req_1}")
    
    logger.info("\n[TEST 2]")
    logger.info(f"Texto: {texto_ejemplo_2}")
    analisis_2, req_2 = analizar_filtracion_y_recomendar(texto_ejemplo_2)
    logger.info("Resultado:")
    logger.info(analisis_2)
    logger.info(f"Requisitos extraídos: {req_2}")
