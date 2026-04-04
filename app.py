import os
import asyncio
import feedparser
import logging
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationBuilder, CommandHandler, ChatJoinRequestHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

# --- IMPORTS DE LOGICA EXTERNA (FUNDAMENTALES) ---
# Asegúrate de haber creado los archivos en /bot y /database como vimos antes
from bot.motor_reglas import analizar_filtracion_y_recomendar
from database.crud import (
    registrar_suscriptor, 
    obtener_suscriptores, 
    obtener_suscriptores_separados, 
    contar_jugadores, 
    buscar_jugador_por_nombre,
    actualizar_vip_usuario,
    limpiar_vips_vencidos
)
import datetime

# Variables globales para el bot
ultima_filtracion_vista = None

# --- 1. CONFIGURACIÓN DE ENTORNO Y LOGS ---
# Registro de actividad para debugear errores de conexión o de scraping
logging.basicConfig(
    filename='bot.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- 2. FUNCIONES DE BÚSQUEDA AVANZADA ---
def get_player_price_futwiz(player_id, player_slug, fc_version=26):
    """
    Obtiene el precio de un jugador desde Futwiz usando la API FC26.
    """
    url = f"https://www.futwiz.com/fc{fc_version}/players"
    headers = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8',
        'next-action': '7f14f6fdfcf68078a40fee222c3416dc2d522611c3',
    }
    
    # Buscamos por slug, devolviendo límite muy bajo
    data = f'[{fc_version},{{"mode":"search","filters":{{}},"search":"{player_slug}","pagination":{{"page":1,"limit":5}},"sorting":{{"field":"rating","direction":"desc"}}}}]'
    
    logging.info(f"Iniciando consulta API FC26 para: {player_slug}")
    
    try:
        response = requests.post(url, headers=headers, data=data, impersonate="chrome120", timeout=15)
        if response.status_code == 200:
            import re, json
            match = re.search(r'\[\{.*?"builder_name".*?\}\]', response.text)
            if match:
                jugadores_batch = json.loads(match.group(0))
                for g in jugadores_batch:
                    # Validamos el ID para asegurar exactitud
                    id_jugador = g.get('line_id') or g.get('pid')
                    if str(id_jugador) == str(player_id):
                        if g.get('prices') and g['prices'].get('console') and g['prices']['console'].get('bin'):
                            precio = str(g['prices']['console']['bin'])
                            logging.info(f"Precio recuperado API: {precio}")
                            return precio
            return "No listado / Extinto"
        else:
            return f"Error HTTP {response.status_code}"
            
    except Exception as e:
        logging.error(f"Error de red en get_player_price_futwiz API: {e}")
        return f"Error de conexión: {e}"

# --- 3. LÓGICA DE PRECIOS DEL BOT ---
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
    """(Obsoleta para FC26) Ya no extrae de URL por SPA."""
    # Para ser retrocompatible si alguien pega un URL de la web, podríamos parsear la URL
    # y enviarla al API, pero como fallback preventivo lo mandamos al anterior o 0
    return 0

# --- 4. TAREAS AUTOMÁTICAS: (TEXTO VIP) ---

