import sqlite3
import os

def _get_connection():
    # Helper para conectarse apuntando siempre al archivo correcto
    db_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(db_dir, 'database.sqlite')
    # Aumentamos el timeout a 20 segundos para evitar errores "database is locked" en un entorno asíncrono
    return sqlite3.connect(db_path, timeout=20.0)

def insertar_jugador(futwiz_id, slug, nombre, rating, version_carta, liga, equipo, nacionalidad, posicion, posiciones_alternativas="", precio_actual=0, precio_historico_minimo=0):
    """
    Inserta un nuevo jugador en la base de datos y retorna su ID interno.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    query = '''
        INSERT INTO jugadores (
            futwiz_id, slug, nombre, rating, version_carta, liga, equipo, 
            nacionalidad, posicion, posiciones_alternativas, precio_actual, precio_historico_minimo, ultima_actualizacion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    '''
    parametros = (
        futwiz_id, slug, nombre, rating, version_carta, liga, equipo, 
        nacionalidad, posicion, posiciones_alternativas, precio_actual, precio_historico_minimo
    )
    
    try:
        cursor.execute(query, parametros)
        conn.commit()
        jugador_id = cursor.lastrowid
        return jugador_id
    except sqlite3.Error as e:
        print(f"Error al insertar el jugador {nombre}: {e}")
        return None
    finally:
        conn.close()

def buscar_jugador_por_requisito(criterios):
    """
    Busca jugadores en la base de datos basado en un diccionario de criterios.
    Uso: buscar_jugador_por_requisito({'rating': 90, 'nacionalidad': 'Argentina'})
    """
    conn = _get_connection()
    # Para obtener un diccionario en vez de una tupla devolvemos las filas así:
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    query = "SELECT * FROM jugadores WHERE 1=1"
    valores = []
    
    for columna, valor in criterios.items():
        query += f" AND {columna} = ?"
        valores.append(valor)
        
    try:
        cursor.execute(query, valores)
        resultados = cursor.fetchall()
        # Convertimos a una lista de diccionarios para que sea más fácil de usar
        return [dict(row) for row in resultados]
    except sqlite3.Error as e:
        print(f"Error en la búsqueda: {e}")
        return []
    finally:
        conn.close()

def actualizar_precio_jugador(jugador_id, nuevo_precio):
    """
    Actualiza el precio de un jugador existente y valida si rompió su mínimo histórico.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Obtener el precio mínimo histórico actual
        cursor.execute("SELECT precio_historico_minimo FROM jugadores WHERE id = ?", (jugador_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return False
            
        precio_historico_minimo = resultado[0]
        
        # 2. Si el nuevo precio es 0, lo ignoramos (suele pasar si escrapea un error)
        if nuevo_precio == 0:
            return False
            
        # 3. Determinar si hay un nuevo mínimo
        precio_historico_minimo_actualizado = precio_historico_minimo
        # Si el histórico era 0 o el nuevo es menor al histórico
        if precio_historico_minimo == 0 or nuevo_precio < precio_historico_minimo:
            precio_historico_minimo_actualizado = nuevo_precio
            
        # 4. Actualizar al jugador
        cursor.execute('''
            UPDATE jugadores 
            SET precio_actual = ?, 
                precio_historico_minimo = ?,
                ultima_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (nuevo_precio, precio_historico_minimo_actualizado, jugador_id))
        
        # 5. Insertar en el historial
        cursor.execute('''
            INSERT INTO historial_precios (jugador_id, precio)
            VALUES (?, ?)
        ''', (jugador_id, nuevo_precio))
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        print(f"Error actualizando precio: {e}")
        return False
    finally:
        conn.close()

def eliminar_jugador(jugador_id):
    """
    Elimina permanentemente a un jugador (y opcionalmente podria eliminar su historial de precios).
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    try:
        # Por la restriccion de clave foranea, primero borramos su historial
        cursor.execute("DELETE FROM historial_precios WHERE jugador_id = ?", (jugador_id,))
        # Luego borramos al jugador
        cursor.execute("DELETE FROM jugadores WHERE id = ?", (jugador_id,))
        
        conn.commit()
        # Retornamos cuantas filas se borraron para saber si existia
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error al eliminar jugador: {e}")
        return False
    finally:
        conn.close()

def obtener_todos_los_jugadores():
    """
    Devuelve todos los jugadores en la base de datos.
    Muy útil para un script "Updater" que recorra la base de datos actualizando a todos cada 24 horas.
    """
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM jugadores")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Error obteniendo todos los jugadores: {e}")
        return []
    finally:
        conn.close()

def obtener_jugador_por_id(jugador_id):
    """
    Devuelve un unico jugador buscando por su ID interno.
    """
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM jugadores WHERE id = ?", (jugador_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Error buscando al jugador {jugador_id}: {e}")
        return None
    finally:
        conn.close()

def obtener_jugador_por_futwiz_id(futwiz_id):
    """
    Devuelve un jugador buscando por su ID de Futwiz (ideal para scrapers).
    """
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM jugadores WHERE futwiz_id = ?", (futwiz_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Error buscando al jugador experto por futwiz_id {futwiz_id}: {e}")
        return None
    finally:
        conn.close()

def registrar_suscriptor(chat_id, username=None, tipo_chat='private'):
    """
    Guarda un nuevo ID de chat en la base de datos para recibir alertas.
    Ignora el insert si el usuario ya está suscrito.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO suscriptores (chat_id, username, tipo_chat, is_vip) VALUES (?, ?, ?, 0)", 
            (chat_id, username, tipo_chat)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error al registrar el suscriptor: {e}")
        return False
    finally:
        conn.close()

def obtener_suscriptores():
    """
    Devuelve la lista de todos los IDs de chat suscritos a las alertas.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT chat_id FROM suscriptores")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Error al obtener suscriptores: {e}")
        return []
    finally:
        conn.close()

def obtener_suscriptores_separados():
    """
    Devuelve un diccionario con dos listas de IDs de chat separadas:
    'vip': Usuarios con is_vip = True (1)
    'gratis': Usuarios con is_vip = False (0)
    """
    conn = _get_connection()
    cursor = conn.cursor()
    Listas = {'vip': [], 'gratis': []}
    
    try:
        import os
        admin_id_env = os.getenv("ADMIN_ID")
        admin_id = int(admin_id_env) if admin_id_env and admin_id_env.isdigit() else None
        
        # Obtenemos chat_id, el flag de is_vip y tipo_chat para filtrar privados
        cursor.execute("SELECT chat_id, is_vip, tipo_chat FROM suscriptores")
        filas = cursor.fetchall()
        
        for chat_id, is_vip, tipo_chat in filas:
            es_admin = (chat_id == admin_id)
            
            # Filtro: Ignorar a los usuarios individuales (privados) que no sean el admin
            if tipo_chat == 'private' and not es_admin:
                continue
            
            # El admin siempre recibe las alertas al instante (actúa como VIP).
            if is_vip or es_admin:
                Listas['vip'].append(chat_id)
            else:
                Listas['gratis'].append(chat_id)
                
        return Listas
    except sqlite3.Error as e:
        print(f"Error al obtener suscriptores separados: {e}")
        return {'vip': [], 'gratis': []}
    finally:
        conn.close()

def contar_jugadores():
    """
    Devuelve la cantidad total de jugadores en la base de datos.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM jugadores")
        return cursor.fetchone()[0]
    except sqlite3.Error as e:
        print(f"Error contando jugadores: {e}")
        return 0
    finally:
        conn.close()

def buscar_jugador_por_nombre(nombre_parcial):
    """
    Busca jugadores activos por coincidencias parciales en su nombre.
    """
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jugadores WHERE nombre LIKE ?", (f'%{nombre_parcial}%',))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Error buscando jugador por nombre: {e}")
        return []
    finally:
        conn.close()

def actualizar_vip_usuario(user_id, dias):
    """
    Actualiza a un usuario para que sea VIP por la cantidad de días especificada.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE suscriptores
            SET is_vip = 1,
                fecha_vencimiento_vip = datetime('now', '+' || ? || ' days')
            WHERE chat_id = ?
        ''', (str(dias), user_id))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error al actualizar VIP: {e}")
        return False
    finally:
        conn.close()

def limpiar_vips_vencidos():
    """
    Busca usuarios VIP cuya fecha de vencimiento haya expirado (menor a la fecha actual),
    los pasa a is_vip = 0 y retorna una lista con sus chat_ids.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    # Usamos localtime para comparar con la hora actual del equipo (que es donde se corre el bot)
    # o puede usarse datetime('now', 'localtime')
    
    chat_ids_vencidos = []
    try:
        # Encontrar los vencidos
        cursor.execute('''
            SELECT chat_id FROM suscriptores 
            WHERE is_vip = 1 AND fecha_vencimiento_vip < datetime('now', 'localtime')
        ''')
        vencidos = cursor.fetchall()
        
        for fila in vencidos:
            chat_ids_vencidos.append(fila[0])
            
        if chat_ids_vencidos:
            # Actualizarlos
            placeholders = ', '.join(['?'] * len(chat_ids_vencidos))
            cursor.execute(f'''
                UPDATE suscriptores
                SET is_vip = 0, fecha_vencimiento_vip = NULL
                WHERE chat_id IN ({placeholders})
            ''', chat_ids_vencidos)
            
            conn.commit()
            
        return chat_ids_vencidos
    except sqlite3.Error as e:
        print(f"Error al limpiar VIPs vencidos: {e}")
        return []
    finally:
        conn.close()

# Bloque de prueba
if __name__ == '__main__':
    print("--- 🧪 Test de Funciones CRUD ---")
    
    # 1. Insertamos un jugador de prueba
    id_creado = insertar_jugador(
        futwiz_id=45,
        slug="lionel-messi",
        nombre="Lionel Messi",
        rating=90,
        version_carta="Gold",
        liga="MLS",
        equipo="Inter Miami",
        nacionalidad="Argentina",
        posicion="RW",
        precio_actual=25000,
        precio_historico_minimo=0
    )
    print(f"✅ Jugador insertado con ID interno: {id_creado}")
    
    # 2. Actualizamos el precio
    actualizar_precio_jugador(id_creado, 22000)
    print("✅ Precio actualizado (simulando un drop bajista de mercado)")
    
    # 3. Buscamos al jugador por la nacionalidad y version
    resultados = buscar_jugador_por_requisito({'nacionalidad': 'Argentina', 'version_carta': 'Gold'})
    print(f"🔍 Resultados de la búsqueda:")
    for r in resultados:
        print(f" - {r['nombre']} ({r['rating']}) | Precio Actual: {r['precio_actual']} | Mínimo: {r['precio_historico_minimo']}")
