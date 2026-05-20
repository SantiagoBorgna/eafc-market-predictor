import sqlite3
import time
import os
from database.crud import _get_connection, insertar_jugador, actualizar_precio_jugador
from bot.motor_reglas import detectar_panic_selling

def test_panic_selling():
    print("Iniciando tests de Panic Selling...")
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 1. Crear jugador con rating bajo (Ignorado)
    id_bajo = insertar_jugador(9991, "test-bajo", "Jugador Bajo", 75, "Gold", "Liga", "Eq", "Nac", "ST")
    
    # 2. Crear jugador con rating alto (Válido)
    id_alto = insertar_jugador(9992, "test-alto", "Jugador Alto", 85, "Gold", "Liga", "Eq", "Nac", "ST")
    
    # Insertar precios históricos falsos
    # Precio hace 1.5 horas (dentro de la ventana)
    cursor.execute('''
        INSERT INTO historial_precios (jugador_id, precio, fecha_registro) 
        VALUES (?, ?, datetime('now', '-1.5 hours'))
    ''', (id_bajo, 10000))
    cursor.execute('''
        INSERT INTO historial_precios (jugador_id, precio, fecha_registro) 
        VALUES (?, ?, datetime('now', '-1.5 hours'))
    ''', (id_alto, 10000))
    
    # Precio hace 2 días (fuera de la ventana, no debería ser tomado)
    id_viejo = insertar_jugador(9993, "test-viejo", "Jugador Viejo", 85, "Gold", "Liga", "Eq", "Nac", "ST")
    cursor.execute('''
        INSERT INTO historial_precios (jugador_id, precio, fecha_registro) 
        VALUES (?, ?, datetime('now', '-2 days'))
    ''', (id_viejo, 10000))
    conn.commit()
    conn.close()
    
    print("\n--- Test 1: Jugador con Rating < 78 ---")
    res1 = detectar_panic_selling(id_bajo, 5000, "Jugador Bajo", 75)
    print("Resultado:", "Ignorado" if res1 is None else "Alerta!")
    assert res1 is None, "Debería ignorar rating bajo"

    print("\n--- Test 2: Jugador con Rating >= 78 ---")
    res2 = detectar_panic_selling(id_alto, 5000, "Jugador Alto", 85)
    print("Resultado:", "Ignorado" if res2 is None else "Alerta!")
    assert res2 is not None, "Debería dar alerta de panic selling"

    print("\n--- Test 3: Anti-Spam Cooldown ---")
    res3 = detectar_panic_selling(id_alto, 4000, "Jugador Alto", 85)
    print("Resultado (2da vez inmediato):", "Ignorado (Cooldown)" if res3 is None else "Alerta!")
    assert res3 is None, "Debería ignorar por cooldown"

    print("\n--- Test 4: Precio fuera de ventana temporal ---")
    res4 = detectar_panic_selling(id_viejo, 5000, "Jugador Viejo", 85)
    print("Resultado (Precio de hace 2 días):", "Ignorado" if res4 is None else "Alerta!")
    assert res4 is None, "Debería ignorar caída calculada con precio viejo"

    print("\n✅ Todos los tests pasaron exitosamente.")

if __name__ == '__main__':
    test_panic_selling()