async def enviar_alerta_retrasada(context: ContextTypes.DEFAULT_TYPE):
    """
    Envía la alerta a usuarios Free tras 15 minutos.
    Concatena el mensaje de invitación a VIP.
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

async def tarea_reddit(context: ContextTypes.DEFAULT_TYPE):
    from scrapers.tracker_reddit import chequear_filtraciones_reddit
    from database.crud import obtener_suscriptores_separados
    
    filtracion = chequear_filtraciones_reddit()
    if not filtracion:
        return
        
    mensaje_vip = f"🚨 **FILTRACIÓN CONFIRMADA** 🚨\n\n📌 **{filtracion['titulo']}**\n\n🔗 [{filtracion['url']}]({filtracion['url']})"
    mensaje_gratis = f"🚨 **FILTRACIÓN** 🚨\n\n📌 **{filtracion['titulo']}**\n\n🔗 [{filtracion['url']}]({filtracion['url']})\n\n💡 *Upgradeá con /vip para no llegar tarde al próximo subidón de precio!*"
    
    listas = obtener_suscriptores_separados()
    vips = listas.get('vip', [])
    gratis = listas.get('gratis', [])
    
    VIP_GROUP_ID = os.getenv("VIP_GROUP_ID")
    
    for c_id in vips:
        try:
            await context.bot.send_message(chat_id=c_id, text=mensaje_vip, parse_mode='Markdown', disable_web_page_preview=False)
        except Exception as e:
            logging.error(f"Error enviando leak a VIP {c_id}: {e}")

    # Doble check si el supergrupo de VIP no levantó is_vip explícito por x razón
    if VIP_GROUP_ID and int(VIP_GROUP_ID) not in vips:
        try:
            await context.bot.send_message(chat_id=int(VIP_GROUP_ID), text=mensaje_vip, parse_mode='Markdown', disable_web_page_preview=False)
        except Exception:
            pass

    # Programamos para los gratis (15 minutos)
    if gratis:
        context.job_queue.run_once(enviar_alertas_retrasadas, 900, data={'usuarios': gratis, 'mensaje': mensaje_gratis})

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
    
    es_nuevo = registrar_suscriptor(chat_id, username, tipo)
    
    if tipo == 'private':
        msj = (
            "¡Bienvenido a **FutMetrics**! ⚽📈\n\n"
            "Gracias por registrarte. Este bot detecta automáticamente filtraciones y caídas de mercado en EA FC 25.\n\n"
            "Para continuar, elegí tu plan haciendo clic en uno de los comandos:\n\n"
            "🆓 /gratis - Recibís las alertas en el grupo gratuito con 15 minutos de retraso.\n"
            "💎 /vip - Recibís las alertas al instante, con oportunidades de inversión seguras.\n\n"
            "💡 *Tip: Podés abrir el botón Menú de Telegram o usar /ayuda para ver mis comandos.*"
        )
        await update.message.reply_text(msj, parse_mode='Markdown')
        return
        
    if es_nuevo:
        await update.message.reply_text("¡Bienvenido! El grupo ya está suscrito a las Alertas. 🛎️")

async def gratis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el enlace al grupo gratis"""
    link = os.getenv("FREE_GROUP_LINK", "https://t.me/AcaPonesTuLinkGratis")
    msj = (
        "¡Excelente elección! 🆓\n\n"
        f"Sumate a nuestro grupo gratuito haciendo clic acá:\n🔗 [Entrar al Grupo Gratis]({link})\n\n"
        "💡 *Recordá que en ese grupo las alertas llegan con 15 minutos de retraso.*\n\n"
        "💎 ¿Te arrepentiste y querés las alertas al instante? Tocá /vip"
    )
    await update.message.reply_text(msj, parse_mode='Markdown', disable_web_page_preview=True)

async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de la suscripción del usuario"""
    if update.effective_chat.type != 'private':
        return # Solo respondemos al estado por MD para no spamear grupos
        
    chat_id = update.effective_chat.id
    from database.crud import obtener_estado_suscripcion
    estado = obtener_estado_suscripcion(chat_id)
    
    MI_ID_ADMIN = os.getenv("ADMIN_ID")
    es_admin = (str(chat_id) == str(MI_ID_ADMIN))
    
    if not estado:
        await update.message.reply_text("❌ No estás registrado en la base de datos. Enviá /start para registrarte primero.")
        return
        
    if estado['is_vip'] or es_admin:
        # El admin no tiene vencimiento aplicable en la DB usualmente, o podría tener NULL
        vence = estado['vencimiento'] if estado['vencimiento'] else "Ilimitado"
        msj = (
            "👑 **Estado de tu Suscripción: VIP** 👑\n\n"
            "✅ Tenés acceso completo a las alertas en tiempo real.\n"
            f"📅 **Tu plan vence el:** {vence}\n\n"
            "💡 *Si necesitás renovar, podés ver la info de pago usando /vip*"
        )
    else:
        msj = (
            "🆓 **Estado de tu Suscripción: GRATIS** 🆓\n\n"
            "Actualmente recibís las alertas con retraso en nuestro grupo gratuito.\n\n"
            "Para recibir las notificaciones **al instante** y comprar jugadores antes de que suban de precio, pasate a nuestro plan Premium tocando acá:\n"
            "👉 /vip"
        )
        
    await update.message.reply_text(msj, parse_mode='Markdown')

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú de ayuda con todos los comandos"""
    msj = (
        "🤖 **Menú de Ayuda - FutMetrics**\n\n"
        "Comandos disponibles para interactuar conmigo:\n"
        "🔸 /start - Menú principal y elección de planes.\n"
        "🔸 /estado - Revisa tu plan actual y vencimiento.\n"
        "🔸 /vip - Info sobre el plan Premium.\n"
        "🔸 /gratis - Entrá a la comunidad gratuita.\n"
        "🔸 /buscar - Buscador premium de cartas de FC 25.\n"
        "🔸 /soporte - Hablá con un humano si tenés dudas o querés pagar.\n"
        "🔸 /id - Te devuelve tu Telegram ID único."
    )
    await update.message.reply_text(msj, parse_mode='Markdown')

