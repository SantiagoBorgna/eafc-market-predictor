import os
import asyncio
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CONFIGURACIÓN ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- LÓGICA DE PRECIOS (KAN-8 y KAN-9) ---
def limpiar_precio(precio_texto):
    """Convierte texto a entero (ej: '15.5K' -> 15500)"""
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
    """Retorna el precio entero"""
    try:
        response = requests.get(url_jugador, impersonate="chrome110", timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            precio_element = soup.select_one('.price-num')
            if precio_element:
                return limpiar_precio(precio_element.text.strip())
        return 0
    except:
        return 0

# --- LÓGICA DEL BOT (KAN-12) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start"""
    await update.message.reply_text("Hola, estoy listo para predecir el mercado")

async def precio_messi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando extra para probar que todo funciona"""
    await update.message.reply_text("Buscando precio de Messi...")
    url = "https://www.futwiz.com/en/fc25/player/lionel-messi/45"
    precio = obtener_precio_actual(url)
    await update.message.reply_text(f"💰 Messi cuesta actualmente: {precio} monedas.")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: No hay TOKEN en el archivo .env")
    else:
        print("🚀 Bot iniciado. Esperando mensajes...")
        # Construimos el bot
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Agregamos los comandos
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("messi", precio_messi))
        
        # El bot se queda escuchando 
        app.run_polling()