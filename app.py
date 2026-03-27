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
    buscar_jugador_por_nombre,
    actualizar_vip_usuario,  # Agregado para la KAN-34
    limpiar_vips_vencidos
)
import datetime

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

# --- 2. FUNCIONES DE BÚSQUEDA AVANZADA ---
def get_player_price_futwiz(player_id, player_slug, fc_version=25):
    """
    Obtiene el precio de un jugador desde Futwiz para una versión específica de EA FC.
    fc_version: El año del juego (ej: 25 para FC25, 26 para FC26, 27 para FC27)
    """
    # La URL en futwiz sigue este formato general
    url = f"https://www.futwiz.com/en/fc{fc_version}/player/{player_slug}/{player_id}"
    logging.info(f"Iniciando consulta avanzada en Futwiz: {url}")
    
    try:
        # Simulación de navegador para evitar bloqueos de Cloudflare
        response = requests.get(url, impersonate="chrome110", timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscamos la clase específica que contiene el precio en Futwiz (.price-num)
            precio_element = soup.select_one('.price-num')
            
            if precio_element:
                precio = precio_element.text.strip()
                logging.info(f"Precio recuperado: {precio}")
                return precio
            else:
                return "No listado / Extinto"
        elif response.status_code == 404:
            return "El jugador no existe en esta versión o la URL es incorrecta."
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
                recomendacion, requisitos_extraidos = analizar_filtracion_y_recomendar(titulo)
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
                
                # 3. Alerta de Twitter para el ADMIN (Integración X)
                if recomendacion and "POSIBLES INVERSIONES" in recomendacion:
                    liga_detectada = requisitos_extraidos.get('liga', 'una liga top')
                    texto_tweet = f"🚨 ¡Nueva oportunidad detectada! Un jugador de {liga_detectada} está por dispararse. La alerta en tiempo real ya fue enviada a los usuarios VIP. Unite al bot: t.me/CardsBot"
                    
                    ADMIN_ID = os.getenv("ADMIN_ID")
                    if ADMIN_ID:
                        try:
                            await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"**[TWEET SUGERIDO]**\n\n{texto_tweet}", parse_mode='Markdown')
                            logging.info("Alerta de Twitter enviada al admin.")
                        except Exception as e:
                            logging.error(f"Error enviando alerta de Twitter al admin: {e}")
                    else:
                        logging.warning("No se ha configurado el ADMIN_ID en el archivo .env.")
                        
    except Exception as e:
        logging.error(f"Error en tarea periódica: {e}")

async def tarea_limpieza_vips(context: ContextTypes.DEFAULT_TYPE):
    """
    Tarea diaria (Cron) para buscar usuarios VIP vencidos y pasarlos a Free.
    Luego les envía un mensaje automático de renovación.
    """
    logging.info("Iniciando limpieza diaria de VIPs vencidos...")
    usuarios_vencidos = limpiar_vips_vencidos()
    
    if usuarios_vencidos:
        logging.info(f"Se encontraron {len(usuarios_vencidos)} suscripciones vencidas. Notificando...")
        mensaje = "Tu suscripción VIP ha finalizado. Usa /vip para renovar."
        
        for chat_id in usuarios_vencidos:
            try:
                await context.bot.send_message(chat_id=chat_id, text=mensaje)
                
                # Novedad: Si tenés el ID del Grupo VIP configurado, el bot los expulsa automáticamente.
                VIP_GROUP_ID = os.getenv("VIP_GROUP_ID")
                if VIP_GROUP_ID:
                    try:
                        # ban_chat_member expulsa al usuario. Podés usar unban_chat_member luego si querés que puedan volver a entrar si pagan de nuevo.
                        await context.bot.ban_chat_member(chat_id=int(VIP_GROUP_ID), user_id=chat_id)
                        await context.bot.unban_chat_member(chat_id=int(VIP_GROUP_ID), user_id=chat_id) # Esto solo lo elimina, no lo banea de por vida.
                        logging.info(f"Usuario {chat_id} expulsado del grupo VIP {VIP_GROUP_ID} por vencimiento.")
                    except Exception as e_kick:
                        logging.error(f"Error expulsando a {chat_id} del grupo VIP: {e_kick}")
                        
            except Exception as e:
                logging.error(f"Error notificando fin de VIP a {chat_id}: {e}")
    else:
        logging.info("No se encontraron suscripciones VIP vencidas hoy.")

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
    """
    Muestra información sobre la suscripción VIP
   
    """
    msj = (
        "💎 **Suscripción VIP** 💎\n\n"
        "• Alertas al instante (sin 15m de espera).\n"
        "• Análisis detallado de inversión.\n"
        "• Soporte 24/7.\n\n"
        "💰 **Precio Mensual:** $5 USD / 5.000 ARS\n"
        "💳 **Alias:** tu.bot.pago\n\n"
        "Escribe a @SoporteBot con tu comprobante para activar tu cuenta."
    )
    await update.message.reply_text(msj, parse_mode='Markdown')