async def soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el contacto de soporte"""
    contacto = os.getenv("SUPPORT_CONTACT", "@TuAdminSoporte")
    msj = (
        f"👨‍💻 **Soporte y Contacto**\n\n"
        f"Si tenés dudas, problemas técnicos o querés enviar el comprobante de tu pago VIP, escribile un mensaje privado a:\n"
        f"👉 {contacto}\n\n"
        f"Recordá siempre enviar tu *ID numérico* para que puedan encontrarte más rápido: `{update.effective_chat.id}`"
    )
    await update.message.reply_text(msj, parse_mode='Markdown')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de admin para enviar mensajes masivos a todos los usuarios."""
    MI_ID_ADMIN = os.getenv("ADMIN_ID")
    if str(update.effective_chat.id) != str(MI_ID_ADMIN):
        return # Comando oculto
        
    if not context.args:
        await update.message.reply_text("⚠️ Uso: /broadcast Mensaje que querés mandar a todos los usuarios registrados.")
        return
        
    mensaje_masivo = " ".join(context.args)
    mensaje_masivo = f"📢 **Mensaje Institucional** 📢\n\n{mensaje_masivo}"
    
    from database.crud import obtener_suscriptores
    todos = obtener_suscriptores()
    
    if not todos:
        await update.message.reply_text("⚠️ No hay ningún usuario registrado en la base de datos.")
        return
        
    enviados = 0
    errores = 0
    await update.message.reply_text(f"⏳ Enviando broadcast masivo a {len(todos)} chats... esto puede demorar.")
    
    import asyncio
    for c_id in todos:
        try:
            await context.bot.send_message(chat_id=c_id, text=mensaje_masivo, parse_mode='Markdown', disable_web_page_preview=True)
            enviados += 1
            await asyncio.sleep(0.05) # Pausa estricta anti-spam de Telegram (máximo 30 mensajes/segundo)
        except Exception as e:
            errores += 1
            logging.error(f"Broadcast fallo para el ID {c_id}")
            
    await update.message.reply_text(f"✅ Broadcast finalizado con éxito.\n✔️ Enviados: {enviados}\n❌ Fallaron: {errores}")

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra información sobre la suscripción VIP y da a elegir la región para pricing regional
    """
    msj = (
        "💎 **Suscripción VIP** 💎\n\n"
        "• Alertas al instante.\n"
        "• Tracking en tiempo real de SBC Leaks.\n"
        "• Descubridor e Historial de precios.\n\n"
        "Para continuar, seleccioná desde dónde nos hablás:"
    )
    
    teclado = [
        [InlineKeyboardButton("🇦🇷 Soy de Argentina", callback_data='vip_ar')],
        [InlineKeyboardButton("🌍 Soy de otro país", callback_data='vip_int')]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)
    
    await update.message.reply_text(msj, parse_mode='Markdown', reply_markup=reply_markup)

async def botones_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las respuestas de los botones de la suscripción VIP"""
    query = update.callback_query
    await query.answer() # Evita que el botón de Telegram se quede "cargando"
    
    support_contact = os.getenv("SUPPORT_CONTACT", "@TuUsuarioAdmin")
    
    if query.data == 'vip_inicio':
        msj = (
            "💎 **Suscripción VIP** 💎\n\n"
            "• Alertas al instante.\n"
            "• Tracking en tiempo real de SBC Leaks.\n"
            "• Descubridor e Historial de precios.\n\n"
            "Para continuar, seleccioná desde dónde nos hablás:"
        )
        teclado = [
            [InlineKeyboardButton("🇦🇷 Soy de Argentina", callback_data='vip_ar')],
            [InlineKeyboardButton("🌍 Soy de otro país", callback_data='vip_int')]
        ]
        reply_markup = InlineKeyboardMarkup(teclado)
        await query.edit_message_text(text=msj, parse_mode='Markdown', reply_markup=reply_markup)
        
    elif query.data == 'vip_ar':
        mp_link = os.getenv("MP_SUBSCRIPTION_LINK", "Configurar link en .env")
        alias_pago = os.getenv("PAYMENT_ALIAS", "Tu alias no configurado en .env")
        msj = (
            "💎 **Suscripción VIP** 💎\n\n"
            "💰 **Precio Mensual:** $5.000 ARS\n\n"
            "Podés elegir entre **dos métodos** para abonar:\n\n"
            "1️⃣ **Débito Automático Mensual** (Mercado Pago)\n"
            "No tenés que acordarte de pagar todos los meses. Suscribirte al débito automático tocando el enlace:\n"
            f"👉 [Suscribirme con Mercado Pago]({mp_link})\n\n"
            "2️⃣ **Transferencia Manual 1 Mes**\n"
            f"💳 **Alias:** {alias_pago}\n\n"
            "**¿Cómo activo mi plan en ambos casos?**\n"
            "1. Realizá la suscripción o transferencia.\n"
            f"2. Contactá a nuestro Admin ({support_contact}) con tu comprobante y enviale este ID tuyo: `{query.message.chat.id}`\n"
            "3. Apenas el Admin lo verifique, **este bot te va a habilitar el acceso VIP** por 30 días acá mismo.\n\n"
            "🆓 ¿Preferís empezar sin pagar? Tocá /gratis para ir a la comunidad gratuita."
        )
        teclado = [[InlineKeyboardButton("⬅️ Volver", callback_data='vip_inicio')]]
        await query.edit_message_text(text=msj, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(teclado))
        
    elif query.data == 'vip_int':
        msj = (
            "💎 **Suscripción VIP Internacional** 💎\n\n"
            "💰 **Precio Mensual:** $5 USD\n\n"
            "Elegí tu método de pago preferido para ver las instrucciones exactas:"
        )
        teclado = [
            [InlineKeyboardButton("🟡 USDT / Binance", callback_data='vip_binance')],
            [InlineKeyboardButton("🔵 PayPal", callback_data='vip_paypal')],
            [InlineKeyboardButton("⬅️ Volver", callback_data='vip_inicio')]
        ]
        reply_markup = InlineKeyboardMarkup(teclado)
        await query.edit_message_text(text=msj, parse_mode='Markdown', reply_markup=reply_markup)

    elif query.data == 'vip_binance':
        binance_addr = os.getenv("BINANCE_ADDRESS", "Tu dirección no configurada en .env")
        msj = (
            "🟡 **Pago Cripto (USDT)** 🟡\n\n"
            "¡Perfecto! Sigue estos pasos para activar tu mes:\n\n"
            "1️⃣ Mandá **5 USDT** a la siguiente dirección:\n"
            f"`{binance_addr}`\n\n"
            "⚠️ **IMPORTANTE:** Asegurate de usar la red **BNB Smart Chain (BEP20)**.\n\n"
            "2️⃣ Cuando termines, mandá una captura del pago o el ID de transacción (TxID) a nuestro admin:\n"
            f"👉 {support_contact}\n\n"
            f"3️⃣ Pasale tu número de ID para que te habilite el bot instantáneamente: `{query.message.chat.id}`"
        )
        teclado = [[InlineKeyboardButton("⬅️ Volver", callback_data='vip_int')]]
        await query.edit_message_text(text=msj, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(teclado))
    
    elif query.data == 'vip_paypal':
        paypal_link = os.getenv("PAYPAL_LINK", "https://paypal.me/AcaPonTuLinkDePaypal")
        msj = (
            "🔵 **Pago con PayPal** 🔵\n\n"
            "¡Excelente! Sigue estos pasos para comenzar a ganar:\n\n"
            "1️⃣ Ingresá al siguiente enlace y aboná **$5 USD**:\n"
            f"🔗 [Abonar Suscripción]({paypal_link})\n\n"
            "2️⃣ Cuando termines, enviale el comprobante del pago a nuestro admin:\n"
            f"👉 {support_contact}\n\n"
            f"3️⃣ Pasale tu número de ID para que te habilite el bot instantáneamente: `{query.message.chat.id}`"
        )
        teclado = [[InlineKeyboardButton("⬅️ Volver", callback_data='vip_int')]]
        await query.edit_message_text(text=msj, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(teclado))

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
        await update.message.reply_text("⚠️ Uso: /setvip [ID_DEL_USUARIO] [DIAS]\nEjemplo: /setvip 123456789 30")
        return

    try:
        user_id = int(context.args[0])
        dias = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Error: El ID del usuario y los días deben ser números enteros. Recordale al usuario que toque /vip para pasarte su ID numérico.")
        return

    if actualizar_vip_usuario(user_id, dias):
        await update.message.reply_text(f"✅ Usuario {user_id} actualizado a VIP por {dias} días en la base de datos.")
        
        # Le enviamos el acceso por privado al usuario
        link = os.getenv("VIP_GROUP_LINK", "https://t.me/AcaPonesTuLinkVIP")
        mensaje_exito = (
            "🎉 <b>¡Tu pago fue aprobado!</b> 🎉\n\n"
            "Ya tenés el plan VIP activo. Unite al grupo privado tocando acá abajo:\n"
            f"🔗 <a href='{link}'>Acceso VIP Exclusivo</a>\n\n"
            f"⏳ Tu suscripción dura {dias} días."
        )
        try:
            # Usando HTML en lugar de Markdown porque Markdown en Telegram se rompe si el enlace VIP contiene _ o símbolos raros
            await context.bot.send_message(chat_id=user_id, text=mensaje_exito, parse_mode='HTML')
            await update.message.reply_text(f"✉️ El usuario recibió su link mágico de entrada por privado.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ El usuario es VIP en la BD, pero NO le pudimos mandar el link por MD (tal vez detuvo el bot). Error: {e}")
            
    else:
        await update.message.reply_text("❌ No se encontró al usuario en la base de datos.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estadísticas globales del sistema"""
    total_j = contar_jugadores()
    total_s = len(obtener_suscriptores())
    await update.message.reply_text(f"📊 **Stats:**\n- Jugadores: {total_j}\n- Suscriptores: {total_s}", parse_mode='Markdown')

# --- ESTADOS DE LA CONVERSACIÓN BUSCAR ---
BUSCAR_NOMBRE, BUSCAR_VERSION = range(2)

async def buscar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia la conversación para buscar una carta, exclusivo para VIP"""
    chat_id = update.effective_chat.id
    from database.crud import obtener_estado_suscripcion
    estado_sub = obtener_estado_suscripcion(chat_id)
    es_admin = (str(chat_id) == str(os.getenv("ADMIN_ID")))
    
    if not estado_sub or (not estado_sub['is_vip'] and not es_admin):
        await update.message.reply_text("💎 **¡Función Premium!** 💎\n\nEl buscador de jugadores y precios en base de datos es una herramienta exclusiva para usuarios VIP.\n\nTocá /vip para actualizar tu plan y desbloquear esta función.")
        return ConversationHandler.END

    await update.message.reply_text("🔎 **Búsqueda de Jugador VIP**\n\nPor favor, escribí el **nombre** del jugador que buscás (ej: Messi, Neymar...).", parse_mode='Markdown')
    return BUSCAR_NOMBRE

async def buscar_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el nombre y arma un menú de botones con las versiones encontradas"""
    nombre = update.message.text
    context.user_data['buscar_nombre'] = nombre
    
    from database.crud import buscar_jugador_por_nombre
    resultados = buscar_jugador_por_nombre(nombre)
    
    if not resultados:
        await update.message.reply_text(f"❌ No encontré ninguna carta de '{nombre}'. Tocá /buscar para intentar de nuevo.")
        context.user_data.clear()
        return ConversationHandler.END
        
    versiones = list(set(r['version_carta'] for r in resultados))
    versiones.sort() # Ordenar alfabéticamente
    
    # Si solo hay una versión, la mostramos directamente para ahorrarle un paso al usuario
    if len(versiones) == 1:
        res_msg = f"🔍 **Resultados para '{nombre}':**\n\n"
        for r in resultados[:10]:
            res_msg += f"• {r['nombre']} ({r['rating']} - {r['version_carta']}) | Precio: {r['precio_actual']} 🪙\n"
            
        await update.message.reply_text(res_msg, parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

    # Guardar temporalmente las versiones para los botones
    context.user_data['versiones'] = versiones
    
    # Armar teclado dinámico, 2 botones por fila
    teclado = []
    fila_actual = []
    for idx, v in enumerate(versiones):
        fila_actual.append(InlineKeyboardButton(v, callback_data=f"v_{idx}"))
        if len(fila_actual) == 2:
            teclado.append(fila_actual)
            fila_actual = []
    if fila_actual:
        teclado.append(fila_actual)
        
    teclado.append([InlineKeyboardButton("🌟 Todas", callback_data="v_todas")])
    
    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text("Genial. Encontré estas versiones. Elegí la que buscás:", reply_markup=reply_markup)
    return BUSCAR_VERSION

async def buscar_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realiza la búsqueda final con la versión seleccionada por botón o texto"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        accion = query.data
        
        versiones = context.user_data.get('versiones', [])
        if accion == "v_todas":
            version = "cualquiera"
        else:
            try:
                idx = int(accion.split('_')[1])
                version = versiones[idx]
            except:
                version = "cualquiera"
    else:
        version = update.message.text

    nombre = context.user_data.get('buscar_nombre', '')
    
    from database.crud import buscar_jugador_por_nombre
    resultados = buscar_jugador_por_nombre(nombre)
    
    if version.lower() != 'cualquiera':
        resultados = [r for r in resultados if version.lower() in r['version_carta'].lower()]
        
    if not resultados:
        msg = f"❌ No encontré ninguna carta de {nombre} (Versión: {version}). Tocá /buscar para intentar de nuevo."
        if update.callback_query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        context.user_data.clear()
        return ConversationHandler.END
        
    res_msg = f"🔍 **Resultados para '{nombre}':**\n\n"
    for r in resultados[:10]:
        res_msg += f"• {r['nombre']} ({r['rating']} - {r['version_carta']}) | Precio: {r['precio_actual']} 🪙\n"
        
    if update.callback_query:
        await query.edit_message_text(res_msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(res_msg, parse_mode='Markdown')
        
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la conversación actual"""
    await update.message.reply_text("❌ Operación cancelada.")
    context.user_data.clear()
    return ConversationHandler.END

async def id_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Devuelve el ID del chat actual (útil para grupos)"""
    chat_id = update.effective_chat.id
    tipo = update.effective_chat.type
    await update.message.reply_text(f"Tu ID es: `{chat_id}`", parse_mode='Markdown')

async def manejar_solicitud_union(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Aprueba o rechaza automáticamente a los que intentan unirse al VIP con el link compartido.
    Requisito: Activar "Aprobar nuevos miembros" / "Solicitudes de unión" en Telegram para el link de invitación.
    """
    request = update.chat_join_request
    if not request: return
    
    user_id = request.from_user.id
    chat_id = request.chat.id
    
    VIP_GROUP_ID = os.getenv("VIP_GROUP_ID")
    
    # Solo interceptamos solicitudes dirigidas al grupo VIP
    if VIP_GROUP_ID and str(chat_id) == VIP_GROUP_ID:
        from database.crud import obtener_estado_suscripcion
        estado_sub = obtener_estado_suscripcion(user_id)
        es_admin = (str(user_id) == os.getenv("ADMIN_ID"))
        
        # Si es admin o su estado is_vip es verdadero
        if es_admin or (estado_sub and estado_sub['is_vip']):
            try:
                await request.approve()
                logging.info(f"Usuario {user_id} aprobado para entrar al grupo VIP.")
            except Exception as e:
                logging.error(f"Error aprobando solicitud de {user_id}: {e}")
        else:
            try:
                await request.decline()
                logging.info(f"Usuario {user_id} rechazado del VIP (no tiene plan).")
                await context.bot.send_message(
                    chat_id=user_id, 
                    text="❌ <b>Acceso Denegado:</b> Tu solicitud para unirte al VIP fue rechazada. No tenés una suscripción activa o ya se venció. Si recién pagaste, enviale el comprobante al @Admin y pasale tu ID numérico usando /vip por acá.", 
                    parse_mode='HTML'
                )
            except Exception as e:
                logging.error(f"Error rechazando/avisando a {user_id}: {e}")

from telegram import BotCommand
from telegram.ext import Application

async def setup_commands(application: Application):
    """Configura el menú nativo de comandos de Telegram"""
    comandos = [
        BotCommand("start", "Menú principal y elección de planes"),
        BotCommand("estado", "Tu plan actual y fecha de corte"),
        BotCommand("vip", "Info sobre el plan Premium"),
        BotCommand("gratis", "Unirte a la comunidad gratuita"),
        BotCommand("buscar", "Buscador de cartas"),
        BotCommand("soporte", "Atención al cliente y pagos"),
        BotCommand("ayuda", "Mostrar manual del bot"),
        BotCommand("id", "Te devuelve tu Telegram ID")
    ]
    await application.bot.set_my_commands(comandos)

# --- 6. EJECUCIÓN DEL SISTEMA ---
if __name__ == "__main__":
    if TOKEN:
        logging.info("Bot en línea. Iniciando JobQueue y Polling.")
        
        # Inicializa el bot y la aplicación
        app = ApplicationBuilder().token(TOKEN).post_init(setup_commands).build()
        
        # Iniciar revisión periódica del feed (cada 60 segundos)
        app.job_queue.run_repeating(chequear_feed_periodico, interval=60, first=10)
        
        # Scraper anti-bloqueo de Telegram para Leaks de Reddit, cada 5 minutos
        app.job_queue.run_repeating(tarea_reddit, interval=300, first=30)
        
        # Tarea diaria: Ejecutar limpieza de VIPs a las 00:00 (hora local de Argentina, que es UTC-3)
        # 00:00 local ARG -> 03:00 UTC
        hora_ejecucion = datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc)
        app.job_queue.run_daily(tarea_limpieza_vips, time=hora_ejecucion)
        
        # Registro de comandos
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("ayuda", ayuda))
        app.add_handler(CommandHandler("soporte", soporte))
        app.add_handler(CommandHandler("broadcast", broadcast))
        app.add_handler(CommandHandler("gratis", gratis))
        app.add_handler(CommandHandler("estado", estado))
        app.add_handler(CommandHandler("vip", vip))
        app.add_handler(CallbackQueryHandler(botones_vip, pattern='^vip_')) # Capta los botones vip_ar y vip_int
        app.add_handler(CommandHandler("setvip", setvip)) # Registro KAN-34
        app.add_handler(CommandHandler("stats", stats))
        # Conversation Handler para Buscar
        buscar_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('buscar', buscar_start)],
            states={
                BUSCAR_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_nombre)],
                BUSCAR_VERSION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_version),
                    CallbackQueryHandler(buscar_version, pattern='^v_')
                ],
            },
            fallbacks=[CommandHandler('cancelar', cancelar)]
        )
        app.add_handler(buscar_conv_handler)
        
        app.add_handler(CommandHandler("id", id_chat))
        
        # Handler para filtrar gente que entra al grupo VIP
        app.add_handler(ChatJoinRequestHandler(manejar_solicitud_union))
        
        app.run_polling()
    else:
        print("❌ ERROR: Falta TELEGRAM_TOKEN en el archivo .env")
        logging.error("No se pudo iniciar el bot: Token ausente.")
