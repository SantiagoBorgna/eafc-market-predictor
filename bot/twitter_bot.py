import os
import logging
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def publicar_tweet(texto):
    """
    Publica un tweet utilizando un Webhook (IFTTT / Make.com) 
    para evadir el muro de pago de la API REST oficial de X.
    """
    webhook_url = os.getenv("TWITTER_WEBHOOK_URL") 
    
    if not webhook_url or webhook_url.strip() == "":
        logging.error("No se ha configurado TWITTER_WEBHOOK_URL en el archivo .env.")
        print("❌ Error: Falla al publicar tweet. Falta TWITTER_WEBHOOK_URL en .env")
        return False
        
    try:
        print(f"Enviando señal de tweet a la plataforma: '{texto}'...")
        
        # Enviamos un JSON simple a nuestro webhook (ej: { "value1": "Texto del tweet..." } para IFTTT)
        payload = {
            "value1": texto
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        
        # Validamos que el webhook haya respondido bien (2xx)
        if response.status_code >= 200 and response.status_code < 300:
            logging.info("✅ Señal de Tweet enviada con éxito al Webhook. Status: %s", response.status_code)
            print("✅ Webhook disparado. Tweet enviado a publicación automágica.")
            return True
        else:
            logging.error("❌ Error del servidor Webhook: %s - %s", response.status_code, response.text)
            print(f"❌ Error en el Webhook: Status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logging.error("❌ Fallo crítico al conectar con el Webhook: %s", e)
        print(f"❌ Fallo crítico de conexión a internet con el Webhook: {e}")
        return False

# Bloque de prueba
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Iniciando prueba de Webhook...")
    print("Asegúrate de haber puesto tu URL de Make/IFTTT en el .env como TWITTER_WEBHOOK_URL")
    # publicar_tweet("Hola X desde IFTTT/Make. Probando bot! 🤖🚀")