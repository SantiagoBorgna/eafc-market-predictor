import os
import asyncio
import feedparser
import logging
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, CommandHandler

# --- IMPORTS DE LOGICA EXTERNA (FUNDAMENTALES) ---
# Asegúrate de haber creado los archivos en /bot y /database como vimos antes
from bot.motor_reglas import analizar_filtracion_y_recomendar
from database.crud import (
    registrar_suscriptor, 
    obtener_suscriptores, 
    obtener_suscriptores_separados, 
    contar_jugadores, 
    buscar_jugador_por_nombre
)

# Variables globales para el bot
ultima_filtracion_vista = None

# --- 1. CONFIGURACIÓN DE ENTORNO Y LOGS (KAN-11) ---
# Registro de actividad para debugear errores de conexión o de scraping
logging.basicConfig(
    filename='bot.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- 2. FUNCIONES DE BÚSQUEDA AVANZADA (Código original del jefe) ---
def get_player_price_futwiz(player_id, player_slug, fc_version=25):
    """
    Obtiene el precio de un jugador desde Futwiz para una versión específica de EA FC.
    fc_version: El año del juego (ej: 25 para FC25, 26 para FC26, 27 para FC27)
    """
    url = f"https://www.futwiz.com/en/fc{fc_version}/player/{player_slug}/{player_id}"
    logging.info(f"Iniciando consulta avanzada en Futwiz: {url}")
    
    try:
        # Simulación de navegador para evitar bloqueos de Cloudflare
        response = requests.get(url, impersonate="chrome110", timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            precio_element = soup.select_one('.price-num')
            
            if precio_element:
                precio = precio_element.text.strip()
                logging.info(f"Precio recuperado: {precio}")
                return precio
            else:
                return "No listado / Extinto"
        elif response.status_code == 404:
            return "Error 404: Jugador no encontrado."
        else:
            return f"Error HTTP {response.status_code}"
            
    except Exception as e:
        logging.error(f"Error de red en get_player_price_futwiz: {e}")
        return f"Error de conexión: {e}"

# --- 3. LÓGICA DE PRECIOS DEL BOT (KAN-8 y KAN-9) ---
def limpiar_precio(precio_texto):
    """Limpia el texto del precio y lo convierte a entero (ej: 55K -> 55000)"""
    if not precio_texto or any(x in precio_texto for x in ["No listado", "Error", "Extinto"]):
        return 0
    p = precio_texto.strip().upper().replace(',', '')
    try:
        if 'K' in p:
            return int(float(p.replace('K', '')) * 1000)
        return int(p)
    except Exception as e:
        logging.error(f"Fallo al limpiar precio {precio_texto}: {e}")
        return 0

def obtener_precio_actual(url_jugador):
    """Scraping rápido para los comandos integrados del bot"""
    try:
        logging.info(f"Scrapeando URL: {url_jugador}")
        response = requests.get(url_jugador, impersonate="chrome110", timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            precio_element = soup.select_one('.price-num')
            if precio_element:
                return limpiar_precio(precio_element.text.strip())
        return 0
    except Exception as e:
        logging.error(f"Error en obtener_precio_actual: {e}")
        return 0

# --- 4. TAREAS AUTOMÁTICAS: KAN-31 (DELAY) Y KAN-32 (TEXTO VIP) ---

async def enviar_alerta_retrasada(context: ContextTypes.DEFAULT_TYPE):
    """
    KAN-31: Envía la alerta a usuarios Free tras 15 minutos.
    KAN-32: Concatena el mensaje de invitación a VIP.
    """
    datos = context.job.data
    chat_ids_gratis = datos['ids']
    mensaje_base = datos['mensaje']
    
    # KAN-32: Texto requerido para incentivar la suscripción VIP
    footer_vip = (
        "\n\n⏳ *Recibiste esta alerta con 15 min de retraso. "
        "Para recibirla al instante y asegurar tu ganancia, actualizá a VIP con /vip*"
    )
    
    mensaje_final = f"{mensaje_base}{footer_vip}"
    
    logging.info(f"Ejecutando KAN-31/32 para {len(chat_ids_gratis)} usuarios.")
    
    for chat_id in chat_ids_gratis:
        try:
            await context.bot.send_message(chat_id=chat_id, text=mensaje_final, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Error enviando a {chat_id}: {e}")

async def chequear_feed_periodico(context: ContextTypes.DEFAULT_TYPE):
    """Revisa el feed de noticias buscando filtraciones cada 60 segundos"""
    global ultima_filtracion_vista
    
    url_feed = "https://www.fifaultimateteam.it/en/feed/"
    try:
        feed = feedparser.parse(url_feed)
        if feed.entries:
            entrada = feed.entries[0]
            titulo = entrada.title
            link = entrada.link
            
            # Filtro KAN-16: Solo SBCs o Leaks nuevos
            if ("SBC" in titulo.upper() or "LEAK" in titulo.upper()) and link != ultima_filtracion_vista:
                ultima_filtracion_vista = link
                
                logging.info(f"Filtración detectada: {titulo}")
                
                # Análisis mediante el Motor de Reglas
                recomendacion = analizar_filtracion_y_recomendar(titulo)
                full_msg = f"🚨 **NUEVA FILTRACIÓN** 🚨\n\n{titulo}\n🔗 {link}"
                if recomendacion:
                    full_msg += f"\n\n💡 **Recomendación:**\n{recomendacion}"
                
                # Segmentación de usuarios
                listas = obtener_suscriptores_separados()
                vips = listas.get('vip', [])
                gratis = listas.get('gratis', [])
                
                # 1. VIP: Envío inmediato
                for chat_id in vips:
                    await context.bot.send_message(chat_id=chat_id, text=full_msg, parse_mode='Markdown')
                
                # 2. Free: Programar para 15 minutos después (900 segundos)
                if gratis:
                    context.job_queue.run_once(
                        enviar_alerta_retrasada, 
                        when=900, 
                        data={'ids': gratis, 'mensaje': full_msg}
                    )
                    logging.info("KAN-31: Alerta para usuarios Free programada en JobQueue.")
                        
    except Exception as e:
        logging.error(f"Error en tarea periódica: {e}")

# --- 5. COMANDOS DEL BOT (TELEGRAM HANDLERS) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra al usuario en la base de datos y da bienvenida"""
    chat_id = update.effective_chat.id
    username = update.effective_chat.username
    tipo = update.effective_chat.type
    
    if registrar_suscriptor(chat_id, username, tipo):
        await update.message.reply_text("¡Bienvenido! Ya estás suscrito a las Alertas Automáticas de FC 25. 🛎️")
    else:
        await update.message.reply_text("¡Hola! Ya te encuentras en nuestra lista de suscriptores. 🛎️")

async def precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta de precio manual"""
    if not context.args:
        await update.message.reply_text("⚠️ Indica una URL de FutWiz después de /precio")
        return
    await update.message.reply_text("⏳ Obteniendo precio en tiempo real...")
    p = obtener_precio_actual(context.args[0])
    await update.message.reply_text(f"💰 El precio es: **{p}** monedas.")

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información sobre la suscripción VIP"""
    msj = (
        "💎 **Suscripción VIP** 💎\n\n"
        "• Alertas al instante (sin 15m de espera).\n"
        "• Análisis detallado de inversión.\n"
        "• Soporte 24/7.\n\n"
        "Escribe a @SoporteBot para activar tu cuenta."
    )
    await update.message.reply_text(msj, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estadísticas globales del sistema"""
    total_j = contar_jugadores()
    total_s = len(obtener_suscriptores())
    await update.message.reply_text(f"📊 **Stats:**\n- Jugadores: {total_j}\n- Suscriptores: {total_s}", parse_mode='Markdown')

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca jugadores por nombre en la base de datos"""
    if not context.args:
        await update.message.reply_text("⚠️ Ejemplo: /buscar Messi")
        return
    query = " ".join(context.args)
    resultados = buscar_jugador_por_nombre(query)
    if not resultados:
        await update.message.reply_text(f"❌ No hay resultados para '{query}'.")
        return
    res_msg = f"🔍 **Resultados para '{query}':**\n\n"
    for r in resultados[:10]:
        res_msg += f"• {r['nombre']} ({r['rating']}) | {r['precio_actual']} 🪙\n"
    await update.message.reply_text(res_msg, parse_mode='Markdown')

# --- 6. EJECUCIÓN DEL SISTEMA ---
if __name__ == "__main__":
    if TOKEN:
        print("🚀 Bot iniciado con KAN-31 y KAN-32...")
        logging.info("Bot en línea. Iniciando JobQueue y Polling.")
        
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Iniciar revisión periódica del feed (cada 60 segundos)
        app.job_queue.run_repeating(chequear_feed_periodico, interval=60, first=10)
        
        # Registro de comandos
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("precio", precio))
        app.add_handler(CommandHandler("vip", vip))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("buscar", buscar))
        
        app.run_polling()
    else:
        print("❌ ERROR: Falta TELEGRAM_TOKEN en el archivo .env")
        logging.error("No se pudo iniciar el bot: Token ausente.")