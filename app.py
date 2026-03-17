import os
import asyncio
import feedparser
import logging
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, CommandHandler
from bot.motor_reglas import analizar_filtracion_y_recomendar
from database.crud import registrar_suscriptor, obtener_suscriptores, contar_jugadores, buscar_jugador_por_nombre

# Variables globales para el bot
ultima_filtracion_vista = None

# --- 1. CONFIGURACIÓN (KAN-11) ---
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- FUNCIONES DE MAIN (Conservadas para búsquedas avanzadas) ---
def get_player_price_futwiz(player_id, player_slug, fc_version=25):
    """
    Obtiene el precio de un jugador desde Futwiz para una versión específica de EA FC.
    fc_version: El año del juego (ej: 25 para FC25, 26 para FC26, 27 para FC27)
    """
    # La URL en futwiz sigue este formato general
    url = f"https://www.futwiz.com/en/fc{fc_version}/player/{player_slug}/{player_id}"
    
    logging.info("Buscando el precio en: %s", url)
    
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

# --- 2. LÓGICA DE PRECIOS DEL BOT (KAN-8 y KAN-9) ---
def limpiar_precio(precio_texto):
    if not precio_texto or any(x in precio_texto for x in ["No listado", "Error"]):
        return 0
    p = precio_texto.strip().upper().replace(',', '')
    try:
        if 'K' in p:
            return int(float(p.replace('K', '')) * 1000)
        return int(p)
    except:
        return 0

def obtener_precio_actual(url_jugador):
    try:
        response = requests.get(url_jugador, impersonate="chrome110", timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            precio_element = soup.select_one('.price-num')
            if precio_element:
                return limpiar_precio(precio_element.text.strip())
        return 0
    except Exception as e:
        logging.error("Ocurrió un error: %s", e)
        return 0

# --- 3. LÓGICA DE FEED CON FILTRO DE RUIDO (KAN-15 y KAN-16) ---
def obtener_ultimo_filtrado():
    """Se conecta al feed y filtra solo mensajes con 'SBC' o 'Leak'"""
    url_feed = "https://www.fifaultimateteam.it/en/feed/"
    feed = feedparser.parse(url_feed)
    
    if feed.entries:
        # KAN-16: Buscamos en las últimas 5 entradas para encontrar algo relevante
        for entrada in feed.entries[:5]:
            titulo = entrada.title
            # Filtro: Solo si contiene SBC o Leak (insensible a mayúsculas/minúsculas)
            if "SBC" in titulo.upper() or "LEAK" in titulo.upper():
                return f"🔥 **FILTRACIÓN IMPORTANTE (SBC/Leak):**\n\n{titulo}\n\n🔗 {entrada.link}"
        
        return "🤫 Por ahora no hay filtraciones críticas. Todo está tranquilo."
    
    return "📭 No se pudo acceder al feed de noticias."

# --- 4. COMANDOS DEL BOT (KAN-12, KAN-14) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_chat.username
    tipo_chat = update.effective_chat.type
    
    if registrar_suscriptor(chat_id, username, tipo_chat):
        await update.message.reply_text("Hola, estoy listo para predecir el mercado y darte filtraciones. ¡Acabas de quedar suscrito a las Alertas Automáticas! 🛎️")
    else:
        await update.message.reply_text("¡Hola! Ya estabas suscrito a las Alertas Automáticas. 🛎️")

async def precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """KAN-14: Integración de precios"""
    if not context.args:
        await update.message.reply_text("⚠️ Envía una URL después de /precio")
        return
    url_usuario = context.args[0]
    await update.message.reply_text("⏳ Buscando precio real...")
    p = obtener_precio_actual(url_usuario)
    await update.message.reply_text(f"💰 El precio es: {p} monedas.")

async def filtrados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """KAN-16: Comando filtrado"""
    await update.message.reply_text("📡 Conectando con el servidor de filtraciones...")
    noticia = obtener_ultimo_filtrado()
    await update.message.reply_text(noticia, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nuevos Comandos: Estadísticas del bot"""
    total_jug = contar_jugadores()
    total_subs = len(obtener_suscriptores())
    await update.message.reply_text(f"📊 **Estadísticas del Motor:**\n- Jugadores rastreados: {total_jug}\n- Suscriptores activos: {total_subs}", parse_mode='Markdown')

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nuevos Comandos: Buscar jugador por nombre y mostrar precio actual"""
    if not context.args:
        await update.message.reply_text("⚠️ Envía un nombre después de /buscar (Ej: /buscar Messi)")
        return
        
    nombre_query = " ".join(context.args)
    resultados = buscar_jugador_por_nombre(nombre_query)
    
    if not resultados:
        await update.message.reply_text(f"❌ No encontré ningún jugador que coincida con '{nombre_query}'.")
        return
        
    mensaje = f"🔍 **Resultados para '{nombre_query}':**\n\n"
    for r in resultados[:10]: # Top 10 para evitar mensajes muy largos en Telegram
        mensaje += f"• {r['nombre']} ({r['rating']} - {r['version_carta']}) | Precio: {r['precio_actual']} 🪙\n"
        
    if len(resultados) > 10:
        mensaje += f"\n*... y {len(resultados) - 10} resultados más.*"
        
    await update.message.reply_text(mensaje, parse_mode='Markdown')

# --- 4.5 TAREAS EN SEGUNDO PLANO (ALERTAS) ---
async def chequear_feed_periodico(context: ContextTypes.DEFAULT_TYPE):
    global ultima_filtracion_vista
    
    url_feed = "https://www.fifaultimateteam.it/en/feed/"
    try:
        feed = feedparser.parse(url_feed)
        if feed.entries:
            entrada = feed.entries[0] # Revisamos la mas reciente de todo el feed
            titulo = entrada.title
            link = entrada.link
            
            # Filtro: Contiene palabra clave y no la hemos mandado antes todavía
            if ("SBC" in titulo.upper() or "LEAK" in titulo.upper()) and link != ultima_filtracion_vista:
                ultima_filtracion_vista = link
                
                # 1. Avisamos la noticia en vivo
                alerta_msg = f"🚨 **ALERTA AUTOMÁTICA: NUEVA FILTRACIÓN DETECTADA** 🚨\n\n{titulo}\n🔗 {link}"
                suscriptores_db = obtener_suscriptores()
                
                for chat_id in suscriptores_db:
                    await context.bot.send_message(chat_id=chat_id, text=alerta_msg, parse_mode='Markdown')
                
                # 2. Pasamos el titular de la noticia por el Motor de Reglas Predictivo
                recomendacion = analizar_filtracion_y_recomendar(titulo)
                if recomendacion:
                    for chat_id in suscriptores_db:
                        await context.bot.send_message(chat_id=chat_id, text=recomendacion, parse_mode='Markdown')
                        
    except Exception as e:
        logging.error("Ocurrió un error: %s", e)

# --- 5. EJECUCIÓN ---
if __name__ == "__main__":
    if TOKEN:
        logging.info("🚀 Bot KAN-16 en línea. Comandos: /start, /precio, /filtrados")
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Registrar JobQueue para las Alertas Automáticas (ejecuta cada 60 segundos)
        job_queue = app.job_queue
        job_queue.run_repeating(chequear_feed_periodico, interval=60, first=10)
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("precio", precio))
        app.add_handler(CommandHandler("filtrados", filtrados))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("buscar", buscar))
        
        app.run_polling()
    else:
        logging.error("❌ Error: TOKEN no encontrado.")
