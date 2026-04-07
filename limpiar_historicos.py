import sys
import os
import time
from database.crud import limpiar_historial_antiguo
from utils.logger import get_logger

logger = get_logger(__name__)

if __name__ == '__main__':
    logger.info("🧹 Iniciando script de limpieza de base de datos...")
    
    dias = 30
    if len(sys.argv) > 1:
         try:
             dias = int(sys.argv[1])
         except ValueError:
             pass
             
    logger.info(f"⏰ Borrando historial de precios anteriores a {dias} días...")
    
    start_time = time.time()
    borrados = limpiar_historial_antiguo(dias)
    duracion = time.time() - start_time
    
    logger.info(f"✅ Se eliminaron {borrados} registros obsoletos en {duracion:.2f} segundos.")
