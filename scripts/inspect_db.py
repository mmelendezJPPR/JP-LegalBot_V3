#!/usr/bin/env python3
"""
Script para inspeccionar la estructura de la base de datos
"""

import sqlite3
import os

def inspect_database(db_path):
    """Inspeccionar estructura de la base de datos"""
    if not os.path.exists(db_path):
        print(f"❌ Base de datos no encontrada: {db_path}")
        return

    print(f"🔍 Inspeccionando: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ver tablas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\n📋 Tablas existentes ({len(tables)}):")

    for table in tables:
        table_name = table[0]
        print(f"\n  📊 Tabla: {table_name}")

        # Ver columnas
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"    Columnas ({len(columns)}):")
        for col in columns:
            col_id, col_name, col_type, not_null, default, pk = col
            print(f"      - {col_name}: {col_type} {'(PK)' if pk else ''} {'(NOT NULL)' if not_null else ''}")

        # Ver algunos registros de ejemplo
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"    Registros: {count}")

            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
                sample = cursor.fetchone()
                print(f"    Ejemplo: {sample}")
        except Exception as e:
            print(f"    Error al contar registros: {e}")

    conn.close()

if __name__ == "__main__":
    # Inspeccionar ambas bases de datos
    inspect_database("database/hybrid_knowledge.db")
    print("\n" + "="*50)
    inspect_database("database/conversaciones.db")