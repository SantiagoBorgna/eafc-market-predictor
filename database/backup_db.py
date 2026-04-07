import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import os
import shutil
from datetime import datetime

def backup_database():
    """
    Copia el archivo database.sqlite a la carpeta backups/
    agregando un timestamp con la fecha de hoy.
    """
    # Determinamos las rutas basadas en la ubicación de este script
    db_dir = os.path.dirname(os.path.abspath(__file__))
    source_db = os.path.join(db_dir, 'database.sqlite')
    backup_dir = os.path.join(db_dir, 'backups')
    
    # Crear el directorio de backups si no existe
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        logger.info(f"Carpeta de backups creada: {backup_dir}")
        
    # Formatear la fecha actual (ej. 20261014)
    timestamp = datetime.now().strftime('%Y%m%d')
    backup_filename = f"db_backup_{timestamp}.sqlite"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # Verificar que el archivo original exista antes de copiar
    if os.path.exists(source_db):
        try:
            shutil.copy2(source_db, backup_path)
            logger.info(f"✅ Backup creado exitosamente en: {backup_path}")
        except Exception as e:
            logger.error(f"❌ Error al realizar el backup: {e}")
    else:
        logger.warning(f"⚠️ Atención: No se encontró la base de datos '{source_db}'.")

if __name__ == "__main__":
    backup_database()
