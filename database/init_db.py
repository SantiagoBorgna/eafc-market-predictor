import logging
from utils.logger import get_logger
logger = get_logger(__name__)
import sqlite3
import os

def init_db():
    db_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(db_dir, 'database.sqlite')
    
    logger.info(f"Conectando a la base de datos en: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    logger.info("Limpiando DB para FC26: dropeando tabla jugadores vieja...")
    cursor.execute('DROP TABLE IF EXISTS jugadores')

    # Tabla: JUGADORES
    logger.info("Creando tabla 'jugadores'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jugadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        futwiz_id INTEGER,
        slug TEXT,
        nombre TEXT NOT NULL,
        rating INTEGER,
        version_carta TEXT,
        liga TEXT,
        equipo TEXT,
        nacionalidad TEXT,
        posicion TEXT,
        posiciones_alternativas TEXT,
        precio_actual INTEGER,
        precio_historico_minimo INTEGER,
        ultima_actualizacion DATETIME
    )
    ''')

    # Tablas Relacionales Temporales
    table_names = ['clubes', 'ligas', 'nacionalidades', 'tipos_carta']
    for t in table_names:
        logger.info(f"Creando tabla '{t}'...")
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {t} (
            id TEXT PRIMARY KEY,
            nombre TEXT
        )
        ''')

    # Tabla: HISTORIAL_PRECIOS
    logger.info("Creando tabla 'historial_precios'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historial_precios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jugador_id INTEGER NOT NULL,
        precio INTEGER NOT NULL,
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (jugador_id) REFERENCES jugadores(id)
    )
    ''')

    # Tabla: SUSCRIPTORES
    logger.info("Creando tabla 'suscriptores'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suscriptores (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        tipo_chat TEXT DEFAULT 'private',
        is_vip BOOLEAN DEFAULT 0,
        fecha_vencimiento_vip DATETIME DEFAULT NULL
    )
    ''')
    
    # Tabla: REDDIT_LEAKS
    logger.info("Creando tabla 'reddit_leaks'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reddit_leaks (
        post_id TEXT PRIMARY KEY,
        titulo TEXT,
        fecha_detectada DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Crear índices para acelerar búsquedas
    logger.info("Creando índices...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jugador_slug ON jugadores(slug)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_historial_jugador ON historial_precios(jugador_id)')

    conn.commit()
    conn.close()
    logger.info("Base de datos inicializada correctamente con esquema relacional.")

if __name__ == '__main__':
    init_db()
