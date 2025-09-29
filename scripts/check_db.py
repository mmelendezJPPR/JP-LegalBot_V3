#!/usr/bin/env python3
import sqlite3

# Conectar a la base de datos
conn = sqlite3.connect('../database/hybrid_knowledge.db')
cursor = conn.cursor()

# Buscar referencias problemáticas
print("🔍 Buscando referencias a 'Reglamento Conjunto' + '2020'...")
cursor.execute("SELECT content FROM fts_chunks WHERE content LIKE '%Reglamento Conjunto%' AND content LIKE '%2020%' LIMIT 3")
results = cursor.fetchall()

print(f"📊 Resultados encontrados: {len(results)}")
for i, (content,) in enumerate(results):
    print(f"\n--- RESULTADO {i+1} ---")
    print(content[:500] + "..." if len(content) > 500 else content)

# Buscar solo "2020"
print("\n🔍 Buscando todas las referencias a '2020'...")
cursor.execute("SELECT content FROM fts_chunks WHERE content LIKE '%2020%' LIMIT 5")
results2020 = cursor.fetchall()

print(f"📊 Total referencias a '2020': {len(results2020)}")
for i, (content,) in enumerate(results2020[:3]):  # Solo mostrar primeras 3
    print(f"\n--- 2020 RESULTADO {i+1} ---")
    print(content[:300] + "..." if len(content) > 300 else content)

conn.close()
print("\n✅ Verificación completada")