async def setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    KAN-34: Comando de Admin Oculto para activar usuarios.
    Formato: /setvip [ID_DEL_USUARIO] [DIAS]
    """
    # Reemplazar con ID real para que solo nosotros podamos usarlo
    MI_ID_ADMIN = os.getenv("ADMIN_ID")
    if not MI_ID_ADMIN:
        await update.message.reply_text("⚠️ ADMIN_ID no configurado en el sistema.")
        return
        
    try:
        MI_ID_ADMIN = int(MI_ID_ADMIN)
    except ValueError:
        return
    
    if update.effective_user.id != MI_ID_ADMIN:
        await update.message.reply_text(f"⛔ Comando denegado. Tu ID de Telegram es {update.effective_user.id}, pero el ADMIN_ID en el archivo .env configurado es {MI_ID_ADMIN}. Reemplazalo en tu .env y reiniciá.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Uso: /setvip [ID_DEL_USUARIO] [DIAS]")
        return

    user_id = int(context.args[0])
    dias = int(context.args[1])

    if actualizar_vip_usuario(user_id, dias):
        await update.message.reply_text(f"✅ Usuario {user_id} actualizado a VIP por {dias} días.")
    else:
        await update.message.reply_text("❌ No se encontró al usuario en la base de datos.")

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
        res_msg += f"• {r['nombre']} ({r['rating']} - {r['version_carta']}) | Precio: {r['precio_actual']} 🪙\n"
    await update.message.reply_text(res_msg, parse_mode='Markdown')

async def id_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Devuelve el ID del chat actual (útil para grupos)"""
    chat_id = update.effective_chat.id
    tipo = update.effective_chat.type
    await update.message.reply_text(f"Este chat ({tipo}) tiene el ID: `{chat_id}`", parse_mode='Markdown')

# --- 6. EJECUCIÓN DEL SISTEMA ---
if __name__ == "__main__":
    if TOKEN:
        logging.info("Bot en línea. Iniciando JobQueue y Polling.")
        
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Iniciar revisión periódica del feed (cada 60 segundos)
        app.job_queue.run_repeating(chequear_feed_periodico, interval=60, first=10)
        
        # Tarea diaria: Ejecutar limpieza de VIPs a las 00:00 (hora local de Argentina, que es UTC-3)
        # 00:00 local ARG -> 03:00 UTC
        hora_ejecucion = datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc)
        app.job_queue.run_daily(tarea_limpieza_vips, time=hora_ejecucion)
        
        # Registro de comandos
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("precio", precio))
        app.add_handler(CommandHandler("vip", vip))
        app.add_handler(CommandHandler("setvip", setvip))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("buscar", buscar))
        app.add_handler(CommandHandler("id", id_chat))
        
        app.run_polling()
    else:
        print("❌ ERROR: Falta TELEGRAM_TOKEN en el archivo .env")
        logging.error("No se pudo iniciar el bot: Token ausente.")
