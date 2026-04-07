import sys
import os
import sqlite3
import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

def check_database_responsive(db_path):
    """Verifica simplemente si se puede conectar a la DB."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"HEALTHCHECK FALLIDO: No se pudo contectar a BD. Detalles: {e}")
        return False

def check_scrapers_recent_activity(db_path):
    """Verifica si ha habido actualizaciones de precio en las últimas 2 horas."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Hay jugadores en la base de datos?
        cursor.execute("SELECT COUNT(*) FROM jugadores")
        total_jugadores = cursor.fetchone()[0]
        
        if total_jugadores == 0:
            logger.info("HEALTHCHECK SALTEADO: No hay jugadores en la base de datos, imposible medir actualización.")
            conn.close()
            return True
            
        # Cuántos se actualizaron en las ultimas 2hs?
        cursor.execute('''
            SELECT COUNT(*) 
            FROM historial_precios 
            WHERE fecha_registro >= datetime('now', '-2 hours')
        ''')
        updates_recientes = cursor.fetchone()[0]
        conn.close()
        
        if updates_recientes == 0:
            logger.error("HEALTHCHECK FALLIDO: La base de datos responde pero ningún scraper guardó precios en las últimas 2 horas.")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"HEALTHCHECK FALLIDO: Error analizando actividad reciente. Detalles: {e}")
        return False

if __name__ == '__main__':
    logger.info("Iniciando rutina de Healthcheck...")
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'database.sqlite')
    
    if not os.path.exists(db_path):
        logger.error(f"HEALTHCHECK FALLIDO: Archivo de DB {db_path} no encontrado.")
        sys.exit(1)
        
    db_ok = check_database_responsive(db_path)
    if not db_ok:
        sys.exit(1)
        
    scraping_ok = check_scrapers_recent_activity(db_path)
    if not scraping_ok:
        sys.exit(1)
        
    logger.info("✅ HEALTHCHECK EXITOSO: El sistema está corriendo y los scrapers están frescos.")
    sys.exit(0)
