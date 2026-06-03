import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import re
import sys
import os
import json
import google.generativeai as genai

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
import time

# Memoria para el cooldown anti-spam de Panic Selling
_cooldown_panic_selling = {}


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
    Analiza una filtración con Google Gemini para traducir, detectar SBC, razonar perfiles 
    y buscar cartas en la base de datos.
    Retorna: mensaje_recomendacion, requisitos_extraidos, titulo_traducido
    """
    api_key = os.getenv("GEMINI_API_KEY")
    requisitos = {}
    titulo_traducido = texto_filtracion
    perfil_recomendado = ""
    is_sbc = False
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"""
Sos un experto trader de EA FC Ultimate Team y traductor. Leé este título de filtración o rumor sobre un SBC, Promo o Evolución:
"{texto_filtracion}"

Tareas:
1. Traducí el título al español de forma natural para gamers.
2. Identificá si se trata de un SBC (Squad Building Challenge).
3. ¿Qué perfiles de cartas van a pedir como requisitos y subirán de precio en el mercado? Describí el perfil recomendado en 1 o 2 oraciones (ej: "Cartas de oro brillantes de nacionalidad Francesa o de la Serie A, preferentemente medias 83-84.").
4. Extraé los requisitos exactos en formato estructurado ("nacionalidad" en inglés, "liga" exacta, "rating" en entero).

Devolvé SOLO un JSON válido y crudo (sin bloques de código markdown, sin texto adicional) con esta estructura exacta:
{{
  "titulo_traducido": "...",
  "is_sbc": true,
  "perfil_recomendado": "...",
  "requisitos": {{"nacionalidad": "France", "liga": "Serie A", "rating": 84}}
}}
Si no podés deducir requisitos estructurados, dejá "requisitos" vacío {{}}.
"""
            response = model.generate_content(prompt)
            texto_json = response.text.strip()
            
            # Limpiamos posibles bloques markdown
            if texto_json.startswith("```json"):
                texto_json = texto_json.split("```json")[1].split("```")[0].strip()
            elif texto_json.startswith("```"):
                texto_json = texto_json.split("```")[1].strip()
                
            data_json = json.loads(texto_json)
            requisitos = data_json.get("requisitos", {})
            titulo_traducido = data_json.get("titulo_traducido", texto_filtracion)
            perfil_recomendado = data_json.get("perfil_recomendado", "")
            is_sbc = data_json.get("is_sbc", False)
            
            logger.info(f"Gemini analizó el leak: SBC={is_sbc}, Perfil={perfil_recomendado}")
            
        except Exception as e:
            logger.error(f"Error procesando leak con Gemini: {e}")
            requisitos = extraer_requisitos(texto_filtracion)
    else:
        logger.info("Sin GEMINI_API_KEY, usando extracción por regex.")
        requisitos = extraer_requisitos(texto_filtracion)
    
    if not requisitos and not perfil_recomendado:
        return None, {}, titulo_traducido
        
    # Buscamos en la BD todos los jugadores que cumplen (ojo, puede ser una lista grande si la BD está llena)
    jugadores_candidatos = buscar_jugador_por_requisito(requisitos) if requisitos else []
    
    if not jugadores_candidatos:
        req_text = ", ".join([f"{k}: {v}" for k, v in requisitos.items()]) if requisitos else ""
        mensaje_fallback = ""
        if is_sbc:
             mensaje_fallback += "🚨 *ALERTA DE SBC DETECTADA*\n\n"
        if perfil_recomendado:
             mensaje_fallback += f"🧠 *Perfil recomendado a buscar en tu club o mercado:*\n{perfil_recomendado}\n\n"
        if req_text:
             mensaje_fallback += f"*Filtro detectado:* {req_text}\n"
             
        mensaje_fallback += "_(Nota: No tenemos jugadores exactos en la Base de Datos para recomendar en este momento)_"
        return mensaje_fallback, requisitos, titulo_traducido
        
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
    mensaje = f"🚨 *ANÁLISIS DE MERCADO / {'SBC LEAK' if is_sbc else 'NUEVA CARTA'}*\n\n"
    
    if api_key and perfil_recomendado:
        mensaje += f"🧠 *Perfil recomendado a buscar:*\n{perfil_recomendado}\n\n"
    elif requisitos:
        requisitos_texto = ", ".join([f"{k}: {v}" for k, v in requisitos.items()])
        mensaje += f"Requisitos detectados: *{requisitos_texto}*\n\n"
    
    if oportunidades:
        mensaje += "📈 *RECOMENDACIONES DE INVERSIÓN (Cartas en DB a buen precio):*\n"
        max_items = CONFIG.get("motor_reglas", {}).get("max_recomendaciones_mostrar", 5)
        for op in oportunidades[:max_items]: # Mostramos hasta el máximo configurado
            mensaje += f"• {op['nombre']} ({op['rating']}) - Precio Actual: {op['precio_actual']} 🪙 (Piso Histórico: {op['precio_historico_minimo']})\n"
            
        mensaje += "\n⚠️ *ATENCIÓN: Invertí con precaución. No es consejo financiero.*"
    else:
        mensaje += "No se detectaron oportunidades claras de inversión en nuestra base de datos para estos requisitos específicos en este momento."
        
    return mensaje, requisitos, titulo_traducido

def detectar_panic_selling(jugador_id, precio_actual, nombre_jugador, rating, tiempo_horas=1):
    """
    Regla Inversa: Analiza si el jugador sufrió una caída violenta en su precio en la última hora.
    Si cae por encima del porcentaje configurado, podría ser Panic Selling.
    """
    # 1. Filtro de Relevancia: Ignorar cartas con rating menor a 78
    try:
        if int(rating) < 78:
            return None
    except (ValueError, TypeError):
        return None
        
    # 2. Sistema Anti-Spam: Cooldown de 2 horas (7200 segundos) por jugador
    current_time = time.time()
    last_alert_time = _cooldown_panic_selling.get(jugador_id, 0)
    if (current_time - last_alert_time) < 7200:
        return None

    umbral_caida = CONFIG.get("motor_reglas", {}).get("umbral_panic_selling_caida", 0.15)
    
    precio_pasado = obtener_precio_hace_n_horas(jugador_id, horas=tiempo_horas)
    if precio_pasado == 0 or precio_actual == 0:
        return None
        
    caida = (precio_pasado - precio_actual) / precio_pasado
    
    if caida >= umbral_caida:
        mensaje = f"📉 *PANIC SELLING DETECTADO*\n\n"
        mensaje += f"Jugador: *{nombre_jugador}* ({rating})\n"
        mensaje += f"Precio Máx ({tiempo_horas}h atrás): {precio_pasado} 🪙\n"
        mensaje += f"Precio Actual: {precio_actual} 🪙\n"
        mensaje += f"Caída abrupta del: *{caida*100:.1f}%*\n\n"
        mensaje += "💸 _Posible oportunidad de compra si esperás un rebote inmediato del mercado._"
        
        logger.info(f"Oportunidad Panic Selling: {nombre_jugador} (Cayó {caida*100:.1f}%)")
        
        # Registrar alerta enviada en el cooldown
        _cooldown_panic_selling[jugador_id] = current_time
        
        return mensaje
        
    return None
