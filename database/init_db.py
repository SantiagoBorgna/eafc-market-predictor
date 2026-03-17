import sqlite3
import os

def init_db():
    # Asegurarnos de que estamos en el directorio correcto o crear un path absoluto
    # Esto asume que el script se corre desde la raíz del proyecto o desde la carpeta database
    db_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(db_dir, 'database.sqlite')
    
    print(f"Conectando a la base de datos en: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Tabla: JUGADORES
    print("Creando tabla 'jugadores'...")
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

    # Tabla: HISTORIAL_PRECIOS
    print("Creando tabla 'historial_precios'...")
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
    print("Creando tabla 'suscriptores'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suscriptores (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        tipo_chat TEXT DEFAULT 'private',
        is_vip BOOLEAN DEFAULT 0,
        fecha_vencimiento_vip DATETIME DEFAULT NULL
    )
    ''')
    
    # Crear índices para acelerar búsquedas
    print("Creando índices...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jugador_slug ON jugadores(slug)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_historial_jugador ON historial_precios(jugador_id)')

    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente.")

if __name__ == '__main__':
    init_db()