#!/usr/bin/env python3
"""
Script de inicialización de base de datos para JP_LegalBot
Se ejecuta automáticamente en el despliegue para crear las tablas necesarias
"""

import os
import sqlite3
from pathlib import Path

def init_database():
    """Inicializa la base de datos SQLite con las tablas necesarias"""
    
    # Crear directorio database si no existe
    db_dir = Path('database')
    db_dir.mkdir(exist_ok=True)
    
    # Ruta de la base de datos principal
    db_path = db_dir / 'conversaciones.db'
    
    print(f"🔧 Inicializando base de datos en: {db_path}")
    
    try:
        # Conectar a la base de datos (se crea si no existe)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Crear tabla de conversaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                usuario TEXT,
                consulta TEXT NOT NULL,
                respuesta TEXT NOT NULL,
                sistema_usado TEXT,
                confianza REAL,
                tiempo_procesamiento REAL,
                ip_usuario TEXT,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear tabla de métricas de rendimiento
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metricas_rendimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                consulta_length INTEGER,
                respuesta_length INTEGER,
                sistema_usado TEXT,
                confianza REAL,
                tiempo_procesamiento REAL,
                ip TEXT,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear tabla de aprendizaje del sistema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aprendizaje_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patron_consulta TEXT,
                respuesta_generada TEXT,
                efectividad REAL,
                feedback_usuario TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear índices para mejor rendimiento
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_timestamp ON conversaciones(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_usuario ON conversaciones(usuario)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metricas_timestamp ON metricas_rendimiento(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aprendizaje_patron ON aprendizaje_sistema(patron_consulta)")
        
        # Confirmar cambios
        conn.commit()
        
        # Verificar que las tablas se crearon correctamente
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = cursor.fetchall()
        
        print(f"✅ Base de datos inicializada correctamente")
        print(f"📊 Tablas creadas: {[tabla[0] for tabla in tablas]}")
        
        # Insertar un registro de prueba para verificar funcionamiento
        cursor.execute("""
            INSERT INTO conversaciones 
            (timestamp, usuario, consulta, respuesta, sistema_usado, confianza, tiempo_procesamiento, ip_usuario) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            '2025-09-24T00:00:00',
            'sistema',
            'Inicialización del sistema',
            'Base de datos inicializada correctamente en Render',
            'sistema_init',
            1.0,
            0.001,
            '127.0.0.1'
        ))
        
        conn.commit()
        print("✅ Registro de prueba insertado correctamente")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        return False

def verify_database():
    """Verifica que la base de datos esté funcionando correctamente"""
    
    db_path = Path('database') / 'conversaciones.db'
    
    if not db_path.exists():
        print(f"❌ Base de datos no existe: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verificar que podemos consultar la tabla
        cursor.execute("SELECT COUNT(*) FROM conversaciones")
        count = cursor.fetchone()[0]
        
        print(f"✅ Base de datos verificada: {count} registros")
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error verificando base de datos: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Iniciando configuración de base de datos para Render...")
    
    # Inicializar base de datos
    if init_database():
        print("✅ Inicialización completada")
        
        # Verificar funcionamiento
        if verify_database():
            print("✅ Verificación exitosa")
            print("🎉 Sistema listo para producción en Render")
        else:
            print("❌ Falló la verificación")
            exit(1)
    else:
        print("❌ Falló la inicialización")
        exit(1)
